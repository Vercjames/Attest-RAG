# Eval report

Retrieval: **hybrid** · generator: **extractive** · 19 queries

## Summary

| metric | result |
|---|---|
| end-to-end pass | 14/19 |
| retrieval@5 (expected doc retrieved) | 15/16 |
| required facts present (answered queries) | 10/12 |
| no stale/wrong fact | 19/19 |
| correct refuse/answer behavior | 16/19 |
| confidence on passing answers: high / medium / low | 3 / 5 / 2 |
| confidence on failing answers: high / medium / low | 0 / 2 / 0 |

## Per query

| id | pass | status | conf | retr@5 | facts | trap |
|---|---|---|---|---|---|---|
| q01 | ✅ | answered | medium | ✅ | ✅ | none (baseline direct lookup) |
| q02 | ✅ | answered | medium | ✅ | ✅ | answer lives only in the fee table |
| q03 | ✅ | answered | medium | ✅ | ✅ | superseded policy and a stale FAQ both say $35; current fee is $15 and varies by tier |
| q04 | ❌ | answered | medium | ✅ | ❌ | FAQ says "about 10 days", policy says provisional credit within 10 business days and investigation up to 45/90 days |
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
| q16 | ❌ | answered | medium | ✅ | ❌ | comparison across table rows plus a policy statement |
| q17 | ✅ | answered | high | ✅ | ✅ | answer is inside a markdown table in a policy doc |
| q18 | ✅ | refused (insufficient_context) | none | – | – | plausible banking question, shares "Premier" with lots of content, but savings rates are not in the corpus |
| q19 | ❌ | refused (insufficient_context) | none | ✅ | – | answer in two places (FAQ and policy) that agree |

## Failures

### q04: How long does a card dispute take?

- trap: FAQ says "about 10 days", policy says provisional credit within 10 business days and investigation up to 45/90 days
- status: answered (answered), confidence medium
- cited: card-disputes-policy#1, card-disputes-policy#3, lost-stolen-card-policy#4
- note: Excluded faq-disputes#2: FAQ last reviewed 2025-02-14, before the current policy took effect

```
Disputes can be filed in online banking, in the mobile app, or by calling Card Services. [card-disputes-policy#1]
For transactions initiated outside the United States, point-of-sale transactions, and transactions on accounts open less than 30 days, the investigation may take up to 90 days. [card-disputes-policy#3]
International delivery typically takes 3 to 5 business days. [lost-stolen-card-policy#4]
```

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

### q16: Do business accounts pay the same wire fees as personal accounts?

- trap: comparison across table rows plus a policy statement
- status: answered (answered), confidence medium
- cited: business-checking-overview#2, fees#WDI-ALL, overdraft-policy-2026#2

```
Business fees for wires, overdrafts, and returned items differ from personal checking fees. [business-checking-overview#2]
When we pay an item that overdraws your account, we charge an overdraft fee. [overdraft-policy-2026#2]
Incoming domestic wire:
- All personal accounts: $15.00 per transfer (Waived for Premier Checking) [fees#WDI-ALL]
```

### q19: Do I need to let you know before I travel abroad?

- trap: answer in two places (FAQ and policy) that agree
- status: refused (insufficient_context), confidence none
- cited: none

```
The knowledge base doesn't appear to cover this. Closest passages are listed; escalate if none apply.
```

