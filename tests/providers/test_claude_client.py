#!/usr/bin/env python3
"""Test script for Claude client with web search tools."""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.llm_clients.claude import ClaudeClient  # noqa: E402

# Load environment variables
load_dotenv()


async def test_claude_prompt(client: ClaudeClient, prompt: str):
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
    # Get API key (try both names)
    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: CLAUDE_API_KEY or ANTHROPIC_API_KEY not found in environment")
        return

    # Initialize client
    print("Initializing Claude client...")
    client = ClaudeClient(api_key)

    # Test prompts
    test_prompts = [
        # Real-time data that requires web search
        "Did the Los Angeles Lakers beat the Sacramento Kings on October 26, 2025?",
        # Historical fact that doesn't need web search
        "Did the United States land on the moon in 1969?",
        # Recent event
        "Who won the 2024 US Presidential election?",
    ]

    for prompt in test_prompts:
        try:
            await test_claude_prompt(client, prompt)
        except Exception as e:
            print(f"ERROR testing prompt: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
