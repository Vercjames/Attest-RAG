"""Confidence: a level an agent can act on, plus the reasons behind it.

Deliberately not the LLM grading itself. Every input is something we can
measure and log, so a reviewer can see why an answer was marked "medium".

  high    act on it
  medium  read the cited passage before quoting it to a customer
  low     treat as a pointer to where to look, not an answer
"""
from __future__ import annotations

from dataclasses import dataclass, field

HIGH_COVERAGE = 0.85
MIN_COVERAGE = 0.6        # below this we refuse rather than answer

LEVELS = ["low", "medium", "high"]


@dataclass
class Confidence:
    level: str                       # high | medium | low | none
    reasons: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)


def assess(*, coverage: float, missing_terms: list[str], cited_doc_types: list[str],
           rankers_agree: bool | None, stale_excluded: list[str],
           validation_ok: bool) -> Confidence:
    signals = {
        "coverage": round(coverage, 2),
        "rankers_agree": rankers_agree,
        "cited_doc_types": sorted(set(cited_doc_types)),
        "stale_excluded": stale_excluded,
        "validation_ok": validation_ok,
    }
    reasons: list[str] = []

    if not validation_ok:
        return Confidence("low", ["answer failed grounding checks"], signals)

    level = 2 if coverage >= HIGH_COVERAGE else 1
    reasons.append(f"query coverage {coverage:.0%}"
                   + (f" (not found: {', '.join(missing_terms)})" if missing_terms else ""))

    def downgrade(why: str) -> None:
        nonlocal level
        level = max(0, level - 1)
        reasons.append(why)

    if rankers_agree is False:
        downgrade("lexical and semantic retrieval disagree on the best source")
    if cited_doc_types and set(cited_doc_types) == {"faq"}:
        downgrade("answer rests only on FAQ content, not policy or fee schedule")
    if stale_excluded:
        downgrade(f"outdated sources were excluded: {', '.join(stale_excluded)}")

    return Confidence(LEVELS[level], reasons, signals)
