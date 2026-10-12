# **Attest-RAG**
*By Verc James*

Question in, cited answer out. Ask a support question and Attest answers from the knowledge base, shows the exact passages it used, and tells you how much to trust it. If the knowledge base can't back the answer, it refuses instead of guessing.

Built against a synthetic knowledge base for a fictional bank, MerchantBridge: 24 docs of policies, help-center FAQs and a fee schedule. Written for contact-center agents, where a confidently wrong fee costs real money.

---

## ⚙️ **Project Requirements**

- [Python](https://www.python.org/) <sub>*3.10+*</sub>
- [Anthropic API Key](https://console.anthropic.com) <sub>*only for `--claude`, needs API credits*</sub>

---

## 🧠 **Project Tech Stack**

- [rank-bm25](https://github.com/dorianbrown/rank_bm25) <sub>*keyword search*</sub>
- [fastembed](https://github.com/qdrant/fastembed) <sub>*semantic search, bge-small*</sub>
- [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) <sub>*Claude answers*</sub>
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) <sub>*HTML cleanup*</sub>
- [pytest](https://docs.pytest.org/)

---

## 🧪 **Project Commands**

Three modes. No flag is the baseline; each flag adds a layer.

| Mode | Install | Ask | Eval |
|---|---|---|---|
| Dev | `pip install -e ".[dev]"` | `python -m attest "What is the overdraft fee?"` | `python eval/run_eval.py` |
| Dense | `pip install -e ".[dev,dense]"` | `python -m attest "What is the overdraft fee?" --dense` | `python eval/run_eval.py --dense` |
| Claude | `pip install -e ".[dev,dense,claude]"` | `python -m attest "What is the overdraft fee?" --claude` | `python eval/run_eval.py --claude` |

- **Dev**: keyword search, extractive answers. No downloads, no key.
- **Dense**: adds semantic search ("bounced" finds "returned item"). Downloads a ~70MB model on first run.
- **Claude**: semantic search plus Claude-written answers, held to the same grounding checks.

```bash
python -m pytest                  # tests
python eval/run_eval.py -v        # -v shows the answer, or the withheld draft, for each failure
python -m attest "What is the overdraft fee?" --json   # full answer structure
```

---

## 🌍 **Project Environment**

Only needed for `--claude`.

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Console API key (`sk-ant-api03-...`) |
| `ATTEST_MODEL` | No | Model, default `claude-sonnet-5-5` |

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."    # macOS / Linux
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."    # PowerShell
```

> ⚠️ A Claude.ai subscription doesn't include API usage. A `401` means a bad key; a `400` usually means no credits.

---

## 🖼️ **Example Output**

`python -m attest "What is the overdraft fee?"`, trimmed:

```
  ANSWERED   confidence: medium
  · outdated sources were excluded: faq-overdraft

  • Overdraft fee, Premier Checking: $0.00 per item (Waived) [1]
  • Overdraft fee, Business Checking: $25.00 per item (Max 4 per business day) [2]
  • Overdraft fee, Essential Checking: $15.00 per item (Max 2 per business day) [3]
  • Overdraft fee, Plus Checking: $15.00 per item (Max 2 per business day) [4]

  Sources
  [1] Fee and Rate Schedule > Overdraft fee  fees.csv:358-438
  ...

  Excluded (outdated)
  · Overdraft FAQ > How much is an overdraft fee?  faq/faq-overdraft.html:44-112
      "Our overdraft fee is $35 per item, with a maximum of 3 fees per day."
      FAQ last reviewed 2024-11-02, before the current policy took effect
```

The old $35 fee is still sitting in the knowledge base. It never makes it into the answer.

---

## 🧭 **Key Design Decisions**

- **Every number has to be in its source.** If an answer states a figure that isn't in a passage it cites, the answer is withheld. The agent gets the passages instead.
- **Citations are exact.** Each one is a file and character range, not just a doc title.
- **Old versions get caught.** Same policy, older effective date? Excluded. FAQ reviewed before the current policy? Excluded, but still shown so the agent knows it's there.
- **Tables are cited raw, searched as sentences.** A CSV row is what the agent sees; a readable version of it is what search matches against.
- **Policies point, so we follow.** "See the Fee and Rate Schedule" pulls the actual fee rows, every tier.
- **Confidence comes from things we can measure**, never from the model grading itself.
- **Account questions get routed, not answered.** Account numbers are redacted before anything is logged or sent to a model.
- **Every answer is audited.** One JSONL line per question in `logs/`, enough to reconstruct what happened.

---

## 📄 **Dataset**

`data/corpus/`: 15 markdown policies, 8 HTML FAQ pages, `fees.csv`. `data/queries.yaml`: 19 questions, each with the facts a good answer needs and the trap it tests.

AI drafted it from a list of traps, then I went through it by hand. The rule was: only traps that happen on their own in a real knowledge base.

- An outdated policy and an FAQ nobody updated, both still saying $35
- Fees that only exist in the table, or only in its notes column
- Help-center pages wrapped in nav, cookie banners and footers
- CSV export junk: blank lines, a comment row, quoted commas
- Customers using different words than the docs ("bounced", "abroad")
- Out-of-scope questions that sound in-scope ("Premier savings APY")
- Account questions, one with an account number in it

A prompt-injection trap was suggested and cut as contrived. Mortgage rates went from "should refuse" to "should route to Partner Products" once I saw the system find the routing rule.

---

## 📊 **Results**

| Mode | Pass |
|---|---|
| Dev | 13/19 |
| Dense | 14/19 |
| Claude | 16/19 |

The stale $35 never showed up in any mode. Full breakdowns: `eval/report-dev.md`, `report-dense.md`, `report-claude.md`.

- Dense fixed the ambiguous wire question and correctly refused the savings APY question.
- Claude handles the questions that need comparing, like business vs personal wire fees.
- Claude's 3 misses happen before Claude runs: the coverage gate refuses them (see below).

---

## 📌 **What I Didn't Build**

- No reranker. Retrieval already finds the right source; the misses are after that.
- No query rewriting. Semantic search covers most of it without an extra LLM call.
- No multi-turn. Agents ask one question at a time.
- No persistence. The index builds in under a second.
- No LLM-as-judge. 19 answers can be read by a person.
- No HTTP endpoint. I spent that time on the audit log and redaction. `Attest.ask()` and the CLI are the interface.
- No UI, no auth. Out of scope per the brief.

---

## 🔭 **With More Time**

1. **Let the coverage gate trust semantic matches.** On "bounced" and "abroad", semantic search finds the right doc, then a word-overlap gate refuses because the words don't match. Loosening it trades safety for recall, so I'd measure that before shipping it.
2. **Ask instead of listing.** "How much is a wire?" has eight answers. The right move is to ask which one.
3. **Split retrieval confidence from answer confidence.** Right now confidence says "found good sources", not "used them well".
4. **Clean up two noisy signals.** The superseded-version notice fires on unrelated questions, and correctly excluding a stale FAQ still lowers confidence.
5. **Swap the account-question regex for a classifier.**

---

## 🤖 **How I Used AI**

Claude wrote most of the code and the dataset. I made the calls: what to build, what to cut, what counted as done. Then I ran it until it broke.

- I had the rules written first (`CLAUDE.md`): exact citations, no unsourced numbers, no raw queries in logs. Each has a test.
- The bugs came from running it, not reading it:
  - A "prefer policy over FAQ" weight buried the best answer. Rebuilt as a tie-breaker.
  - The CLI showed the same fee cited twice. Failing test first, then the fix.
  - Claude first scored 12/19. The `-v` drafts showed answers cut off mid-list. Raised the token limit, flagged truncation as its own failure, and it went to 16.
- I pushed back where it was wrong: a contrived injection trap, an over-engineered setup, and a confident "Claude is dropping citations" that turned out to be truncation.
