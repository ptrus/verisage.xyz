"""OpenAI LLM client implementation."""

import httpx

from src.llm_clients.base import BaseLLMClient
from src.models import LLMResponse


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: OpenAI model name (must support web_search tool for real-time grounding)
        """
        super().__init__(api_key, "openai")
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.model = model
        # Configure web-search tool to support real-time grounding data.
        self.tools = [{"type": "web_search"}]

    async def query(self, prompt: str) -> LLMResponse:
        """Send a query to OpenAI and return structured response.

        Args:
            prompt: The question/prompt to send to OpenAI

        Returns:
            LLMResponse with decision, confidence, reasoning, and raw response
        """
        try:
            dispute_prompt = self._create_dispute_prompt(prompt)

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "tools": self.tools,
                "tool_choice": "auto",
                "messages": [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": dispute_prompt},
                ],
                "max_tokens": 1024,
                "temperature": 0.2,
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            raw_response = data["choices"][0]["message"]["content"]
            decision, confidence, reasoning = self._parse_response(raw_response)

            return LLMResponse(
                provider=self.provider_name,
                decision=decision,
                confidence=confidence,
                reasoning=reasoning,
                raw_response=raw_response,
                error=None,
            )

        except Exception as e:
            return LLMResponse(
                provider=self.provider_name,
                decision="uncertain",
                confidence=0.0,
                reasoning=f"Error querying OpenAI: {str(e)}",
                raw_response="",
                error=str(e),
            )
