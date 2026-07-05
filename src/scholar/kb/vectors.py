# """Qdrant vector store + hybrid (dense + BM25) retrieval.

# Pure dense search misses exact terms ("NSF GRFP", a specific lab name); pure
# lexical misses paraphrase. Hybrid + rerank is the current best-practice recipe,
# so we fuse both with Reciprocal Rank Fusion before the cross-encoder rerank.
# """
# from __future__ import annotations

# from functools import lru_cache

# from qdrant_client import QdrantClient
# from qdrant_client.http import models as qm
# from rank_bm25 import BM25Okapi

# from ..config import get_settings
# from ..observability import get_logger
# from ..schemas import Opportunity
# from .embeddings import get_embedder

# log = get_logger("vectors")


# def _rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
#     """Reciprocal Rank Fusion over several ranked id lists."""
#     scores: dict[str, float] = {}
#     for ranking in rankings:
#         for rank, doc_id in enumerate(ranking):
#             scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
#     return scores


# class VectorStore:
#     def __init__(self) -> None:
#         s = get_settings()
#         self._client = QdrantClient(url=s.qdrant_url)
#         self._collection = s.qdrant_collection
#         self._embedder = get_embedder()

#     def ensure_collection(self) -> None:
#         existing = {c.name for c in self._client.get_collections().collections}
#         if self._collection not in existing:
#             self._client.create_collection(
#                 collection_name=self._collection,
#                 vectors_config=qm.VectorParams(
#                     size=self._embedder.dim, distance=qm.Distance.COSINE
#                 ),
#             )
#             log.info("created_qdrant_collection", name=self._collection)

#     def upsert(self, opportunities: list[Opportunity]) -> None:
#         if not opportunities:
#             return
#         self.ensure_collection()
#         vectors = self._embedder.embed([o.embedding_text() for o in opportunities])
#         points = [
#             qm.PointStruct(
#                 id=_uuid_from(o.id),
#                 vector=v,
#                 payload={"opp_id": o.id, "text": o.embedding_text(), **o.model_dump()},
#             )
#             for o, v in zip(opportunities, vectors)
#         ]
#         self._client.upsert(collection_name=self._collection, points=points)
#         log.info("upserted_vectors", n=len(points))

#     def fetch_opportunities(self, query: str, top_k: int = 30) -> list[Opportunity]:
#         """Reconstruct full Opportunity objects from the vector DB (fast mode).

#         Used when there's no live Scout run — we pull the best existing candidates
#         straight from Qdrant payloads so the Matchmaker has something to score.
#         """
#         self.ensure_collection()
#         qvec = self._embedder.embed_one(query)
#         hits = self._client.search(
#             collection_name=self._collection, query_vector=qvec, limit=top_k
#         )
#         out: list[Opportunity] = []
#         for h in hits:
#             payload = dict(h.payload or {})
#             payload.pop("opp_id", None)
#             payload.pop("text", None)
#             try:
#                 out.append(Opportunity.model_validate(payload))
#             except Exception:  # noqa: BLE001 - skip malformed rows
#                 continue
#         return out

#     def hybrid_search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
#         """Return ``(opp_id, fused_score)`` from dense + BM25, then rerank."""
#         self.ensure_collection()
#         qvec = self._embedder.embed_one(query)

#         dense = self._client.search(
#             collection_name=self._collection, query_vector=qvec, limit=top_k
#         )
#         dense_ids = [h.payload["opp_id"] for h in dense]
#         corpus = [(h.payload["opp_id"], h.payload.get("text", "")) for h in dense]

#         # BM25 over the same candidate pool (cheap, no separate sparse index).
#         if corpus:
#             bm25 = BM25Okapi([t.split() for _, t in corpus])
#             bm_scores = bm25.get_scores(query.split())
#             bm_ranked = [
#                 cid
#                 for cid, _ in sorted(
#                     zip([c for c, _ in corpus], bm_scores),
#                     key=lambda x: x[1],
#                     reverse=True,
#                 )
#             ]
#         else:
#             bm_ranked = []

#         fused = _rrf([dense_ids, bm_ranked])

#         # Cross-encoder rerank for final precision. Best-effort: if the reranker
#         # model can't load, fall back to the dense+BM25 fusion rather than failing.
#         if corpus:
#             try:
#                 texts = [t for _, t in corpus]
#                 rr = self._embedder.rerank(query, texts)
#                 for (cid, _), score in zip(corpus, rr):
#                     fused[cid] = fused.get(cid, 0.0) + float(score)
#             except Exception as exc:  # noqa: BLE001
#                 log.warning("rerank_skipped", error=str(exc))

#         return sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]


# def _uuid_from(short_id: str) -> str:
#     """Qdrant needs a UUID/int id; derive a stable UUID from our short hash."""
#     import uuid

#     return str(uuid.uuid5(uuid.NAMESPACE_URL, short_id))


# @lru_cache
# def get_vectors() -> VectorStore:
#     return VectorStore()


"""Qdrant vector store + hybrid (dense + BM25) retrieval.

Pure dense search misses exact terms ("NSF GRFP", a specific lab name); pure
lexical misses paraphrase. Hybrid + rerank is the current best-practice recipe,
so we fuse both with Reciprocal Rank Fusion before the cross-encoder rerank.
"""
from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from rank_bm25 import BM25Okapi

