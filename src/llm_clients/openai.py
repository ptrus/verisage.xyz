"""OpenAI LLM client implementation."""

import httpx

from src.llm_clients.base import BaseLLMClient
from src.models import LLMResponse


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            model: OpenAI model name (use gpt-5 for Responses API with web search)
        """
        super().__init__(api_key, "openai", model)
        self.api_url = "https://api.openai.com/v1/responses"
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

            # Responses API uses "instructions" and "input" instead of "messages"
            payload = {
                "model": self.model,
                "tools": self.tools,
                "instructions": self._system_prompt(),
                "input": dispute_prompt,
            }

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            # Responses API returns content in output array
            # Find the message object and extract the text
            raw_response = ""
            for item in data.get("output", []):
                if item.get("type") == "message" and item.get("status") == "completed":
                    content = item.get("content", [])
                    if content and content[0].get("type") == "output_text":
                        raw_response = content[0].get("text", "")
                        break
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

        except httpx.HTTPStatusError as e:
            # Get the error details from the response
            error_detail = e.response.text if hasattr(e, "response") else str(e)
            return LLMResponse(
                provider=self.provider_name,
                model=self.model,
                decision="uncertain",
                confidence=0.0,
                reasoning=f"Error querying OpenAI: {str(e)} - {error_detail}",
                raw_response="",
                error=f"{str(e)} - {error_detail}",
            )
        except Exception as e:
            return LLMResponse(
                provider=self.provider_name,
                model=self.model,
                decision="uncertain",
                confidence=0.0,
                reasoning=f"Error querying OpenAI: {str(e)}",
                raw_response="",
                error=str(e),
            )
