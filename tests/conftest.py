import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attest.chunking import chunk_documents  # noqa: E402
from attest.documents import load_corpus  # noqa: E402
from attest.pipeline import Attest  # noqa: E402

TODAY = date(2026, 10, 12)   # pin "today" so effective-date logic is deterministic


@pytest.fixture(scope="session")
def docs():
    return load_corpus(ROOT / "data" / "corpus", TODAY)


@pytest.fixture(scope="session")
def chunks(docs):
    return chunk_documents(docs)


@pytest.fixture
def system(chunks, tmp_path):
    return Attest(chunks, embedder=None, audit_log=tmp_path / "audit.jsonl")
