"""Strip customer identifiers from a query before it is logged or sent to an LLM.

Regex-based and intentionally conservative: it will miss identifiers phrased
in words ("my account ending in four four one seven"). Good enough to keep
obvious PII out of the audit log; not a substitute for a real DLP service.
"""
from __future__ import annotations

import re

_PATTERNS = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("PHONE", re.compile(r"\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")),
    # 8-19 bare digits: account and card numbers. Amounts like 5,000 or
    # $10000.00 don't match (commas, $, decimals, or too short).
    ("ACCOUNT_NUMBER", re.compile(r"(?<![$\d.,])\b\d{8,19}\b(?![.,]\d)")),
]


def redact(text: str) -> tuple[str, list[str]]:
    found = []
    for label, pattern in _PATTERNS:
        text, n = pattern.subn(f"[{label}]", text)
        found += [label] * n
    return text, found
