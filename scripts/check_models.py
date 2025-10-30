#!/usr/bin/env python3
"""Check available models for each API."""

import os

from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("CHECKING AVAILABLE MODELS")
print("=" * 80)
print()

# Check Claude.
print("CLAUDE (Anthropic)")
print("-" * 80)
claude_key = os.getenv("CLAUDE_API_KEY")
if claude_key:
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=claude_key)

        # Try a simple test with different model names.
        test_models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20240620",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]

        print(f"API Key: {claude_key[:20]}...")
        print("\nTrying models:")
        for model in test_models:
            try:
                response = client.messages.create(
                    model=model, max_tokens=10, messages=[{"role": "user", "content": "Hi"}]
                )
                print(f"  ✓ {model} - WORKS")
                break
            except anthropic.NotFoundError:
                print(f"  ✗ {model} - NOT FOUND")
            except anthropic.AuthenticationError as e:
                print(f"  ✗ {model} - AUTH ERROR: {e}")
                break
            except Exception as e:
                print(f"  ? {model} - ERROR: {type(e).__name__}: {str(e)[:100]}")
    except Exception as e:
        print(f"Error: {e}")
else:
    print("No API key found")

print()

# Check Gemini.
print("GEMINI (Google)")
print("-" * 80)
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    try:
        import google.generativeai as genai

        genai.configure(api_key=gemini_key)

        print(f"API Key: {gemini_key[:20]}...")
        print("\nListing available models:")

        models = genai.list_models()
        for model in models:
            if "generateContent" in model.supported_generation_methods:
                print(f"  ✓ {model.name}")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
else:
    print("No API key found")

print()
print("=" * 80)
