"""The checks that stand between a generated answer and an agent quoting it."""
import json

from attest.generation import Draft
from attest.validation import validate


def _ctx(chunks, *ids):
    by_id = {c.chunk_id: c for c in chunks}
    return [by_id[i] for i in ids]


def test_number_must_appear_in_a_cited_passage(chunks):
    ctx = _ctx(chunks, "fees#WDO-PLS")
    assert validate(Draft("Plus pays $25 per domestic wire. [fees#WDO-PLS]"), ctx).ok
    bad = validate(Draft("Plus pays $35 per domestic wire. [fees#WDO-PLS]"), ctx)
    assert bad.ungrounded_numbers == ["35"]


def test_number_in_an_uncited_passage_does_not_count(chunks):
    ctx = _ctx(chunks, "fees#WDO-PLS", "fees#WIO-PER")
    # $45 is in the context, but not in the passage the sentence cites
    assert validate(Draft("International is $45. [fees#WDO-PLS]"), ctx).ungrounded_numbers == ["45"]


def test_citations_must_be_to_retrieved_passages(chunks):
    ctx = _ctx(chunks, "fees#WDO-PLS")
    v = validate(Draft("Plus pays $25. [fees#WDO-PLS] [made-up#1]"), ctx)
    assert v.unknown_citations == ["made-up#1"]
    assert validate(Draft("Plus pays $25."), ctx).uncited


class HallucinatingGenerator:
    name = "stub"

    def generate(self, query, context):
        return Draft(f"The fee is $99. [{context[0].chunk_id}]")


def test_ungrounded_answer_is_withheld_not_shown(system):
    system.generator = HallucinatingGenerator()
    ans = system.ask("What is the overdraft fee?")
    assert ans.status == "unverified"
    assert ans.answer is None
    assert ans.related                      # agent still gets the passages
    assert any("99" in n for n in ans.notices)


def test_stale_faq_is_excluded_and_current_fee_by_tier_is_returned(system):
    ans = system.ask("What is the overdraft fee?")
    assert ans.status == "answered"
    assert "$35" not in ans.answer
    cited = {c.chunk_id for c in ans.citations}
    assert {"fees#OD-ESS", "fees#OD-PLS", "fees#OD-PRM", "fees#OD-BIZ"} <= cited
    assert "faq-overdraft#1" in {c.chunk_id for c in ans.related}


def test_account_questions_are_refused_and_pii_never_logged(system):
    ans = system.ask("Why was account 4417889023 charged $35 on March 3?")
    assert ans.status == "refused" and ans.refusal_reason == "account_specific"
    assert "4417889023" not in ans.query
    log = system.audit_log.read_text()
    assert "4417889023" not in log
    assert json.loads(log.splitlines()[-1])["redactions"] == ["ACCOUNT_NUMBER"]


def test_out_of_scope_is_refused_with_closest_passages(system):
    ans = system.ask("What is the APY on bitcoin savings?")
    assert ans.status == "refused" and ans.refusal_reason == "insufficient_context"
    assert ans.confidence.level == "none"
