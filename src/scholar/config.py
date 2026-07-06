"""Central, typed configuration loaded once from the environment / .env.

Using ``pydantic-settings`` gives us validation + IDE autocomplete and keeps
every magic string in exactly one place.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Model serving ---
    llm_base_url: str = Field("http://localhost:8000/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field("not-needed", alias="LLM_API_KEY")
    # vLLM supports constrained `guided_json` decoding; hosted APIs (Groq, etc.)
    # reject that param, so turn it OFF for them and rely on JSON-mode + parsing.
    llm_guided_json: bool = Field(True, alias="LLM_GUIDED_JSON")

    model_heavy: str = Field("Qwen2.5-72B-Instruct", alias="MODEL_HEAVY")
    model_fast: str = Field("Mistral-Nemo-12B-Instruct", alias="MODEL_FAST")
    model_scribe: str = Field("Qwen2.5-32B-Instruct", alias="MODEL_SCRIBE")
    embed_model: str = Field("BAAI/bge-large-en-v1.5", alias="EMBED_MODEL")
    # Must be one of fastembed's supported cross-encoders. MiniLM-L-6 is the
    # lightest (~90MB); BAAI/bge-reranker-base is heavier but stronger.
    rerank_model: str = Field("Xenova/ms-marco-MiniLM-L-6-v2", alias="RERANK_MODEL")

    # --- Web-app system of record (accounts + application tracking) ---
    # SQLite by default = zero-setup local dev; point at Postgres for the real app.
    database_url: str = Field("sqlite:///./scholar.db", alias="DATABASE_URL")
    # Signing secret for auth tokens (override in production!). >=32 chars keeps
    # the HMAC key at a safe length for HS256.
    auth_secret: str = Field(
        "dev-insecure-change-me-please-set-AUTH_SECRET", alias="AUTH_SECRET"
    )

    # --- Knowledge base ---
    neo4j_uri: str = Field("bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field("neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field("please-change-me", alias="NEO4J_PASSWORD")
    qdrant_url: str = Field("http://localhost:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field("opportunities", alias="QDRANT_COLLECTION")

    # --- Scout tools ---
    tavily_api_key: str | None = Field(None, alias="TAVILY_API_KEY")
    searxng_url: str | None = Field(None, alias="SEARXNG_URL")
    openalex_mailto: str = Field("anon@example.com", alias="OPENALEX_MAILTO")
    # Optional Hugging Face token — faster, un-rate-limited fastembed model
    # downloads for the local embedder + cross-encoder reranker.
    hf_token: str | None = Field(None, alias="HF_TOKEN")

    # --- Observability ---
    langfuse_public_key: str | None = Field(None, alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str | None = Field(None, alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str | None = Field(None, alias="LANGFUSE_HOST")

    # --- Pipeline tuning ---
    max_reflection_loops: int = Field(3, alias="MAX_REFLECTION_LOOPS")
    match_score_threshold: int = Field(70, alias="MATCH_SCORE_THRESHOLD")
    top_k_opportunities: int = Field(5, alias="TOP_K_OPPORTUNITIES")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # --- Deep research (thorough, but paced to fit Groq's free tier) ---
    deep_breadth: int = Field(5, alias="DEEP_BREADTH")    # sub-questions per round
    deep_depth: int = Field(2, alias="DEEP_DEPTH")        # plan + reflect-and-expand rounds
    deep_max_pages: int = Field(10, alias="DEEP_MAX_PAGES")  # pages crawled/round
    stale_ttl_days: int = Field(21, alias="STALE_TTL_DAYS")

    # Freshness & lean retention. The daily job (opt-in) sweeps stale/expired opps
    # and PRUNES past-deadline ones from Neo4j+Qdrant so the KB stays small and
    # current. The bounded "surf for new" refresh is LLM-costly, so it only runs
    # in the daily job when MAINTENANCE_REFRESH_QUERY is set (protects free-tier).
    maintenance_daily: bool = Field(False, alias="MAINTENANCE_DAILY")
    expired_grace_days: int = Field(0, alias="EXPIRED_GRACE_DAYS")  # 0 = prune as soon as past
    maintenance_refresh_query: str | None = Field(None, alias="MAINTENANCE_REFRESH_QUERY")
    # How many watchlist keywords the daily job surfs (rotation, oldest first).
    # Each is a bounded deep pass (~18 LLM calls), so keep this small on free tiers.
    watchlist_daily_limit: int = Field(3, alias="WATCHLIST_DAILY_LIMIT")

    # Recursive crawling (crawl4ai DFS). 0 = off (single-page, laptop default).
    # >0 follows links that many levels deep from each seed URL — powerful but
    # heavy (needs crawl4ai + a headless browser), best on a GPU/desktop machine.
    deep_crawl_depth: int = Field(0, alias="DEEP_CRAWL_DEPTH")
    deep_crawl_max_pages: int = Field(8, alias="DEEP_CRAWL_MAX_PAGES")  # cap per seed

    # Critic: for opportunities missing a deadline, run this many bounded targeted
    # searches to try to fill it in. 0 = disable the Critic enrichment step.
    critic_max_enrich: int = Field(3, alias="CRITIC_MAX_ENRICH")

    # Rate control so a long deep run never crosses Groq's free limits:
    #   Groq free 70B ≈ 30 req/min, 12K tok/min, 100K tok/day. We pace UNDER 30 RPM
    #   and cap concurrency; the SDK's Retry-After handles the per-minute token cap.
    llm_max_concurrency: int = Field(2, alias="LLM_MAX_CONCURRENCY")
    llm_rpm_limit: int = Field(25, alias="LLM_RPM_LIMIT")   # stay safely below 30/min
    llm_max_retries: int = Field(6, alias="LLM_MAX_RETRIES")  # wait out token-window 429s

    # Per-role preferred provider (name from providers.json). Spreading roles
    # across FREE providers multiplies total free capacity: e.g. FAST/extraction
    # (frequent, big payloads) -> gemini's 1M-TPM budget, HEAVY -> groq's 70B.
    # Empty = pool order. Full failover to the rest of the pool is kept.
    llm_provider_heavy: str | None = Field(None, alias="LLM_PROVIDER_HEAVY")
    llm_provider_fast: str | None = Field(None, alias="LLM_PROVIDER_FAST")
    llm_provider_scribe: str | None = Field(None, alias="LLM_PROVIDER_SCRIBE")

    @property
    def embedding_dim(self) -> int:
        # Vector width must match the chosen bge model, or Qdrant upserts fail.
        name = self.embed_model.lower()
        if "large" in name:
            return 1024
        if "small" in name:
            return 384
        return 768  # bge-base and most others


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor — cached so we parse the env exactly once."""
    return Settings()
