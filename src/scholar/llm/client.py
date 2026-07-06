# """Async LLM gateway: one OpenAI-protocol client *per provider*, with failover.

# Public surface is unchanged for agents — ``complete`` and ``structured`` take a
# ``Role`` and return text / a validated Pydantic object. Underneath, every call
# walks the provider pool (Groq -> OpenRouter -> Cerebras -> …); on a rate-limit or
# outage it rolls to the next provider, which is what makes a $0 free-tier setup
# actually survive real usage.

# ``structured`` additionally degrades *within* a provider across request shapes:
# vLLM ``guided_json`` -> generic JSON-mode -> prompt-only, validating whatever
# comes back (with a last-resort parse of the first embedded JSON object).
# """
# from __future__ import annotations

# import asyncio
# import json
# import time
# from functools import lru_cache
# from typing import Awaitable, Callable, TypeVar

# from openai import (
#     APIConnectionError,
#     APITimeoutError,
#     AsyncOpenAI,
#     BadRequestError,
#     InternalServerError,
#     RateLimitError,
# )
# from pydantic import BaseModel, ValidationError
# from tenacity import retry, stop_after_attempt, wait_exponential

# from ..observability import get_logger
# from .providers import ProviderConfig, load_providers
# from .router import Role, temperature

# log = get_logger("llm")
# T = TypeVar("T", bound=BaseModel)
# R = TypeVar("R")

# # Transient/over-capacity errors that should roll to the next provider.
# _FAILOVER_ERRORS = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)


# def _extract_json(text: str) -> str:
#     """Pull the first balanced JSON object out of a model response."""
#     start = text.find("{")
#     if start == -1:
#         raise ValueError("no JSON object found in model output")
#     depth = 0
#     for i, ch in enumerate(text[start:], start):
#         if ch == "{":
#             depth += 1
#         elif ch == "}":
#             depth -= 1
#             if depth == 0:
#                 return text[start : i + 1]
#     raise ValueError("unbalanced JSON in model output")


# class _RateLimiter:
#     """Proactive request pacer: guarantees a minimum gap between request *starts*
#     so we stay under a target requests-per-minute (Groq free tier = 30 RPM)."""

#     def __init__(self, rpm: int) -> None:
#         self._interval = 60.0 / max(rpm, 1)
#         self._lock = asyncio.Lock()
#         self._next = 0.0

#     async def acquire(self) -> None:
#         async with self._lock:
#             now = time.monotonic()
#             wait = self._next - now
#             if wait > 0:
#                 await asyncio.sleep(wait)
#                 now = time.monotonic()
#             self._next = now + self._interval


# class LLMClient:
#     def __init__(self) -> None:
#         from ..config import get_settings

#         s = get_settings()
#         self._providers = load_providers()
#         self._clients = {
#             # max_retries lets the SDK patiently wait out per-minute token (429)
#             # windows via Retry-After instead of failing the run.
#             p.name: AsyncOpenAI(base_url=p.base_url, api_key=p.api_key, max_retries=s.llm_max_retries)
#             for p in self._providers
#         }
#         # Cap in-flight requests + pace request starts so a long deep run never
#         # crosses the free-tier rate limits.
#         self._sem = asyncio.Semaphore(s.llm_max_concurrency)
#         self._limiter = _RateLimiter(s.llm_rpm_limit)

#     @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=8))
#     async def _with_failover(
#         self, call: Callable[[ProviderConfig, AsyncOpenAI], Awaitable[R]]
#     ) -> R:
#         last: Exception | None = None
#         for provider in self._providers:
#             try:
#                 await self._limiter.acquire()  # pace under the RPM ceiling
#                 async with self._sem:
#                     return await call(provider, self._clients[provider.name])
#             except (*_FAILOVER_ERRORS, BadRequestError) as exc:
#                 last = exc
#                 log.warning("provider_failover", provider=provider.name, error=str(exc))
#                 continue
#         raise last or RuntimeError("no providers configured")

#     async def complete(
#         self, role: Role, system: str, user: str, max_tokens: int = 1024
#     ) -> str:
#         async def call(provider: ProviderConfig, client: AsyncOpenAI) -> str:
#             resp = await client.chat.completions.create(
#                 model=provider.model_for(role),
#                 temperature=temperature(role),
#                 max_tokens=max_tokens,
#                 messages=[
#                     {"role": "system", "content": system},
#                     {"role": "user", "content": user},
#                 ],
#             )
#             return resp.choices[0].message.content or ""

