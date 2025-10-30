"""Perplexity AI LLM client implementation."""

import httpx

from src.llm_clients.base import BaseLLMClient
from src.models import LLMResponse


class PerplexityClient(BaseLLMClient):
    """Client for Perplexity AI API."""

    def __init__(self, api_key: str, model: str = "sonar-pro"):
        """Initialize Perplexity client.

        Args:
            api_key: Perplexity API key
            model: Perplexity model name (sonar models have built-in real-time web search)
        """
        super().__init__(api_key, "perplexity")
        self.api_url = "https://api.perplexity.ai/chat/completions"
        self.model = model

    async def query(self, prompt: str) -> LLMResponse:
        """Send a query to Perplexity and return structured response.

        Args:
            prompt: The question/prompt to send to Perplexity

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
                "enable_search_classifier": True,
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
                reasoning=f"Error querying Perplexity: {str(e)}",
                raw_response="",
                error=str(e),
            )
