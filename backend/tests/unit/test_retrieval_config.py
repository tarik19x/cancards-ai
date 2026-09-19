"""The production retrieval defaults are a decision backed by measurements; pin them."""

from app.config import Settings


def test_the_default_is_the_best_measured_method(monkeypatch):
    # Hybrid + rerank on the card-name chunks: recall@8 0.958 on the 100 held-out
    # questions, against 0.321 for dense search on the original chunks.
    monkeypatch.delenv("RETRIEVAL_MODE", raising=False)
    monkeypatch.delenv("PINECONE_NAMESPACE", raising=False)
    settings = Settings(_env_file=None)
    assert settings.retrieval_mode == "hybrid_rerank"
    assert settings.pinecone_namespace == "headers-v1"


def test_the_old_behaviour_is_one_setting_away(monkeypatch):
    # Point 4 re-measures the "before" state this way; the weekly eval job is pinned to it.
    monkeypatch.setenv("RETRIEVAL_MODE", "dense")
    monkeypatch.setenv("PINECONE_NAMESPACE", "")
    settings = Settings(_env_file=None)
    assert settings.retrieval_mode == "dense"
    assert settings.pinecone_namespace == ""
