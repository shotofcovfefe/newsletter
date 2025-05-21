from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
from openai import OpenAI
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_random_exponential

from newsletter.utils import timed  # <-- your existing timing decorator

# ──────────────────────────────── env ──────────────────────────────
load_dotenv(dotenv_path=Path(".env"))

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

if not OPENAI_KEY:
    raise EnvironmentError("OPENAI_API_KEY not set in environment.")
if not ANTHROPIC_KEY:
    raise EnvironmentError("ANTHROPIC_API_KEY not set in environment.")

openai_client = OpenAI(api_key=OPENAI_KEY)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ────────────────────────── retry decorator ────────────────────────
retry_call = retry(
    wait=wait_random_exponential(min=1, max=20),
    stop=stop_after_attempt(5),
    reraise=True,
)


# ───────────────────────── unified call_llm ────────────────────────
@timed("LLM call")
@retry_call
def call_llm(
        provider: str,
        model: str,
        *,
        system: Optional[str] = None,
        user: str,
        extra_messages: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        timeout: int = 60,
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, str]] = None,
) -> str:
    """
    Unified wrapper for OpenAI & Anthropic chat completions.

    Returns the raw text response (ready for json.loads if applicable).
    """
    extra_messages = extra_messages or []

    if provider == "openai":
        messages = (
                ([{"role": "system", "content": system}] if system else [])
                + [{"role": "user", "content": user}]
                + extra_messages
        )

        resp = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            tools=tools,
            response_format=response_format,
        )
        return resp.choices[0].message.content

    elif provider == "anthropic":
        # Claude-3 schema  ──────────────────────────────────────────────
        messages = [
            {"role": "user", "content": [{"type": "text", "text": user}]}
        ]
        if extra_messages:
            # extra_messages already OpenAI-style; convert each to blocks
            for m in extra_messages:
                messages.append(
                    {
                        "role": m["role"],
                        "content": [{"type": "text", "text": m["content"]}],
                    }
                )

        resp = anthropic_client.messages.create(
            model=model,
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return "".join(
            blk.text for blk in resp.content if blk.type == "text"
        )

    raise ValueError(f"Unsupported provider: {provider}")
