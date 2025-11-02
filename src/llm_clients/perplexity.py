"""Perplexity AI LLM client implementation."""

from perplexity import AsyncPerplexity

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
        super().__init__(api_key, "perplexity", model)
        self.client = AsyncPerplexity(api_key=api_key)
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

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": dispute_prompt},
                ],
                search_mode="web",
                enable_search_classifier=True,
                web_search_options={
                    "search_type": "pro",
                },
            )

            raw_response = response.choices[0].message.content
            decision, confidence, reasoning = self._parse_response(raw_response)

            return LLMResponse(
                provider=self.provider_name,
                model=self.model,
                decision=decision,
                confidence=confidence,
                reasoning=reasoning,
                raw_response=raw_response,
                error=None,
            )

        except Exception as e:
            return LLMResponse(
                provider=self.provider_name,
                model=self.model,
                decision="uncertain",
                confidence=0.0,
                reasoning=f"Error querying Perplexity: {str(e)}",
                raw_response="",
                error=str(e),
            )
