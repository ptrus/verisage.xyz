"""Oracle orchestrator for multi-LLM dispute resolution."""

import asyncio
from typing import Optional

from src.config import settings
from src.llm_clients.claude import ClaudeClient
from src.llm_clients.gemini import GeminiClient
from src.llm_clients.grok import GrokClient
from src.llm_clients.mock import MockLLMClient
from src.llm_clients.openai import OpenAIClient
from src.llm_clients.perplexity import PerplexityClient
from src.models import (
    DecisionType,
    LLMResponse,
    OracleResult,
    TweetAnalysisResult,
    TweetLLMResponse,
    TweetVerdictType,
)
from src.scoring import WeightedScorer


class TooManyAgentsFailedError(Exception):
    """Raised when more than 2 API agents fail."""

    pass


class Oracle:
    """Orchestrates queries to multiple LLM backends and aggregates results."""

    def __init__(self):
        """Initialize the Oracle with all LLM clients and scoring system."""
        # Initialize LLM clients (use mock clients in debug mode).
        if settings.debug_mock:
            # Create 5 mock clients to simulate multi-LLM consensus.
            self.clients = {
                "mock-claude": MockLLMClient(provider_name="mock-claude", sleep_duration=3.0),
                "mock-gemini": MockLLMClient(provider_name="mock-gemini", sleep_duration=2.5),
                "mock-perplexity": MockLLMClient(
                    provider_name="mock-perplexity", sleep_duration=4.0
                ),
                "mock-openai": MockLLMClient(provider_name="mock-openai", sleep_duration=2.0),
                "grok": MockLLMClient(provider_name="mock-grok", sleep_duration=2.5),
            }
            self.weights = {
                "mock-claude": 1.0,
                "mock-gemini": 1.0,
                "mock-perplexity": 1.0,
                "mock-openai": 1.0,
                "grok": 1.0,
            }
        else:
            # Check which providers have API keys configured.
            # Filter out None, empty strings, and whitespace-only strings.
            available_providers = {
                "claude": settings.claude_api_key,
                "gemini": settings.gemini_api_key,
                "perplexity": settings.perplexity_api_key,
                "openai": settings.openai_api_key,
                "grok": settings.grok_api_key,
            }

            configured_providers = {
                provider: key
                for provider, key in available_providers.items()
                if key and key.strip()
            }

            # Require at least 2 providers for consensus.
            if len(configured_providers) < 2:
                missing_list = ", ".join(
                    sorted([p for p in available_providers.keys() if not available_providers[p]])
                )
                raise ValueError(
                    f"At least 2 LLM providers are required for consensus. "
                    f"Configured: {len(configured_providers)}/5. "
                    f"Missing: {missing_list}. "
                    "Set at least 2 API keys or enable DEBUG_MOCK=true."
                )

            # Initialize only configured clients.
            self.clients = {}
            self.weights = {}

            if "claude" in configured_providers:
                self.clients["claude"] = ClaudeClient(
                    settings.claude_api_key, model=settings.claude_model
                )
                self.weights["claude"] = settings.claude_weight

            if "gemini" in configured_providers:
                self.clients["gemini"] = GeminiClient(
                    settings.gemini_api_key, model=settings.gemini_model
                )
                self.weights["gemini"] = settings.gemini_weight

            if "perplexity" in configured_providers:
                self.clients["perplexity"] = PerplexityClient(
                    settings.perplexity_api_key, model=settings.perplexity_model
                )
                self.weights["perplexity"] = settings.perplexity_weight

            if "openai" in configured_providers:
                self.clients["openai"] = OpenAIClient(
                    settings.openai_api_key, model=settings.openai_model
                )
                self.weights["openai"] = settings.openai_weight

            if "grok" in configured_providers:
                self.clients["grok"] = GrokClient(settings.grok_api_key, model=settings.grok_model)
                self.weights["grok"] = settings.grok_weight

        self.scorer = WeightedScorer(self.weights)

    async def resolve_dispute(self, query: str) -> OracleResult:
        """Query all LLM backends and aggregate their responses.

        Args:
            query: The dispute question to resolve

        Returns:
            OracleResult with aggregated decision and individual responses

        Raises:
            TooManyAgentsFailedError: If more than 2 API agents fail
        """
        # Query all LLMs in parallel with per-provider error isolation.
        # Exclude Grok from fact verification (only used for tweet analysis).
        tasks = [
            self._safe_query(provider_name, client, query)
            for provider_name, client in self.clients.items()
            if provider_name != "grok"
        ]
        responses: list[LLMResponse] = await asyncio.gather(*tasks, return_exceptions=False)

        # Check if too many agents failed.
        failed_count = sum(1 for r in responses if r.error is not None)
        if failed_count > 2:
            failed_providers = [r.provider for r in responses if r.error is not None]
            raise TooManyAgentsFailedError(
                f"More than 2 API agents failed ({failed_count} failed: {', '.join(failed_providers)}). "
                "Job will be retried."
            )

        # Aggregate responses using weighted scoring.
        result = self.scorer.aggregate_responses(query, responses)

        return result

    async def _safe_query(
        self,
        provider_name: str,
        client,
        query: str,
    ) -> LLMResponse:
        """Query a single provider and normalize any unexpected exceptions."""
        try:
            response = await client.query(query)
        except Exception as exc:  # pragma: no cover - defensive guard
            return LLMResponse(
                provider=provider_name,
                model="unknown",
                decision=DecisionType.UNCERTAIN,
                confidence=0.0,
                reasoning=f"Error querying {provider_name}: {exc}",
                raw_response="",
                error=str(exc),
            )

        if response.provider != provider_name:
            # Ensure downstream code can always rely on the provider identifier.
            response = response.model_copy(update={"provider": provider_name})

        return response

    async def analyze_tweet(self, tweet_url: str) -> TweetAnalysisResult:
        """Analyze a tweet for credibility using Grok (only model that can fetch tweets).

        Args:
            tweet_url: Twitter/X URL to analyze

        Returns:
            TweetAnalysisResult with aggregated verdict and individual analyses

        Raises:
            TooManyAgentsFailedError: If Grok fails
        """
        # Only Grok can fetch and analyze tweets directly from URLs.
        # Other models (Claude, Gemini, OpenAI, Perplexity) cannot access tweet content.

        if "grok" not in self.clients:
            raise ValueError(
                "Grok API key is required for tweet analysis. "
                "Set GROK_API_KEY environment variable."
            )

        # Query only Grok for tweet analysis.
        grok_response = await self._safe_analyze_tweet("grok", self.clients["grok"], tweet_url)

        # Check if Grok failed.
        if grok_response.error is not None:
            raise TooManyAgentsFailedError(
                f"Grok failed to analyze tweet: {grok_response.error}. Job will be retried."
            )

        # Return response with only Grok's analysis.
        responses = [grok_response]

        # Aggregate responses (will just use Grok's verdict since it's the only one).
        result = self.scorer.aggregate_tweet_responses(tweet_url, responses)

        return result

    async def _safe_analyze_tweet(
        self,
        provider_name: str,
        client,
        tweet_url: str,
    ) -> TweetLLMResponse:
        """Analyze tweet with a single provider and normalize any unexpected exceptions."""
        try:
            response = await client.analyze_tweet(tweet_url)
        except Exception as exc:  # pragma: no cover - defensive guard
            return TweetLLMResponse(
                provider=provider_name,
                model="unknown",
                verdict=TweetVerdictType.QUESTIONABLE,
                confidence=0.0,
                analysis=f"Error analyzing tweet with {provider_name}: {exc}",
                identified_claims=[],
                red_flags=[],
                raw_response="",
                error=str(exc),
            )

        if response.provider != provider_name:
            # Ensure downstream code can always rely on the provider identifier.
            response = response.model_copy(update={"provider": provider_name})

        return response


# Lazily instantiated oracle. Imported modules call get_oracle() to avoid.
# validation on module import when running the API server.
_oracle_instance: Optional["Oracle"] = None


def get_oracle() -> Oracle:
    """Return a shared Oracle instance, creating it on first use."""
    global _oracle_instance
    if _oracle_instance is None:
        _oracle_instance = Oracle()
    return _oracle_instance
