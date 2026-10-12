import numpy as np

from attest.retrieval import Retriever, rrf, tokenize


def test_superseded_versions_never_come_back(chunks):
    res = Retriever(chunks).search("overdraft fee $35 per item 3 per day")
    assert all(h.chunk.doc_id != "overdraft-policy-2025" for h in res.hits)
    assert "overdraft-policy-2025" in res.suppressed


def test_faq_penalty_breaks_ties_but_does_not_bury_a_clear_winner():
    faq, policy, a, b, c = 0, 1, 2, 3, 4
    penalty = [2, 0, 0, 0, 0]
    # FAQ ranked first, policy fourth: FAQ still wins...
    s = rrf([[faq, a, b, c, policy]], penalty)
    assert s[faq] > s[policy]
    # ...but loses a near-tie to policy.
    s = rrf([[faq, policy]], penalty)
    assert s[policy] > s[faq]


def test_coverage_separates_in_scope_from_out_of_scope(chunks):
    r = Retriever(chunks)
    assert r.search("What is the cutoff for a domestic wire?").coverage == 1.0
    oos = r.search("Can I buy bitcoin with my checking account?")
    assert oos.coverage < 0.6 and "bitcoin" in oos.missing_terms


def test_tokenizer_normalizes_money():
    assert tokenize("$25.00 and 5,000 or 3%") == ["25", "5000", "3%"]


class BagOfWordsEmbedder:
    """Stands in for the real model so hybrid fusion is tested without downloads."""

    def __init__(self, vocab):
        self.vocab = {t: i for i, t in enumerate(sorted(vocab))}

    def embed(self, texts):
        out = np.zeros((len(texts), len(self.vocab)), dtype=np.float32)
        for row, t in enumerate(texts):
            for tok in tokenize(t):
                if tok in self.vocab:
                    out[row, self.vocab[tok]] += 1
        return out + 1e-6


def test_hybrid_mode_fuses_both_rankings(chunks):
    vocab = {t for c in chunks for t in tokenize(c.index_text)}
    r = Retriever(chunks, BagOfWordsEmbedder(vocab))
    assert r.mode == "hybrid"
    res = r.search("international wire cutoff time")
    assert res.mode == "hybrid"
    assert res.hits[0].chunk.doc_id == "wire-transfers-policy"
    assert res.hits[0].bm25_rank is not None and res.hits[0].dense_rank is not None
