from __future__ import annotations

"""Thin wrapper around an OpenAI-compatible chat completions endpoint (e.g., LM Studio)."""

import os
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI


class LLM:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        seed: Optional[int] = None,
        timeout: Optional[float] = None,
    ):
        """
        Args:
            base_url: OpenAI-compatible endpoint (e.g., LM Studio local server).
            api_key: Arbitrary token for local servers.
            seed: Optional; only used if backend supports it.
            timeout: Optional request timeout in seconds (OpenAI SDK uses httpx under the hood).
        """
        self.base_url = base_url
        self.seed = seed

        # NOTE: OpenAI python SDK accepts `timeout` for httpx client timeouts.
        # Some backends ignore it, but it's safe to pass.
        if timeout is not None:
            self.client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        else:
            self.client = OpenAI(base_url=base_url, api_key=api_key)

        # Optional: enable timings via env var LLM_TIMINGS=1
        self.timings = os.getenv("LLM_TIMINGS", "0").strip() == "1"

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        response_format: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a chat completion request and return the assistant text content.

        Args:
            response_format: Optional; if supported by backend, can enforce JSON output, e.g.
                {"type": "json_object"}
            extra: Optional dict merged into request kwargs (advanced usage: max_tokens, top_p, etc.).
        """
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        # Determinism (only if backend supports it)
        if self.seed is not None:
            kwargs["seed"] = self.seed

        # Structured output (only if backend supports it)
        if response_format is not None:
            kwargs["response_format"] = response_format

        # Allow advanced overrides (max_tokens, top_p, etc.)
        if extra:
            kwargs.update(extra)

        t0 = time.time()
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as e:
            raise RuntimeError(
                f"LLM request failed (model={model}, base_url={self.base_url}): {e}"
            ) from e
        finally:
            if self.timings:
                dt = time.time() - t0
                rf = f" response_format={response_format}" if response_format else ""
                print(f"[llm] model={model} temp={temperature}{rf} took={dt:.2f}s")

        content = resp.choices[0].message.content
        return (content or "").strip()