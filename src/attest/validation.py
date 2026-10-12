"""Deterministic checks on a draft before anyone sees it.

The failure that matters most in a support setting is a confident wrong
number: a fee, a limit, a cutoff time. So beyond "are the citations real",
every number in the answer must appear in a passage the answer cites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .chunking import Chunk
from .generation import CITATION, Draft
from .retrieval import normalize_number

_NUMBER = re.compile(r"\$?\d[\d,:]*(?:\.\d+)?%?")


@dataclass
class Validation:
    unknown_citations: list[str] = field(default_factory=list)   # cited but not retrieved
    ungrounded_numbers: list[str] = field(default_factory=list)  # not in any cited passage
    uncited: bool = False                                         # no citations at all

    @property
    def ok(self) -> bool:
        return not (self.unknown_citations or self.ungrounded_numbers or self.uncited)

    def problems(self) -> list[str]:
        out = []
        if self.uncited:
            out.append("answer has no citations")
        if self.unknown_citations:
            out.append(f"cites passages that were not retrieved: {self.unknown_citations}")
        if self.ungrounded_numbers:
            out.append(f"numbers not found in cited passages: {self.ungrounded_numbers}")
        return out


def numbers_in(text: str) -> set[str]:
    return {normalize_number(n).rstrip(".:") for n in _NUMBER.findall(text)}


def validate(draft: Draft, context: list[Chunk]) -> Validation:
    by_id = {c.chunk_id: c for c in context}
    cited = draft.cited_ids
    v = Validation(uncited=not cited)
    v.unknown_citations = [cid for cid in cited if cid not in by_id]

    source_numbers: set[str] = set()
    for cid in cited:
        if c := by_id.get(cid):
            source_numbers |= numbers_in(c.text) | numbers_in(c.index_text)
    answer_body = CITATION.sub("", draft.text)
    v.ungrounded_numbers = sorted(numbers_in(answer_body) - source_numbers)
    return v
