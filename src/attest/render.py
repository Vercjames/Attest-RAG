"""Human-readable terminal rendering of an Answer.

The Answer itself carries full chunk ids and exact spans (see --json). For
reading in a terminal, citations become numbered footnotes, text wraps to the
window, and each source gets one header line plus a short quote.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import textwrap

from .generation import CITATION
from .pipeline import Answer, Citation

STATUS_COLOR = {"answered": "32", "unverified": "33", "refused": "31"}   # green / yellow / red
CONF_COLOR = {"high": "32", "medium": "33", "low": "31", "none": "2"}
QUOTE_CHARS = 140


def _use_color() -> bool:
    if os.getenv("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        os.system("")   # turn on ANSI escape handling in the Windows console
    return True


def render(ans: Answer) -> str:
    color = _use_color()
    width = min(shutil.get_terminal_size((100, 20)).columns, 110) - 2

    def c(code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if color else text

    def wrap(text: str, indent: str = "  ", hang: str | None = None) -> list[str]:
        return textwrap.wrap(text, width, initial_indent=indent,
                             subsequent_indent=hang if hang is not None else indent) or [indent]

    out: list[str] = [""]
    out.append(f"  {c('1;' + STATUS_COLOR.get(ans.status, '0'), ans.status.upper())}"
               f"   confidence: {c(CONF_COLOR.get(ans.confidence.level, '0'), ans.confidence.level)}")
    for r in ans.confidence.reasons:
        out += [c("2", line) for line in wrap(r, "  · ", "    ")]
    out.append("")

    # Number sources by first appearance in the answer.
    numbers: dict[str, int] = {}
    for group in CITATION.findall(ans.answer or ""):
        for cid in (i.strip() for i in re.split(r"[,;]", group)):
            numbers.setdefault(cid, len(numbers) + 1)

    def footnote(m: re.Match) -> str:
        ids = [i.strip() for i in re.split(r"[,;]", m.group(1))]
        return c("36", "[" + ",".join(str(numbers[i]) for i in ids if i in numbers) + "]")

    if ans.answer:
        for line in _merge_same_source(ans.answer):
            bullet = line.startswith("- ")
            if line.endswith(":") and not CITATION.search(line):
                if out[-1]:
                    out.append("")
                out.append(c("1", f"  {line}"))
                continue
            # wrap the plain text first, then color footnotes, so escapes don't skew widths
            plain = CITATION.sub(lambda m: "[" + ",".join(
                str(numbers.get(i.strip(), "?")) for i in re.split(r"[,;]", m.group(1))) + "]", line)
            for w in wrap(plain[2:] if bullet else plain, "  • " if bullet else "  ", "    " if bullet else "  "):
                out.append(re.sub(r"\[([\d,?]+)\]", lambda m: c("36", m.group(0)), w))
        out.append("")

    by_id = {x.chunk_id: x for x in ans.citations}
    if numbers:
        out.append(c("1", "  Sources") + c("2", "  (the [n] after each line points here)"))
        for cid, n in numbers.items():
            if cid in by_id:
                out += _source(by_id[cid], c("36", f"[{n}]"), c, wrap)
        out.append("")

    # "Excluded <id>: <why>" notices belong next to the passage they explain.
    why = {}
    notices = []
    for n in ans.notices:
        m = re.match(r"Excluded (\S+): (.*)", n)
        if m:
            why[m.group(1)] = m.group(2)
        else:
            notices.append(n)

    if ans.related:
        label = "Excluded (outdated)" if ans.status == "answered" else "Closest passages"
        out.append(c("1", f"  {label}"))
        for x in ans.related:
            out += _source(x, c("2", "·"), c, wrap)
            if x.chunk_id in why:
                out += [c("33", line) for line in wrap(why[x.chunk_id], "      ")]
        out.append("")

    for n in notices:
        out += [c("2", line) for line in wrap(n, "  note: ", "        ")]
    return "\n".join(out).rstrip() + "\n"


def _merge_same_source(answer: str) -> list[str]:
    """Join consecutive prose sentences that cite the same source, so the
    marker appears once per paragraph instead of once per sentence."""
    merged: list[str] = []
    prev_cite = None
    for line in (l.strip() for l in answer.strip().splitlines()):
        if not line:
            prev_cite = None
            continue
        cites = CITATION.findall(line)
        prose = not line.startswith("- ") and len(cites) == 1 and line.endswith(f"[{cites[0]}]")
        if prose and merged and prev_cite == cites[0]:
            body = line[: -len(f"[{cites[0]}]")].rstrip()
            merged[-1] = merged[-1][: -len(f"[{cites[0]}]")].rstrip() + " " + body + f" [{cites[0]}]"
        else:
            merged.append(line)
        prev_cite = cites[0] if prose else None
    return merged


def _source(x: Citation, marker: str, c, wrap) -> list[str]:
    quote = " ".join(x.text.split())
    if len(quote) > QUOTE_CHARS:
        quote = quote[:QUOTE_CHARS].rsplit(" ", 1)[0] + " …"
    label = x.heading if x.heading.startswith(x.title) else f"{x.title} > {x.heading}"
    lines = [f"  {marker} {label}  " + c("2", f"{x.path}:{x.start}-{x.end}")]
    lines += [c("2", line) for line in wrap(f'"{quote}"', "      ")]
    return lines
