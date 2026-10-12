"""Turn Documents into retrievable Chunks.

A chunk has two texts:
  text        the exact source span (doc.text[start:end]); this is what gets cited
  index_text  what retrieval sees: the span plus title/heading context, or for a
              fee row, the row rendered as a sentence with its column names

Keeping them separate is the table decision: a CSV line like
"WDO-PLS,Outgoing domestic wire,Wires,Plus Checking,$25.00,..." retrieves
badly as-is, but it is what an agent should be shown verbatim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .documents import Document

MAX_CHARS = 900   # sections in this corpus are short; only split the outliers


@dataclass
class Chunk:
    chunk_id: str
    doc: Document
    heading: str
    start: int
    end: int
    index_text: str

    @property
    def text(self) -> str:
        return self.doc.text[self.start:self.end]

    @property
    def doc_id(self) -> str:
        return self.doc.doc_id


def chunk_documents(docs: list[Document]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        if doc.doc_type == "fee_schedule":
            chunks.extend(_fee_row_chunks(doc))
        else:
            chunks.extend(_section_chunks(doc))
    return chunks


def _section_chunks(doc: Document) -> list[Chunk]:
    out = []
    for sec in doc.sections:
        for start, end in _split(doc.text, sec.start, sec.end):
            cid = f"{doc.doc_id}#{len(out) + 1}"
            ctx = sec.heading if sec.heading.startswith(doc.title) else f"{doc.title} > {sec.heading}"
            body = render_tables(doc.text[start:end])
            out.append(Chunk(cid, doc, sec.heading, start, end, f"{ctx}\n{body}"))
    return out


_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")


def render_tables(text: str) -> str:
    """Rewrite markdown table rows as 'Column: value; Column: value'.

    Same idea as the fee CSV: a bare row like '| Premier | $5,000.00 |' has
    no words for a query to match, and loses its meaning out of context.
    Prose passes through unchanged.
    """
    out, header = [], None
    for line in text.splitlines():
        m = _TABLE_ROW.match(line)
        if not m:
            header = None
            out.append(line)
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if header is None:
            header = cells
        elif not all(set(c) <= set("-: ") for c in cells):
            out.append("; ".join(f"{h}: {v}" for h, v in zip(header, cells)) + ".")
    return "\n".join(out)


def _split(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split an oversized section on paragraph boundaries, keeping offsets."""
    if end - start <= MAX_CHARS:
        return [(start, end)]
    spans, cur = [], start
    for m in re.finditer(r"\n\s*\n", text[start:end]):
        brk = start + m.start()
        if brk - cur >= MAX_CHARS // 2:
            spans.append((cur, brk))
            cur = start + m.end()
    spans.append((cur, end))
    return spans


def _fee_row_chunks(doc: Document) -> list[Chunk]:
    out = []
    for sec in doc.sections:
        row = doc.meta["rows"][sec.heading]
        rendered = (
            f"{doc.title}: {row['fee_name']} ({row['category']} fee) "
            f"for {row['account_tier']} is {row['amount']} {row['unit']}."
        )
        if row.get("notes"):
            rendered += f" Notes: {row['notes']}."
        rendered += f" Effective {row['effective_date']}."
        out.append(Chunk(f"{doc.doc_id}#{row['fee_id']}", doc, row["fee_name"],  # heading = fee family
                         sec.start, sec.end, rendered))
    return out
