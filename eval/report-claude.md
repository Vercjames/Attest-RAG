# Eval report

Retrieval: **hybrid** · generator: **claude** · 19 queries

## Summary

| metric | result |
|---|---|
| end-to-end pass | 16/19 |
| retrieval@5 (expected doc retrieved) | 15/16 |
| required facts present (answered queries) | 12/12 |
| no stale/wrong fact | 19/19 |
| correct refuse/answer behavior | 16/19 |
| confidence on passing answers: high / medium / low | 3 / 7 / 2 |
| confidence on failing answers: high / medium / low | 0 / 0 / 0 |

## Per query

| id | pass | status | conf | retr@5 | facts | trap |
|---|---|---|---|---|---|---|
| q01 | ✅ | answered | medium | ✅ | ✅ | none (baseline direct lookup) |
| q02 | ✅ | answered | medium | ✅ | ✅ | answer lives only in the fee table |
| q03 | ✅ | answered | medium | ✅ | ✅ | superseded policy and a stale FAQ both say $35; current fee is $15 and varies by tier |
| q04 | ✅ | answered | medium | ✅ | ✅ | FAQ says "about 10 days", policy says provisional credit within 10 business days and investigation up to 45/90 days |
| q05 | ✅ | answered | medium | ✅ | ✅ | ambiguous; depends on direction, destination, and tier |
| q06 | ✅ | answered | low | ✅ | ✅ | needs two documents (lost card + foreign transaction fee in the table) |
| q07 | ❌ | refused (insufficient_context) | none | ✅ | – | vocabulary mismatch ("bounced" vs "returned item" / "NSF") |
| q08 | ❌ | refused (insufficient_context) | none | ❌ | – | out of scope for rates, but the corpus does say how to route it |
| q09 | ✅ | refused (insufficient_context) | none | – | – | out of scope, but shares words with in-scope content ("checking account") |
| q10 | ✅ | refused (account_specific) | none | ✅ | – | account-specific; the knowledge base cannot answer this |
| q11 | ✅ | refused (account_specific) | none | – | – | account-specific and contains an account number (PII must not be logged); $35 also matches the stale fee |
| q12 | ✅ | answered | high | ✅ | ✅ | answer is in the table's notes column |
| q13 | ✅ | answered | medium | ✅ | ✅ | tiered answer in an HTML page with boilerplate |
| q14 | ✅ | answered | low | ✅ | ✅ | paraphrase of "funds availability" |
| q15 | ✅ | answered | high | ✅ | ✅ | FAQ defers to the fee table; amount only in the table |
| q16 | ✅ | answered | medium | ✅ | ✅ | comparison across table rows plus a policy statement |
| q17 | ✅ | answered | high | ✅ | ✅ | answer is inside a markdown table in a policy doc |
| q18 | ✅ | refused (insufficient_context) | none | – | – | plausible banking question, shares "Premier" with lots of content, but savings rates are not in the corpus |
| q19 | ❌ | refused (insufficient_context) | none | ✅ | – | answer in two places (FAQ and policy) that agree |

## Failures

### q07: My payment bounced. Am I getting charged for that?

- trap: vocabulary mismatch ("bounced" vs "returned item" / "NSF")
- status: refused (insufficient_context), confidence none
- cited: none

```
The knowledge base doesn't appear to cover this. Closest passages are listed; escalate if none apply.
```

### q08: What are your current mortgage rates?

- trap: out of scope for rates, but the corpus does say how to route it
- status: refused (insufficient_context), confidence none
- cited: none

```
The knowledge base doesn't appear to cover this. Closest passages are listed; escalate if none apply.
```

### q19: Do I need to let you know before I travel abroad?

- trap: answer in two places (FAQ and policy) that agree
- status: refused (insufficient_context), confidence none
- cited: none

```
The knowledge base doesn't appear to cover this. Closest passages are listed; escalate if none apply.
```