#         return await self._with_failover(call)

#     async def structured(
#         self,
#         role: Role,
#         system: str,
#         user: str,
#         schema: type[T],
#         max_tokens: int = 2048,
#     ) -> T:
#         """Return a validated ``schema`` instance, with per-provider degradation."""
#         schema_json = schema.model_json_schema()

#         async def call(provider: ProviderConfig, client: AsyncOpenAI) -> T:
#             base = dict(
#                 model=provider.model_for(role),
#                 temperature=temperature(role),
#                 max_tokens=max_tokens,
#                 messages=[
#                     {
#                         "role": "system",
#                         "content": (
#                             f"{system}\n\nRespond with ONLY a JSON object matching this schema:\n"
#                             f"{json.dumps(schema_json)}"
#                         ),
#                     },
#                     {"role": "user", "content": user},
#                 ],
#             )
#             variants: list[dict] = []
#             if provider.guided_json:
#                 variants.append(
#                     {**base, "response_format": {"type": "json_object"}, "extra_body": {"guided_json": schema_json}}
#                 )
#             variants.append({**base, "response_format": {"type": "json_object"}})
#             variants.append(base)

#             last: Exception | None = None
#             for kwargs in variants:
#                 try:
#                     resp = await client.chat.completions.create(**kwargs)
#                 except BadRequestError as exc:
#                     last = exc
#                     continue  # try a simpler request shape on this same provider
#                 raw = resp.choices[0].message.content or ""
#                 try:
#                     return schema.model_validate_json(raw)
#                 except ValidationError:
#                     return schema.model_validate_json(_extract_json(raw))
#             raise last or RuntimeError("structured() exhausted all request variants")

#         return await self._with_failover(call)


# @lru_cache
# def get_llm() -> LLMClient:
#     return LLMClient()




"""Async LLM gateway: one OpenAI-protocol client *per provider*, with failover.

Public surface is unchanged for agents — ``complete`` and ``structured`` take a
``Role`` and return text / a validated Pydantic object. Underneath, every call
walks the provider pool (Groq -> OpenRouter -> Cerebras -> …); on a rate-limit or
outage it rolls to the next provider, which is what makes a $0 free-tier setup
actually survive real usage.

``structured`` additionally degrades *within* a provider across request shapes:
vLLM ``guided_json`` -> generic JSON-mode -> prompt-only, validating whatever
comes back (with a last-resort parse of the first embedded JSON object).
"""
from __future__ import annotations

import asyncio
import json
import time
from functools import lru_cache
from typing import Awaitable, Callable, TypeVar

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential

from ..observability import get_logger
from .providers import ProviderConfig, load_providers
from .router import Role, temperature

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")

# Transient/over-capacity errors that should roll to the next provider.
_FAILOVER_ERRORS = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError, AuthenticationError)