from ..config import get_settings
from ..observability import get_logger
from ..schemas import Opportunity
from .embeddings import get_embedder

log = get_logger("vectors")


def _rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion over several ranked id lists."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return scores


class VectorStore:
    def __init__(self) -> None:
        s = get_settings()
        self._client = QdrantClient(url=s.qdrant_url)
        self._collection = s.qdrant_collection
        self._embedder = get_embedder()

    def ensure_collection(self) -> None:
        existing = {c.name for c in self._client.get_collections().collections}
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=qm.VectorParams(
                    size=self._embedder.dim, distance=qm.Distance.COSINE
                ),
            )
            log.info("created_qdrant_collection", name=self._collection)

    def upsert(self, opportunities: list[Opportunity]) -> None:
        if not opportunities:
            return
        self.ensure_collection()
        vectors = self._embedder.embed([o.embedding_text() for o in opportunities])
        points = [
            qm.PointStruct(
                id=_uuid_from(o.id),
                vector=v,
                payload={"opp_id": o.id, "text": o.embedding_text(), **o.model_dump()},
            )
            for o, v in zip(opportunities, vectors)
        ]
        self._client.upsert(collection_name=self._collection, points=points)
        log.info("upserted_vectors", n=len(points))

    def count(self) -> int:
        """Number of opportunities currently in the vector store (KB size)."""
        try:
            self.ensure_collection()
            return self._client.count(collection_name=self._collection).count
        except Exception as exc:  # noqa: BLE001
            log.warning("count_failed", error=str(exc))
            return 0

    def delete_by_ids(self, opp_ids: list[str]) -> int:
        """Remove opportunities from the vector store by content-addressed id
        (used by the freshness sweep to prune expired opportunities)."""
        if not opp_ids:
            return 0
        self.ensure_collection()
        self._client.delete(
            collection_name=self._collection,
            points_selector=[_uuid_from(i) for i in opp_ids],
        )
        log.info("deleted_vectors", n=len(opp_ids))
        return len(opp_ids)

    def fetch_by_id(self, opp_id: str) -> Opportunity | None:
        """Retrieve a single Opportunity by its content-addressed id, or None."""
        self.ensure_collection()
        try:
            points = self._client.retrieve(
                collection_name=self._collection,
                ids=[_uuid_from(opp_id)],
                with_payload=True,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("fetch_by_id_failed", opp_id=opp_id, error=str(exc))
            return None
        if not points:
            return None
        payload = dict(points[0].payload or {})
        payload.pop("opp_id", None)
        payload.pop("text", None)
        try:
            return Opportunity.model_validate(payload)
        except Exception:  # noqa: BLE001
            return None

    def fetch_opportunities(self, query: str, top_k: int = 30) -> list[Opportunity]:
        """Reconstruct full Opportunity objects from the vector DB (fast mode)."""
        self.ensure_collection()
        qvec = self._embedder.embed_one(query)
        
        # CHANGED: Migrated from .search() to .query_points()
        response = self._client.query_points(
            collection_name=self._collection, 
            query=qvec, 
            limit=top_k
        )
        hits = response.points
        
        out: list[Opportunity] = []
        for h in hits:
            payload = dict(h.payload or {})
            payload.pop("opp_id", None)
            payload.pop("text", None)
            try:
                out.append(Opportunity.model_validate(payload))
            except Exception:  # noqa: BLE001 - skip malformed rows
                continue
        return out

    def hybrid_search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        """Return ``(opp_id, fused_score)`` from dense + BM25, then rerank."""
        self.ensure_collection()
        qvec = self._embedder.embed_one(query)

        # CHANGED: Migrated from .search() to .query_points()
        response = self._client.query_points(
            collection_name=self._collection, 
            query=qvec, 
            limit=top_k
        )
        # Keep only points that actually carry a payload with our opp_id.
        dense_pairs = [
            (p["opp_id"], p.get("text", ""))
            for h in response.points
            if (p := h.payload) and "opp_id" in p
        ]
        dense_ids = [oid for oid, _ in dense_pairs]
        corpus = dense_pairs

        # BM25 over the same candidate pool (cheap, no separate sparse index).
        if corpus:
            bm25 = BM25Okapi([t.split() for _, t in corpus])
            bm_scores = bm25.get_scores(query.split())
            bm_ranked = [
                cid
                for cid, _ in sorted(
                    zip([c for c, _ in corpus], bm_scores),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ]
        else:
            bm_ranked = []

        fused = _rrf([dense_ids, bm_ranked])

        # Cross-encoder rerank for final precision.
        if corpus:
            try:
                texts = [t for _, t in corpus]
                rr = self._embedder.rerank(query, texts)
                for (cid, _), score in zip(corpus, rr):
                    fused[cid] = fused.get(cid, 0.0) + float(score)
            except Exception as exc:  # noqa: BLE001
                log.warning("rerank_skipped", error=str(exc))

        return sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]


def _uuid_from(short_id: str) -> str:
    """Qdrant needs a UUID/int id; derive a stable UUID from our short hash."""
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, short_id))


@lru_cache
def get_vectors() -> VectorStore:
    return VectorStore()