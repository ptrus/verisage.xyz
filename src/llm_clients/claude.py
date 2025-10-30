"""Claude (Anthropic) LLM client implementation."""

from anthropic import AsyncAnthropic

from src.llm_clients.base import BaseLLMClient
from src.models import LLMResponse


class ClaudeClient(BaseLLMClient):
    """Client for Anthropic's Claude API."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        """Initialize Claude client.

        Args:
            api_key: Anthropic API key
            model: Claude model name (must support web_search tool for real-time grounding)
        """
        super().__init__(api_key, "claude")
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model
        # Configure web-search tool to support real-time grounding data.
        self.tools = [
            {
                "type": "web_search_20250305",
                "name": "web_search",
            }
        ]

    async def query(self, prompt: str) -> LLMResponse:
        """Send a query to Claude and return structured response.

        Args:
            prompt: The question/prompt to send to Claude

        Returns:
            LLMResponse with decision, confidence, reasoning, and raw response
        """
        try:
            dispute_prompt = self._create_dispute_prompt(prompt)

            message = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._system_prompt(),
                messages=[{"role": "user", "content": dispute_prompt}],
                tools=self.tools,
                stream=False,
            )

            # Extract text from content blocks, handling tool use responses.
            raw_response = ""
            for block in message.content:
                if hasattr(block, "text"):
                    raw_response += block.text

            # If no text found, return uncertain.
            if not raw_response:
                return LLMResponse(
                    provider=self.provider_name,
                    decision="uncertain",
                    confidence=0.0,
                    reasoning="No text response received from Claude",
                    raw_response=str(message.content),
                    error="No text content in response",
                )

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
                reasoning=f"Error querying Claude: {str(e)}",
                raw_response="",
                error=str(e),
            )
