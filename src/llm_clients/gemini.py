"""Google Gemini LLM client implementation."""

from google import genai
from google.genai.types import GenerateContentConfig, GoogleSearch, Tool

from src.llm_clients.base import BaseLLMClient
from src.models import LLMResponse


class GeminiClient(BaseLLMClient):
    """Client for Google's Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-exp"):
        """Initialize Gemini client.

        Args:
            api_key: Google API key
            model: Gemini model name (must support Google Search grounding)
        """
        super().__init__(api_key, "gemini")
        self.model_name = model

    async def query(self, prompt: str) -> LLMResponse:
        """Send a query to Gemini and return structured response.

        Args:
            prompt: The question/prompt to send to Gemini

        Returns:
            LLMResponse with decision, confidence, reasoning, and raw response
        """
        client = None
        try:
            client = genai.Client(api_key=self.api_key)
            dispute_prompt = self._create_dispute_prompt(prompt)

            response = await client.aio.models.generate_content(
                model=self.model_name,
                config=GenerateContentConfig(
                    system_instruction=self._system_prompt(),
                    tools=[Tool(google_search=GoogleSearch())],
                ),
                contents=dispute_prompt,
            )
            raw_response = response.text
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
                reasoning=f"Error querying Gemini: {str(e)}",
                raw_response="",
                error=str(e),
            )
        finally:
            # Ensure the aio transport is closed to avoid connection leaks.
            if client is not None:
                close = getattr(client.aio, "close", None)
                if callable(close):
                    await close()
