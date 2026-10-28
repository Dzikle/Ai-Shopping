"""Deterministic product identity and candidate matching package (ADR-0003)."""

from .matcher import (
    MATCHER_VERSION,
    STOPWORDS,
    extract_signature,
    match_products,
)

__all__ = [
    "MATCHER_VERSION",
    "STOPWORDS",
    "extract_signature",
    "match_products",
]
