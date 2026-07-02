"""Local, open-source embeddings + cross-encoder reranking.

We use ``fastembed`` (ONNX runtime) so we get ``bge-large-en-v1.5`` quality with
no torch/CUDA dependency in the orchestrator container — the heavy GPU work
stays on the Brain VMs, while the Hands container does cheap CPU embedding.

The reranker is the trending second stage of modern retrieval: dense recall is
fuzzy, so a cross-encoder re-scores the top candidates for precision.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import get_settings
from ..observability import get_logger

log = get_logger("embeddings")


class Embedder:
    def __init__(self) -> None:
        s = get_settings()
        self._dim = s.embedding_dim
        self._text_model = None
        self._reranker = None
        self._model_name = s.embed_model
        self._rerank_name = s.rerank_model

    # Lazy init keeps import time + test startup fast.
    def _ensure_text(self):
        if self._text_model is None:
            from fastembed import TextEmbedding

            self._text_model = TextEmbedding(model_name=self._model_name)
        return self._text_model

    def _ensure_reranker(self):
        if self._reranker is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._reranker = TextCrossEncoder(model_name=self._rerank_name)
        return self._reranker

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_text()
        return [vec.tolist() for vec in model.embed(texts)]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Cross-encoder relevance scores aligned with ``documents`` order."""
        reranker = self._ensure_reranker()
        return list(reranker.rerank(query, documents))


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()
