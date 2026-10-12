"""Load the corpus into Documents with named sections.

Every Document has a `text` that citations point into. For markdown and CSV
that is the raw file, so a span's offsets are true file offsets. For HTML it
is the extracted article text (boilerplate removed); raw-HTML offsets would be
useless to an agent reading a citation.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml
from bs4 import BeautifulSoup

# Authority when sources disagree: policy and the fee schedule are the
# system of record; FAQs are customer-facing summaries that drift.
# Applied as a rank penalty inside fusion (a FAQ at rank r is scored as if it
# were at rank r + 2), so it breaks near-ties without burying a FAQ that is
# clearly the best match. An earlier multiplicative weight did bury them:
# RRF scores are compressed enough that x0.8 dropped a #1 FAQ to ~#15.
AUTHORITY_RANK_PENALTY = {"policy": 0, "fee_schedule": 0, "faq": 2}


@dataclass
class Section:
    heading: str          # e.g. "Overdraft Policy > Overdraft fee"
    start: int            # offsets into Document.text
    end: int


@dataclass
class Document:
    doc_id: str
    title: str
    doc_type: str         # policy | faq | fee_schedule
    path: str
    text: str
    sections: list[Section]
    meta: dict = field(default_factory=dict)

    @property
    def superseded_by(self) -> str | None:
        return self.meta.get("superseded_by")


# ---------------------------------------------------------------- markdown

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.+)$", re.M)


def load_markdown(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    meta, body_start = {}, 0
    if m := _FRONT_MATTER.match(text):
        meta = yaml.safe_load(m.group(1)) or {}
        body_start = m.end()

    sections: list[Section] = []
    trail: list[str] = []
    headings = list(_HEADING.finditer(text, body_start))
    for i, h in enumerate(headings):
        level, title = len(h.group(1)), h.group(2).strip()
        trail = trail[: level - 1] + [title]
        start = h.end() + 1
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        if text[start:end].strip():
            sections.append(Section(" > ".join(trail), *_strip_span(text, start, end)))

    return Document(
        doc_id=meta.get("doc_id", path.stem),
        title=meta.get("title", path.stem),
        doc_type=meta.get("type", "policy"),
        path=str(path),
        text=text,
        sections=sections,
        meta=meta,
    )


# ---------------------------------------------------------------- html

# Help-center exports wrap every article in the same chrome. Left in, it
# shows up in every page's chunks and matches queries like "fees".
_BOILERPLATE = ["script", "style", "nav", "header", "footer", "aside"]
_BOILERPLATE_CLASSES = ["cookie-banner", "breadcrumbs", "feedback-widget"]


def load_html(path: Path) -> Document:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    meta = {m["name"]: m["content"] for m in soup.find_all("meta") if m.get("name")}

    for tag in soup(_BOILERPLATE):
        tag.decompose()
    for cls in _BOILERPLATE_CLASSES:
        for tag in soup.find_all(class_=cls):
            tag.decompose()

    root = soup.find("article") or soup.find("main") or soup.body
    title = root.find("h1").get_text(" ", strip=True) if root.find("h1") else path.stem

    # Rebuild clean text block by block so we know where each section lives.
    parts: list[str] = []
    sections: list[Section] = []
    pos, heading, sec_start = 0, title, None

    def emit(s: str) -> None:
        nonlocal pos
        parts.append(s)
        pos += len(s)

    for el in root.find_all(["h1", "h2", "h3", "p", "li"]):
        txt = " ".join(el.get_text(" ", strip=True).split())
        if not txt:
            continue
        if el.name in ("h1", "h2", "h3"):
            if sec_start is not None and pos > sec_start:
                sections.append(Section(heading, sec_start, pos - 1))
            heading = title if el.name == "h1" else f"{title} > {txt}"
            emit(txt + "\n")
            sec_start = pos
        else:
            emit(("- " if el.name == "li" else "") + txt + "\n")
    if sec_start is not None and pos > sec_start:
        sections.append(Section(heading, sec_start, pos - 1))

    return Document(
        doc_id=meta.get("doc-id", path.stem),
        title=title,
        doc_type=meta.get("doc-type", "faq"),
        path=str(path),
        text="".join(parts),
        sections=sections,
        meta=meta,
    )


# ---------------------------------------------------------------- csv

def load_fee_schedule(path: Path) -> Document:
    """One section per fee row. Offsets are the row's raw line in the file.

    Exports have junk: blank lines and a trailing '#' comment. Skip both
    rather than indexing them.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    header = next(csv.reader([lines[0]]))
    sections: list[Section] = []
    rows: dict[str, dict] = {}
    offset = len(lines[0])
    for line in lines[1:]:
        start, offset = offset, offset + len(line)
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        row = dict(zip(header, next(csv.reader(io.StringIO(line)))))
        rows[row["fee_id"]] = row
        sections.append(Section(row["fee_id"], start, start + len(line.rstrip("\r\n"))))

    return Document(
        doc_id=path.stem,
        title="Fee and Rate Schedule",
        doc_type="fee_schedule",
        path=str(path),
        text=text,
        sections=sections,
        meta={"rows": rows},
    )


# ---------------------------------------------------------------- corpus

LOADERS = {".md": load_markdown, ".html": load_html, ".csv": load_fee_schedule}


def load_corpus(root: str | Path, today: date | None = None) -> list[Document]:
    root = Path(root)
    docs = []
    for p in sorted(root.rglob("*")):
        if p.suffix in LOADERS:
            doc = LOADERS[p.suffix](p)
            doc.path = p.relative_to(root).as_posix()   # stable across machines
            docs.append(doc)
    mark_superseded(docs, today or date.today())
    return docs


def mark_superseded(docs: list[Document], today: date) -> None:
    """Old versions of a policy stay in real KBs. Detect them by policy_id
    and effective date instead of trusting someone to delete the old file."""
    by_policy: dict[str, list[Document]] = {}
    for d in docs:
        if pid := d.meta.get("policy_id"):
            by_policy.setdefault(pid, []).append(d)
    for versions in by_policy.values():
        live = [d for d in versions if _as_date(d.meta.get("effective")) <= today]
        if len(live) < 2:
            continue
        live.sort(key=lambda d: _as_date(d.meta["effective"]))
        current = live[-1]
        for old in live[:-1]:
            old.meta["superseded_by"] = current.doc_id
            current.meta.setdefault("supersedes", []).append(old.doc_id)


def _as_date(v) -> date:
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)) if v else date.min


def _strip_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end
