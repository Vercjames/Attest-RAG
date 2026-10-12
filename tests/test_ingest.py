"""Citations are only useful if they point at the real text."""
from conftest import ROOT


def test_every_chunk_is_an_exact_source_span(docs, chunks):
    for c in chunks:
        assert c.text == c.doc.text[c.start:c.end]
        assert c.text.strip(), c.chunk_id
    # markdown and csv spans are true file offsets, not offsets into a copy
    for c in chunks:
        if c.doc.doc_type != "faq":
            raw = (ROOT / "data" / "corpus" / c.doc.path).read_text(encoding="utf-8")
            assert raw[c.start:c.end] == c.text


def test_html_boilerplate_is_not_indexed(chunks):
    faq_text = " ".join(c.index_text for c in chunks if c.doc.doc_type == "faq")
    for junk in ["cookies", "Member FDIC", "Was this article helpful", "Sign In", "Help Center >"]:
        assert junk not in faq_text


def test_fee_schedule_skips_export_junk_and_keeps_quoted_commas(docs):
    fees = next(d for d in docs if d.doc_type == "fee_schedule")
    rows = fees.meta["rows"]
    assert len(rows) == 34                               # blank line and '#' footer skipped
    assert rows["RI-PER"]["account_tier"] == "Essential, Plus Checking"
    assert "FeeMaster" not in " ".join(fees.text[s.start:s.end] for s in fees.sections)


def test_fee_row_is_cited_raw_but_indexed_with_column_context(chunks):
    row = next(c for c in chunks if c.chunk_id == "fees#WIO-PRM")
    assert row.text.startswith("WIO-PRM,Outgoing international wire")
    assert "Premier Checking is $45.00 per transfer" in row.index_text
    assert "First 2 per statement cycle waived" in row.index_text


def test_markdown_tables_are_indexed_as_labeled_values(chunks):
    limits = next(c for c in chunks if c.doc_id == "instant-transfers-policy" and "Daily limit" in c.text)
    assert "Account tier: Premier Checking; Daily limit: $5,000.00" in limits.index_text


def test_older_policy_version_is_marked_superseded(docs):
    by_id = {d.doc_id: d for d in docs}
    assert by_id["overdraft-policy-2025"].superseded_by == "overdraft-policy-2026"
    assert by_id["overdraft-policy-2026"].superseded_by is None
