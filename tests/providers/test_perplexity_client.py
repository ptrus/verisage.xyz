#!/usr/bin/env python3
"""Test script for Perplexity client."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.llm_clients.perplexity import PerplexityClient  # noqa: E402

# Load environment variables
load_dotenv()


async def test_perplexity_prompt(client: PerplexityClient, prompt: str):
    """Test a single prompt and show the response."""
    print(f"\n{'=' * 80}")
    print(f"PROMPT: {prompt}")
    print(f"{'=' * 80}")

    response = await client.query(prompt)

    print(f"\nProvider: {response.provider}")
    print(f"Decision: {response.decision}")
    print(f"Confidence: {response.confidence}")
    print(f"Reasoning: {response.reasoning}")
    print(f"\nRaw Response:\n{response.raw_response}")

    if response.error:
        print(f"\nError: {response.error}")

    print(f"{'=' * 80}\n")

    return response


async def main():
    """Run test prompts."""
    # Get API key
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key or api_key == "mock-key":
        print("ERROR: PERPLEXITY_API_KEY not found in environment")
        return

    # Initialize client
    print("Initializing Perplexity client...")
    client = PerplexityClient(api_key)

    # Test prompts
    test_prompts = [
        # Real-time data that requires web search
        "Did the Los Angeles Lakers beat the Sacramento Kings on October 26, 2025?",
        # Historical fact
        "Did the United States land on the moon in 1969?",
        # Recent event
        "Who won the 2024 US Presidential election?",
    ]

    for prompt in test_prompts:
        try:
            await test_perplexity_prompt(client, prompt)
        except Exception as e:
            print(f"ERROR testing prompt: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
