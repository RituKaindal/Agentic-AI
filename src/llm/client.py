"""LLM client using OpenAI-compatible API."""

import json
import logging
from functools import lru_cache
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from src.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """LLM client with structured output support via OpenAI-compatible API."""

    def __init__(self, model: str | None = None):
        """Initialize LLM client.

        Args:
            model: Model identifier (e.g., 'claude-sonnet-4-6').
                   If not provided, uses the model from settings.
        """
        settings = get_settings()
        self.model = model or settings.llm_model
        self.api_key = settings.get_api_key()
        self.base_url = settings.openai_base_url

        # Initialize OpenAI client with FICO AI Gateway
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str:
        """Get a completion from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            The assistant's response text.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM completion failed: {e}")
            raise

    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> T:
        """Get a structured response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            response_model: Pydantic model class for the response.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            Instance of response_model populated with the LLM's response.
        """
        schema = response_model.model_json_schema()
        schema_str = json.dumps(schema, indent=2)

        system_suffix = f"""
You must respond with valid JSON that matches this schema:
{schema_str}

Respond ONLY with the JSON object, no markdown code blocks or other text."""

        enhanced_messages = []
        for msg in messages:
            if msg["role"] == "system":
                enhanced_messages.append(
                    {"role": "system", "content": msg["content"] + "\n\n" + system_suffix}
                )
            else:
                enhanced_messages.append(msg)

        if not any(m["role"] == "system" for m in messages):
            enhanced_messages.insert(0, {"role": "system", "content": system_suffix})

        response_text = await self.complete(
            messages=enhanced_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
            response_text = response_text.strip()

        try:
            data = json.loads(response_text)
            return response_model.model_validate(data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}\nResponse: {response_text[:500]}")
            raise ValueError(f"LLM returned invalid JSON: {e}")

    async def analyze_code(
        self,
        code: str,
        prompt: str,
        response_model: type[T] | None = None,
        context: str | None = None,
    ) -> T | str:
        """Analyze code with an optional context.

        Args:
            code: The code to analyze.
            prompt: Analysis instructions.
            response_model: Optional Pydantic model for structured response.
            context: Optional additional context.

        Returns:
            Either structured response or raw text.
        """
        messages = [
            {
                "role": "system",
                "content": "You are an expert code reviewer. Analyze code carefully and provide detailed, actionable feedback.",
            },
            {
                "role": "user",
                "content": f"{prompt}\n\n{f'Context: {context}' if context else ''}\n\nCode:\n```\n{code}\n```",
            },
        ]

        if response_model:
            return await self.complete_structured(messages, response_model)
        return await self.complete(messages)


@lru_cache
def get_llm_client(model: str | None = None) -> LLMClient:
    """Get a cached LLM client instance."""
    return LLMClient(model)
