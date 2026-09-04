"""Shared fixtures. No test may touch the network (docs/DESIGN.md §17)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture
def settings(tmp_path):
    from ideate.config import Settings

    return Settings(
        provider="mock",
        index_dir=str(tmp_path / "index"),
        memory_path=str(tmp_path / "memory.jsonl"),
        runs_dir=str(tmp_path / "runs"),
        receipts_dir=str(tmp_path / "receipts"),
        meta_path=str(tmp_path / "meta.jsonl"),
    )


@pytest.fixture
def mock_llm():
    from ideate.llm.mock import MockLLM

    return MockLLM(seed=0)


@pytest.fixture(scope="session")
def bundled_documents():
    from ideate.config import bundled_corpus_dir
    from ideate.knowledge.loaders import load_corpus

    return load_corpus([bundled_corpus_dir()])


@pytest.fixture(scope="session")
def kb(bundled_documents):
    from ideate.knowledge.retriever import KnowledgeBase

    return KnowledgeBase.build(bundled_documents)


@pytest.fixture
def cli_env(tmp_path):
    """Environment for subprocess CLI tests: mock provider, tmp state dirs, src on PYTHONPATH."""
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC),
        "IDEATE_PROVIDER": "mock",
        "IDEATE_INDEX_DIR": str(tmp_path / "index"),
        "IDEATE_MEMORY_PATH": str(tmp_path / "memory.jsonl"),
        "IDEATE_RUNS_DIR": str(tmp_path / "runs"),
        "IDEATE_RECEIPTS_DIR": str(tmp_path / "receipts"),
        "IDEATE_META_PATH": str(tmp_path / "meta.jsonl"),
    }
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return env
