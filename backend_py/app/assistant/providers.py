"""Provider-neutral model adapters for the assistant (M13).

Design rules (m13 task doc, "Provider configuration"):
- narrow adapter at the FastAPI boundary, no provider router;
- model id / base URL / key / max tokens / timeout / invocation budget come
  from server-side env config only (never shipped to Flutter);
- the model is a language interpreter: it returns *search labels*, never
  product IDs, prices, stock or totals;
- structured output contract validated strictly; nonconforming output or an
  outage yields explicit recoverable states, never a fabricated pass;
- the deterministic `MockShoppingProvider` exists for tests and explicit
  local opt-in (`ASSISTANT_PROVIDER=mock`); it is always flagged as a mock.

Only the standard library is used for the outbound HTTP call so the backend
keeps its dependency set unchanged.
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, ValidationError

from app.assistant.transliteration import transliterate_to_cyrillic

ALLOWED_UNITS = ("pack", "pcs", "g", "kg", "ml", "l")
MAX_ITEMS_PER_TURN = 8
MAX_MESSAGE_CHARS = 500
MAX_CONTEXT_ENTRIES = 6
MAX_CONTEXT_CHARS_PER_ENTRY = 400

_MONEY_KEY_PATTERN = re.compile(r"price|total|cost|savin|summ|paid|den\.?|mkd", re.IGNORECASE)


class ProviderUnavailable(Exception):
    """The configured provider could not be reached / timed out / auth failed."""


class ProviderInvalidResponse(Exception):
    """The provider answered but its output violated the strict contract."""


@dataclass
class InterpreterRequest:
    message: str
    locale: str = "mk"
    context: list[dict] | None = None        # [{"role": "user"|"assistant", "content": str}]
    basket_labels: list[str] | None = None   # context only; never trusted


@dataclass
class ParsedItem:
    label: str
    quantity: float | None = None
    unit: str = "pack"

    @property
    def search_query(self) -> str:
        return transliterate_to_cyrillic(self.label)


@dataclass
class InterpreterPlan:
    assistant_message: str | None = None
    items: list[ParsedItem] = field(default_factory=list)


class AssistantProvider:
    """Narrow seam the coordinator is bound to."""

    id: str = "abstract"
    is_mock: bool = False

    def plan_turn(self, request: InterpreterRequest) -> InterpreterPlan:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock provider (deterministic, tests + explicit local opt-in only)
# ---------------------------------------------------------------------------

_SPLIT_PATTERN = re.compile(r"[,;\n]|(?:^|\s)и(?:\s|$)|(?:^|\s)(?:i|and)(?:\s|$)", re.IGNORECASE)

_SORTED_QUANTITY_WORDS = {  # longest words first for greedy matching
    "килограми": "kg",
    "килограма": "kg",
    "килограм": "kg",
    "парчиња": "pcs",
    "грамови": "g",
    "литари": "l",
    "литри": "l",
    "литара": "l",
    "литра": "l",
    "литре": "l",
    "литар": "l",
    "пакети": "pack",
    "пакет": "pack",
    "парче": "pcs",
    "комади": "pcs",
    "комад": "pcs",
    "грама": "g",
    "грам": "g",
    "кило": "kg",
    "litri": "l",
    "litar": "l",
    "grams": "g",
    "gram": "g",
    "units": "pcs",
    "count": "pcs",
    "packs": "pack",
    "pack": "pack",
    "kg": "kg",
    "g": "g",
    "г": "g",
    "гр": "g",
    "кг": "kg",
    "мл": "ml",
    "ml": "ml",
    "l": "l",
    "л": "l",
    "пк": "pack",
    "pcs": "pcs",
}

_QUANTITY_WORDS_PATTERN = re.compile(
    r"(?i)\s*(\d+(?:[.,]\d+)?)\s*(" + "|".join(re.escape(w) for w in sorted(_SORTED_QUANTITY_WORDS, key=len, reverse=True)) + r")\b"
)

_POLITE_PREFIXES = [
    "направи ми список за",
    "направи ми список",
    "направи ми кошница",
    "направи ми листа",
    "направи ми листа за пазарење",
    "додај ми",
    "додај",
    "треба ми",
    "make me a list of",
    "make me a list",
    "add",
    "i need",
]


class MockShoppingProvider(AssistantProvider):
    """Deterministic offline interpreter for tests and local demos.

    Not production AI: it parses simple Macedonian/Latin/English requests
    ("млеко, 500 г брашно и 2 литра јогурт") into bounded search items.
    It is always reported to the client as `is_mock` so nobody can mistake
    scripted parsing for a live model.
    """

    id = "mock"
    is_mock = True

    def plan_turn(self, request: InterpreterRequest) -> InterpreterPlan:
        text = (request.message or "").strip().lower()
        prefixes = [
            re.escape(p)
            for p in _POLITE_PREFIXES
        ]
        for prefix in prefixes:
            stripped = re.sub(prefix, "", text, count=1, flags=re.IGNORECASE)
            if stripped != text:
                text = stripped.strip(" :,.:-_")
        text = re.sub(r"кошниц[аатаиауеи]*", " ", text)
        text = re.sub(r"список.*?(?=:\s*|$)", " ", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"за неделно пазарење", " ", text, flags=re.IGNORECASE)
        text = text.strip(" :,.:-_")
        if not text:
            return InterpreterPlan(
                assistant_message="Не напишавте производи; обидете се повторно со пример: „млеко, јајца и леб“.",
                items=[],
            )
        items: list[ParsedItem] = []
        for segment in _SPLIT_PATTERN.split(text):
            parsed = self._parse_segment(segment)
            if parsed is not None:
                items.append(parsed)
            if len(items) >= MAX_ITEMS_PER_TURN:
                break
        plan_items = items[:MAX_ITEMS_PER_TURN]
        message = self._compose_message(plan_items)
        return InterpreterPlan(assistant_message=message, items=plan_items)

    def _parse_segment(self, segment: str) -> ParsedItem | None:
        seg = segment.strip(" :,.:-_").strip()
        if not seg:
            return None
        quantity: float | None = None
        unit = "pack"
        match = _QUANTITY_WORDS_PATTERN.search(seg)
        if match:
            qty_raw = match.group(1).replace(",", ".")
            try:
                numeric = Decimal(qty_raw)
            except InvalidOperation:
                numeric = None
            if numeric is not None and numeric > 0:
                quantity = float(numeric)
                unit = _SORTED_QUANTITY_WORDS.get(match.group(2).lower(), "pack")
        label = _QUANTITY_WORDS_PATTERN.sub(" ", seg, count=1)
        label = label.strip(" .,:-–—")
        label = label.strip()
        if not label or label.isdigit():
            return None
        if len(label) > 80:
            label = label[:80].strip()
        return ParsedItem(label=label, quantity=quantity, unit=unit)

    def _compose_message(self, items: list[ParsedItem]) -> str:
        if not items:
            return "Не можев детерминистички да извадам производи од барањето."
        labels = [f"„{i.label}“" for i in items]
        joined = ", ".join(labels[:-1]) + f" и {labels[-1]}" if len(labels) > 1 else labels[0]
        return (
            f"Прегледав каталог по барање за {joined}. "
            "Проверете ги предлог-промените подолу пред да ги потврдите; "
            "цените и вкупните суми ги пресметува детерминистичкиот оптимизатор на серверот."
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (opt-in, server-side credentials only)
# ---------------------------------------------------------------------------

class _PlanItemModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    quantity: float | None = None
    unit: str | None = None


class _ModelPlanModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[_PlanItemModel] = []
    assistantMessage: str | None = None


class OpenAICompatibleProvider(AssistantProvider):
    """Chat-completions adapter for a user-configured provider/base URL.

    The model must answer with a JSON object `{"items":[{"label", "quantity",
    "unit"}], "assistantMessage"}`. Anything else — text around JSON, extra
    money-like keys in consumed fields, invalid units, out-of-bound counts —
    is rejected with `ProviderInvalidResponse` (never partially applied).
    One outbound call per turn; no retries, no streaming.
    """

    id = "openai_compatible"

    def __init__(self, model: str, base_url: str, api_key: str, max_tokens: int, timeout_seconds: float):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds

    @property
    def model_name(self) -> str:
        return self._model

    def plan_turn(self, request: InterpreterRequest) -> InterpreterPlan:
        payload = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _build_system_prompt()},
                *[
                    {"role": m.get("role") or "user", "content": str(m.get("content") or "")[: MAX_CONTEXT_CHARS_PER_ENTRY]}
                    for m in (request.context or [])[-MAX_CONTEXT_ENTRIES:]
                    if _is_transportable_role(m.get("role"))
                ],
                {"role": "user", "content": _build_user_content(request)},
            ],
        }
        text = self._call_chat(payload)
        plan = self._parse_plan(text)
        return plan

    def _call_chat(self, payload: dict) -> str:
        endpoint = f"{self._base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            # 4xx/5xx: record nothing about credentials; raise coarse outage.
            raise ProviderUnavailable(f"provider_http_{exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailable(f"provider_unreachable: {type(exc).__name__}") from None
        try:
            decoded = json.loads(raw)
            content = decoded["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise ProviderInvalidResponse("nonconforming_provider_envelope") from None
        if not isinstance(content, str):
            raise ProviderInvalidResponse("provider_content_not_text")
        return content

    def _parse_plan(self, content: str) -> InterpreterPlan:
        stripped = content.strip()
        fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
        if fence_match:
            stripped = fence_match.group(1)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ProviderInvalidResponse("no_json_object")
        json_text = stripped[start : end + 1]
        try:
            document = json.loads(json_text)
        except json.JSONDecodeError:
            raise ProviderInvalidResponse("invalid_json") from None
        if not isinstance(document, dict):
            raise ProviderInvalidResponse("json_not_object")
        for key, value in document.items():
            if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                raise ProviderInvalidResponse("unsupported_value_type")
        # Money-like top-level fields must not exist (the model cannot carry prices).
        if any(_MONEY_KEY_PATTERN.search(str(key)) for key in document.keys()):
            raise ProviderInvalidResponse("price_like_field_from_model")
        try:
            parsed = _ModelPlanModel.model_validate(document)
        except ValidationError as exc:
            raise ProviderInvalidResponse(f"schema_validation: {len(exc.errors())} errors") from None
        items: list[ParsedItem] = []
        for raw in parsed.items[:MAX_ITEMS_PER_TURN]:
            label = str(raw.label or "").strip()
            if not label or len(label) > 80:
                continue
            quantity, unit = _validated_quantity(raw.quantity, raw.unit)
            items.append(ParsedItem(label=label, quantity=quantity, unit=unit))
        message = (parsed.assistantMessage or "").strip()
        if len(message) > 700:
            message = message[:700].strip()
        return InterpreterPlan(assistant_message=message or None, items=items)


def _validated_quantity(quantity, unit) -> tuple[float | None, str]:
    q: float | None = None
    if quantity is not None:
        try:
            d = Decimal(str(quantity))
        except InvalidOperation:
            d = None
        if d is not None and d > 0:
            bounded = d.quantize(Decimal("0.001"))
            if bounded > Decimal("100000"):
                bounded = Decimal("100000")
            q = float(bounded)
    u = str(unit or "pack").strip().lower()
    if u not in ALLOWED_UNITS:
        u = "pack"
    return q, u


def _is_transportable_role(role) -> bool:
    return str(role or "").lower() in ("user", "assistant")


def _build_system_prompt() -> str:
    return (
        "You are a Macedonian-language shopping assistant interpreter for the AI Shopping app. "
        "Read the user's shopping request (Macedonian Cyrillic, Latin romanization or English) "
        "and return ONLY a JSON object with the fields "
        '{"items":[{"label":"производ","quantity":number,"unit":"pack|pcs|g|kg|ml|l"}],"assistantMessage":"..."}'
        ". Rules: extract at most 8 product labels exactly as requested (normalize spelling to "
        "Cyrillic when the input is Latin), copy requested quantities and units (pack/pcs/g/kg/ml/l, "
        "default pack), never add prices, totals, product IDs, stores or availability - those come "
        "from server tools later. Keep assistantMessage under 700 characters and mention nothing "
        "numeric. No markdown, no extra JSON keys."
    )


def _build_user_content(request: InterpreterRequest) -> str:
    lines = [f"MESSAGE: {request.message[:MAX_MESSAGE_CHARS]}"]
    context = (request.context or [])[-MAX_CONTEXT_ENTRIES:]
    for entry in context:
        role = "USER" if str(entry.get("role")) == "user" else "ASSISTANT"
        lines.append(f"{role}: {str(entry.get('content') or '')[: MAX_CONTEXT_CHARS_PER_ENTRY]}")
    basket = (request.basket_labels or [])[:20]
    if basket:
        lines.append("BASKET_LABELS: " + ", ".join(b[:60] for b in basket))
    if request.locale == "en":
        lines.append("ANSWER IN English in assistantMessage; keep labels in the original language.")
    return "\n".join(lines)


def build_provider(settings) -> AssistantProvider | None:
    """Resolve the configured provider from settings; None = no model configured."""
    if settings.assistant_provider == "mock":
        return MockShoppingProvider()
    if settings.assistant_provider == "openai_compatible":
        if settings.assistant_model and settings.assistant_base_url:
            return OpenAICompatibleProvider(
                model=settings.assistant_model,
                base_url=settings.assistant_base_url,
                api_key=settings.assistant_api_key,
                max_tokens=max(256, min(4096, settings.assistant_max_output_tokens)),
                timeout_seconds=max(5.0, settings.assistant_timeout_seconds),
            )
    return None


def provider_info(provider: AssistantProvider | None) -> dict:
    if provider is None:
        return {"id": "none", "model": None, "isMock": False, "configured": False}
    if provider.is_mock:
        return {"id": "mock", "model": None, "isMock": True, "configured": True}
    model = getattr(provider, "model_name", None)
    return {"id": provider.id, "model": model, "isMock": False, "configured": True}
