from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

import anthropic
from openai import OpenAI, OpenAIError
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from newsletter.utils.utils import timed

# ──────────────────────────────── env ──────────────────────────────
load_dotenv(dotenv_path=Path(".env"))

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

if not OPENAI_KEY:
    raise EnvironmentError("OPENAI_API_KEY not set in environment.")
if not ANTHROPIC_KEY:
    raise EnvironmentError("ANTHROPIC_API_KEY not set in environment.")

openai_client = OpenAI(api_key=OPENAI_KEY, max_retries=0)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY, max_retries=0)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────── retry decorator ────────────────────────
retry_call = retry(
    wait=wait_exponential(multiplier=1, min=4, max=60),
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
        temperature: float = 0.2,
        max_tokens: int = 12000,
        timeout: int = 180,
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, str]] = None,
        enable_web_search: bool = False,
        web_search_options: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Unified wrapper for OpenAI & Anthropic chat completions.
    Can enable web search for supported providers/models.

    Returns the raw text response (ready for json.loads if applicable).
    """
    extra_messages = extra_messages or []

    if provider == "openai":
        messages = (
                ([{"role": "system", "content": system}] if system else [])
                + [{"role": "user", "content": user}]
                + extra_messages
        )

        openai_params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
            "tools": tools,
            "response_format": response_format,
        }
        if enable_web_search:
            # Caller should ensure 'model' is search-enabled (e.g., gpt-4o-mini-search-preview)
            if web_search_options:
                openai_params["web_search_options"] = web_search_options
                del openai_params["response_format"]
                del openai_params["timeout"]
                del openai_params["tools"]
                del openai_params["temperature"]
            # If 'tools' is also provided along with enable_web_search for OpenAI,
            # ensure they are compatible or handled as expected by OpenAI API.
            # For now, we pass both if provided.

        try:
            resp = openai_client.chat.completions.create(**openai_params)
        except OpenAIError as e:
            logger.error("Status %s\n%s", e.status_code, e.response.json())
            raise
        return resp.choices[0].message.content

    elif provider == "anthropic":
        anthropic_messages = [
            {"role": "user", "content": [{"type": "text", "text": user}]}
        ]
        if extra_messages:
            for m in extra_messages:
                anthropic_messages.append(
                    {
                        "role": m["role"],
                        "content": [{"type": "text", "text": m["content"]}],
                    }
                )

        anthropic_params: Dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        anthropic_tool_list = None
        if enable_web_search:
            # Use Anthropic's specific web search tool
            # For now, generic 'tools' param is ignored if 'enable_web_search' is true for Anthropic
            max_uses = 5
            if web_search_options and "max_uses" in web_search_options and isinstance(web_search_options["max_uses"],
                                                                                      int):
                max_uses = web_search_options["max_uses"]
            anthropic_tool_list = [{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": max_uses
            }]

        if anthropic_tool_list:
            anthropic_params["tools"] = anthropic_tool_list

        resp = anthropic_client.messages.create(**anthropic_params)

        # Extract text content. This should work even if the model used a tool internally (like web search)
        # and then produced a final text response.
        final_text_parts = []
        for blk in resp.content:
            if blk.type == "text":
                final_text_parts.append(blk.text)
        return "".join(final_text_parts)

    raise ValueError(f"Unsupported provider: {provider}")
