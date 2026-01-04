from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI


class LLM:
    def __init__(self, base_url: str, api_key: str, seed: Optional[int] = None):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.seed = seed
        # Optional: enable timings via env var LLM_TIMINGS=1
        self.timings = os.getenv("LLM_TIMINGS", "0").strip() == "1"

    def chat(self, model: str, messages: List[Dict[str, str]], temperature: float) -> str:
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed

        t0 = time.time()
        resp = self.client.chat.completions.create(**kwargs)
        dt = time.time() - t0

        if self.timings:
            print(f"[llm] model={model} temp={temperature} took={dt:.2f}s")

        return (resp.choices[0].message.content or "").strip()