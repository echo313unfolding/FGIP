"""Async LLM client for OpenAI-compatible endpoints (Ollama, LM Studio, etc.)."""

import httpx
import os
import time
from typing import Any, Optional

# Configurable timeout via environment variable
# Default 120s, but CDNA needs 600+ for slow generation
DEFAULT_LLM_TIMEOUT = float(os.environ.get("ECHO_LLM_TIMEOUT", "120"))


class LLMClient:
    """Async client for OpenAI-compatible chat completions."""

    def __init__(self, base_url: str, model: str, timeout: float = DEFAULT_LLM_TIMEOUT):
        """
        Initialize the LLM client.

        Args:
            base_url: Base URL for the OpenAI-compatible API (e.g., http://127.0.0.1:11434/v1)
            model: Model name to use (e.g., qwen2.5:latest)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._warmed: bool = False
        self._warmup_time_ms: Optional[float] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def warmup(self) -> dict[str, Any]:
        """
        Warm up LLM by sending minimal completion request.

        Preloads model into memory on Ollama-style backends.
        This eliminates cold-start latency on first real request.

        Returns:
            Dict with warmup status, model, and duration
        """
        start = time.time()
        client = await self._get_client()

        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "warmup"}],
                    "max_tokens": 1,
                    "temperature": 0.0,
                },
                timeout=60.0,  # Allow cold start time
            )

            duration_ms = round((time.time() - start) * 1000, 2)
            self._warmup_time_ms = duration_ms

            if response.status_code == 200:
                self._warmed = True
                return {
                    "status": "warmed",
                    "model": self.model,
                    "duration_ms": duration_ms,
                }
            else:
                return {
                    "status": "error",
                    "model": self.model,
                    "duration_ms": duration_ms,
                    "error": f"HTTP {response.status_code}",
                }
        except Exception as e:
            duration_ms = round((time.time() - start) * 1000, 2)
            return {
                "status": "error",
                "model": self.model,
                "duration_ms": duration_ms,
                "error": str(e),
            }

    @property
    def is_warmed(self) -> bool:
        """Check if LLM has been warmed up."""
        return self._warmed

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        temperature: float = 0.0,
        tool_choice: str = "auto",
    ) -> dict[str, Any]:
        """
        Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions in OpenAI format
            temperature: Sampling temperature (0.0 for deterministic)
            tool_choice: Tool choice mode ('auto', 'none', 'required')

        Returns:
            Response dict with 'choices', potentially containing 'tool_calls'
        """
        client = await self._get_client()

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        url = f"{self.base_url}/chat/completions"

        response = await client.post(url, json=payload)
        response.raise_for_status()

        return response.json()

    async def health_check(self) -> dict[str, Any]:
        """Check if the LLM endpoint is reachable."""
        client = await self._get_client()

        try:
            # Try models endpoint first (standard OpenAI)
            response = await client.get(f"{self.base_url}/models", timeout=5.0)
            if response.status_code == 200:
                return {"status": "ok", "endpoint": self.base_url, "model": self.model}
        except Exception:
            pass

        # Fallback: try a minimal chat request
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
                timeout=10.0,
            )
            if response.status_code == 200:
                return {"status": "ok", "endpoint": self.base_url, "model": self.model}
        except Exception as e:
            return {"status": "error", "endpoint": self.base_url, "error": str(e)}

        return {"status": "unreachable", "endpoint": self.base_url}