def _extract_json(text: str) -> str:
    """Pull the first balanced JSON object out of a model response."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in model output")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced JSON in model output")


class _RateLimiter:
    """Token-bucket pacer: enforces both a minimum inter-request gap (RPM ceiling)
    and a short-window burst cap so back-to-back asyncio.gather calls never fire
    faster than Groq's burst allowance.

    Two independent controls:
      rpm        — steady-state ceiling (e.g. 28 for Groq free tier, leaving 2
                   RPM of headroom for occasional manual calls).
      burst_cap  — max requests allowed inside any 10-second window. Groq's burst
                   window is not documented, but empirically ~6 in 10 s is safe.
    """

    def __init__(self, rpm: int, burst_cap: int = 6, burst_window: float = 10.0) -> None:
        self._interval = 60.0 / max(rpm, 1)
        self._burst_cap = burst_cap
        self._burst_window = burst_window
        self._lock = asyncio.Lock()
        self._next = 0.0
        # Sliding window: store timestamps of the last N completions.
        self._recent: list[float] = []

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()

            # --- burst guard ---
            # Evict timestamps outside the current window.
            cutoff = now - self._burst_window
            self._recent = [t for t in self._recent if t > cutoff]
            if len(self._recent) >= self._burst_cap:
                # Wait until the oldest request in the window falls out.
                wait = self._recent[0] + self._burst_window - now
                if wait > 0:
                    log.debug("burst_cap_wait", wait_s=round(wait, 2))
                    await asyncio.sleep(wait)
                    now = time.monotonic()
                    cutoff = now - self._burst_window
                    self._recent = [t for t in self._recent if t > cutoff]

            # --- steady-state RPM gap ---
            wait = self._next - now
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()

            self._next = now + self._interval
            self._recent.append(now)


class LLMClient:
    def __init__(self) -> None:
        from ..config import get_settings

        s = get_settings()
        self._providers = load_providers()
        self._clients = {
            # max_retries lets the SDK patiently wait out per-minute token (429)
            # windows via Retry-After instead of failing the run.
            p.name: AsyncOpenAI(base_url=p.base_url, api_key=p.api_key, max_retries=s.llm_max_retries)
            for p in self._providers
        }
        # Cap in-flight requests + pace request starts so a long deep run never
        # crosses the free-tier rate limits.
        # llm_max_concurrency should be <= burst_cap so the semaphore and burst
        # guard stay in sync (default: 4 concurrent, 6 per 10 s burst window).
        self._sem = asyncio.Semaphore(s.llm_max_concurrency)
        self._limiter = _RateLimiter(
            rpm=s.llm_rpm_limit,
            burst_cap=getattr(s, "llm_burst_cap", 6),
            burst_window=getattr(s, "llm_burst_window", 10.0),
        )

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=8))
    async def _with_failover(
        self, call: Callable[[ProviderConfig, AsyncOpenAI], Awaitable[R]], role: Role
    ) -> R:
        from .providers import providers_for

        last: Exception | None = None
        for provider in providers_for(role):
            try:
                await self._limiter.acquire()  # pace under the RPM ceiling
                async with self._sem:
                    return await call(provider, self._clients[provider.name])
            except (*_FAILOVER_ERRORS, BadRequestError, ValidationError) as exc:
                last = exc
                log.warning("provider_failover", provider=provider.name, error=str(exc))
                continue
        raise last or RuntimeError("no providers configured")

    async def complete(
        self, role: Role, system: str, user: str, max_tokens: int = 1024
    ) -> str:
        async def call(provider: ProviderConfig, client: AsyncOpenAI) -> str:
            resp = await client.chat.completions.create(
                model=provider.model_for(role),
                temperature=temperature(role),
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content or ""

        return await self._with_failover(call, role)

    async def structured(
        self,
        role: Role,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 2048,
    ) -> T:
        """Return a validated ``schema`` instance, with per-provider degradation."""
        schema_json = schema.model_json_schema()

        async def call(provider: ProviderConfig, client: AsyncOpenAI) -> T:
            base = dict(
                model=provider.model_for(role),
                temperature=temperature(role),
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{system}\n\nRespond with ONLY a JSON object matching this schema:\n"
                            f"{json.dumps(schema_json)}"
                        ),
                    },
                    {"role": "user", "content": user},
                ],
            )
            variants: list[dict] = []
            if provider.guided_json:
                variants.append(
                    {**base, "response_format": {"type": "json_object"}, "extra_body": {"guided_json": schema_json}}
                )
            variants.append({**base, "response_format": {"type": "json_object"}})
            variants.append(base)

            last: Exception | None = None
            for kwargs in variants:
                try:
                    resp = await client.chat.completions.create(**kwargs)
                except BadRequestError as exc:
                    last = exc
                    continue  # try a simpler request shape on this same provider
                raw = resp.choices[0].message.content or ""
                # Validate strictly, then fall back to extracting the first JSON
                # object. If both fail, don't give up — try the next request
                # shape (and ultimately the next provider) instead of crashing.
                try:
                    return schema.model_validate_json(raw)
                except ValidationError:
                    pass
                try:
                    return schema.model_validate_json(_extract_json(raw))
                except (ValidationError, ValueError) as exc:
                    last = exc
                    log.warning(
                        "structured_validation_failed",
                        provider=provider.name,
                        schema=schema.__name__,
                    )
                    continue
            raise last or RuntimeError("structured() exhausted all request variants")

        return await self._with_failover(call, role)


@lru_cache
def get_llm() -> LLMClient:
    return LLMClient()