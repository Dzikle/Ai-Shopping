"""Unit conversion utilities - exact port of UnitConversionUtil.java."""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal


def normalize_unit(raw_unit: str | None) -> str:
    if raw_unit is None or not raw_unit.strip():
        return "pack"
    u = raw_unit.strip().lower()
    if u in ("g", "gr", "gram", "grams", "гр", "грам"):
        return "g"
    if u in ("kg", "kgr", "kilogram", "kilograms", "кг", "кгр"):
        return "kg"
    if u in ("ml", "milliliter", "milliliters", "мл"):
        return "ml"
    if u in ("l", "lt", "liter", "liters", "л", "литар"):
        return "l"
    if u in ("pcs", "pc", "piece", "pieces", "бр", "број", "пар", "парче"):
        return "pcs"
    return "pack"


def dimension_of(normalized_unit: str) -> str:
    if normalized_unit in ("g", "kg"):
        return "mass"
    if normalized_unit in ("ml", "l"):
        return "volume"
    return "count"


def to_base_amount(quantity: Decimal | None, normalized_unit: str) -> Decimal:
    safe_qty = quantity if (quantity is not None and quantity > 0) else Decimal(1)
    return safe_qty * 1000 if normalized_unit in ("kg", "l") else safe_qty


def scale(value: Decimal | None, places: int) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def compute_packs_needed(
    requested_qty: Decimal | None,
    requested_unit: str | None,
    sku_qty_value: Decimal | None,
    sku_qty_unit: str | None,
    sku_pack_count: int | None,
) -> int:
    safe_req_qty = requested_qty if (requested_qty is not None and requested_qty > 0) else Decimal(1)
    norm_req_unit = normalize_unit(requested_unit)
    req_dim = dimension_of(norm_req_unit)

    if req_dim == "count" or sku_qty_value is None or sku_qty_value <= 0 or sku_qty_unit is None:
        return max(1, int(safe_req_qty.to_integral_value(rounding=ROUND_CEILING)))

    norm_sku_unit = normalize_unit(sku_qty_unit)
    sku_dim = dimension_of(norm_sku_unit)
    if req_dim != sku_dim:
        return max(1, int(safe_req_qty.to_integral_value(rounding=ROUND_CEILING)))

    safe_pack_count = max(1, sku_pack_count or 1)
    requested_base = to_base_amount(safe_req_qty, norm_req_unit)
    per_sku_base = to_base_amount(sku_qty_value, norm_sku_unit) * safe_pack_count
    if per_sku_base <= 0:
        return 1

    packs = (requested_base / per_sku_base).to_integral_value(rounding=ROUND_CEILING)
    return max(1, int(packs))
