"""call_llm() / call_llm_json() — 3-tier fallback: Groq (key rotation) ->
OpenRouter (key rotation) -> Ollama (auto-started, local). Raw httpx, no
LangChain. Ported from reference/backend/services/llm.py — same retry/
fallback/schema-correction behaviour, remapped onto this service's config.py
names. Ollama isn't configured in this environment's .env; that tier is
reached only if both cloud tiers are exhausted and simply fails fast if
`ollama` isn't installed (no hard dependency on it being present).
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from config import (
    ACTIVE_BASE_URL,
    GROQ_API_KEYS,
    GROQ_BASE_URL,
    GROQ_TO_OLLAMA_MODEL,
    GROQ_TO_OR_MODEL,
    LLM_DEBUG_LOGGING,
    LLM_PROVIDER,
    OLLAMA_BASE_URL,
    OLLAMA_PRIMARY_MODEL,
    OPENROUTER_BASE_URL,
    OR_API_KEYS,
    OR_PRIMARY_MODEL,
)

logger = logging.getLogger("capa_ai.llm")
logger.setLevel(logging.DEBUG if LLM_DEBUG_LOGGING else logging.INFO)

T = TypeVar("T", bound=BaseModel)

# Errors worth rotating to the next key/tier for, not just 429: a bad/expired
# key (401/403), a provider outage (5xx), or a network blip (timeout/connect
# error) all leave other fallback tiers sitting unused if we only retry on 429.
_RETRYABLE_NETWORK_EXCS = (httpx.TimeoutException, httpx.ConnectError, httpx.TransportError)


def _is_retryable_status(status_code: int) -> bool:
    # 401/403: each key is a distinct credential — one revoked/expired key
    # shouldn't block trying the next. 413: Groq returns it when
    # prompt_tokens + max_tokens exceeds that key's remaining per-minute
    # token budget — a quota problem, not a malformed-request problem.
    return status_code == 429 or status_code >= 500 or status_code in (401, 403, 413)


class TruncatedResponseError(Exception):
    """Raised when the provider cut the response off at max_tokens
    (finish_reason == 'length'). Never valid JSON, so retrying with the
    same max_tokens just repeats the failure."""

    def __init__(self, content: str):
        self.content = content
        super().__init__("LLM response truncated at max_tokens (finish_reason=length)")


def _extract_content(resp: httpx.Response) -> str:
    choice = resp.json()["choices"][0]
    content = choice["message"]["content"]
    if LLM_DEBUG_LOGGING:
        logger.debug("  full response: %s", content[:3000])
    if choice.get("finish_reason") == "length":
        raise TruncatedResponseError(content)
    return content


# Cursor-based key rotation: advances on failure, never resets backward in a process run.
_groq_key_cursor: int = 0
_or_key_cursor: int = 0
_key_cursor_lock = asyncio.Lock()
_ollama_startup_lock = asyncio.Lock()


async def _ensure_ollama_running() -> None:
    """Check if Ollama is up; start it automatically if not. Guarded by a
    lock so concurrent callers that all hit "no cloud option left" at once
    wait on a single spawn instead of each launching their own process."""
    async with _ollama_startup_lock:
        health_url = OLLAMA_BASE_URL.replace("/v1/chat/completions", "")
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(health_url)
                if r.status_code < 500:
                    return
        except Exception:
            pass

        logger.info("Ollama not running — starting ollama serve...")
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            subprocess.Popen(["ollama", "serve"], **kwargs)
        except FileNotFoundError as exc:
            raise RuntimeError(
                "[llm] All cloud LLM tiers exhausted and Ollama is not installed locally."
            ) from exc

        for _ in range(30):
            await asyncio.sleep(1)
            try:
                async with httpx.AsyncClient(timeout=2.0) as c:
                    r = await c.get(health_url)
                    if r.status_code < 500:
                        logger.info("Ollama started.")
                        return
            except Exception:
                pass
        raise RuntimeError("[llm] Ollama did not start within 30 seconds.")


async def call_llm(
    messages: list[dict], model: str, temperature: float = 0.3, max_tokens: int | None = None
) -> str:
    """Call the LLM with automatic key rotation and Ollama fallback.

    Groq mode (default): tries GROQ_API_KEYS[0], [1], ... in order. On a
    retryable failure, switches immediately to the next key, then the next
    tier (OpenRouter), then Ollama (auto-started).

    Ollama mode (LLM_PROVIDER=ollama): calls Ollama directly, skipping all
    Groq/OpenRouter key logic.

    max_tokens defaults to the provider's own default when unset — pass it
    explicitly for prompts whose expected output is large, since a silent
    truncation surfaces downstream as a confusing Pydantic "field required"
    error rather than an obvious token-limit one.
    """
    payload = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if LLM_DEBUG_LOGGING:
        logger.debug("  full prompt: %s", json.dumps(messages)[:3000])

    if LLM_PROVIDER == "ollama":
        logger.info("LLM  ollama/%s  (forced)", model)
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                ACTIVE_BASE_URL, headers={"Content-Type": "application/json"}, json=payload
            )
        resp.raise_for_status()
        logger.info("  ollama OK  %.0f ms", (time.perf_counter() - t0) * 1000)
        return _extract_content(resp)

    # Groq mode: cycle through all available keys, starting from the cursor.
    # The cursor read/advance is locked so concurrent requests hitting a
    # failure on the same key don't both advance past the same "next" key.
    global _groq_key_cursor
    n = len(GROQ_API_KEYS)
    async with _key_cursor_lock:
        start_cursor = _groq_key_cursor
    for offset in range(n):
        idx = (start_cursor + offset) % n
        api_key = GROQ_API_KEYS[idx]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        logger.info("LLM  groq[%d/%d]/%s", idx + 1, n, model)
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(GROQ_BASE_URL, headers=headers, json=payload)
        except _RETRYABLE_NETWORK_EXCS as exc:
            logger.warning("  groq[%d] -> network error (%s), trying next key", idx + 1, exc)
            async with _key_cursor_lock:
                _groq_key_cursor = (idx + 1) % n
            continue

        if _is_retryable_status(resp.status_code):
            logger.warning("  groq[%d] -> HTTP %d, trying next key", idx + 1, resp.status_code)
            async with _key_cursor_lock:
                _groq_key_cursor = (idx + 1) % n
            continue

        resp.raise_for_status()
        logger.info("  groq[%d] OK  %.0f ms", idx + 1, (time.perf_counter() - t0) * 1000)
        return _extract_content(resp)

    # All Groq keys exhausted — try OpenRouter before Ollama
    logger.warning("LLM  all %d Groq key(s) exhausted", n)
    if OR_API_KEYS:
        global _or_key_cursor
        n_or = len(OR_API_KEYS)
        async with _key_cursor_lock:
            or_start_cursor = _or_key_cursor
        or_model = GROQ_TO_OR_MODEL.get(model, OR_PRIMARY_MODEL)
        or_payload = {**payload, "model": or_model}
        for offset in range(n_or):
            idx = (or_start_cursor + offset) % n_or
            api_key = OR_API_KEYS[idx]
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            logger.info("LLM  openrouter[%d/%d]/%s", idx + 1, n_or, or_model)
            t0 = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(OPENROUTER_BASE_URL, headers=headers, json=or_payload)
            except _RETRYABLE_NETWORK_EXCS as exc:
                logger.warning("  openrouter[%d] -> network error (%s), trying next key", idx + 1, exc)
                async with _key_cursor_lock:
                    _or_key_cursor = (idx + 1) % n_or
                continue
            if _is_retryable_status(resp.status_code):
                logger.warning("  openrouter[%d] -> HTTP %d, trying next key", idx + 1, resp.status_code)
                async with _key_cursor_lock:
                    _or_key_cursor = (idx + 1) % n_or
                continue
            resp.raise_for_status()
            logger.info("  openrouter[%d] OK  %.0f ms", idx + 1, (time.perf_counter() - t0) * 1000)
            return _extract_content(resp)
        logger.warning("LLM  all OpenRouter keys exhausted — falling back to Ollama")

    # All cloud providers exhausted — fall back to Ollama
    await _ensure_ollama_running()
    ollama_model = GROQ_TO_OLLAMA_MODEL.get(model, OLLAMA_PRIMARY_MODEL)
    ollama_payload = {**payload, "model": ollama_model}
    logger.info("LLM  ollama/%s  (fallback)", ollama_model)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            OLLAMA_BASE_URL, headers={"Content-Type": "application/json"}, json=ollama_payload
        )
    resp.raise_for_status()
    logger.info("  ollama OK  %.0f ms", (time.perf_counter() - t0) * 1000)
    return _extract_content(resp)


def strip_fences(raw: str) -> str:
    """Strip a markdown code fence (```json ... ``` or ``` ... ```) from an
    LLM response if present. Shared by every agent that parses raw LLM JSON."""
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else parts[0]
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


async def call_llm_json(
    messages: list[dict],
    model: str,
    schema_class: Type[T],
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> T:
    """Call LLM expecting JSON output that validates against schema_class.

    Retries once with an error-correction prompt on schema failure. On a
    truncated response (finish_reason=length) the retry also raises
    max_tokens by 50%, since a correction prompt alone can't fix a response
    that was cut off mid-string. Raises ValueError if both attempts fail.
    """
    for attempt in range(2):
        system_hint = {
            "role": "system",
            "content": (
                "You MUST respond with a single valid JSON object that matches this schema:\n"
                f"{json.dumps(schema_class.model_json_schema(), indent=2)}\n"
                "No markdown, no explanation — raw JSON only."
            ),
        }
        full_messages = [system_hint] + messages

        try:
            raw = await call_llm(full_messages, model, temperature, max_tokens=max_tokens)
        except TruncatedResponseError as exc:
            raw = exc.content
            if attempt == 0:
                logger.warning("LLM response truncated (attempt 1) — retrying with larger max_tokens")
                max_tokens = int(max_tokens * 1.5) if max_tokens else 2000
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": "Your previous response was cut off before finishing. "
                        "Return ONLY the complete, corrected JSON object.",
                    },
                ]
                continue
            else:
                logger.error("LLM response truncated after 2 attempts")
                raise ValueError(f"LLM response truncated after 2 attempts. Last response: {raw}") from exc

        text = strip_fences(raw)

        try:
            data = json.loads(text)
            return schema_class.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            if attempt == 0:
                logger.warning("JSON schema validation failed (attempt 1) — retrying with correction prompt: %s", exc)
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            f"Your response failed validation: {exc}\n"
                            "Fix it and return only the corrected JSON object."
                        ),
                    },
                ]
            else:
                logger.error("JSON schema validation failed after 2 attempts: %s", exc)
                raise ValueError(
                    f"LLM failed schema validation after 2 attempts: {exc}\nLast response: {raw}"
                ) from exc

    raise ValueError("Unreachable")
