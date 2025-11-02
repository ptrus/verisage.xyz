"""Mock LLM client for testing and development."""

import asyncio

from src.llm_clients.base import BaseLLMClient
from src.models import DecisionType, LLMResponse


class MockLLMClient(BaseLLMClient):
    """Mock LLM client that returns fixed responses after a delay."""

    def __init__(self, provider_name: str = "mock", sleep_duration: float = 5.0):
        """Initialize mock client.

        Args:
            provider_name: Name to identify this mock provider
            sleep_duration: How long to sleep before returning (simulates API latency)
        """
        # Don't call super().__init__ since we don't need an API key.
        self.provider_name = provider_name
        self.sleep_duration = sleep_duration

    async def query(self, prompt: str) -> LLMResponse:
        """Return a mock response after sleeping.

        Args:
            prompt: The query (ignored in mock mode)

        Returns:
            LLMResponse with fixed mock data
        """
        # Simulate API latency.
        await asyncio.sleep(self.sleep_duration)

        # Return fixed mock response.
        raw_response = """DECISION: YES
CONFIDENCE: 0.85
REASONING: This is a mock response for testing purposes. The mock oracle always returns YES with 85% confidence after a 5-second delay to simulate real API behavior."""

        return LLMResponse(
            provider=self.provider_name,
            model="mock",
            decision=DecisionType.YES,
            confidence=0.85,
            reasoning="This is a mock response for testing purposes. The mock oracle always returns YES with 85% confidence after a 5-second delay to simulate real API behavior.",
            raw_response=raw_response,
            error=None,
        )
