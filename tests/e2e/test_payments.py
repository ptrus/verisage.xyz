#!/usr/bin/env python3
"""
Test client for Verisage x402 payment flow.

This script demonstrates the full payment flow using x402HttpxClient:
1. Create a wallet with eth_account
2. Make a request to the protected endpoint
3. x402HttpxClient automatically handles 402 response, signs and pays
4. Poll for the result
5. Test payment verification (without payment should fail, reusing payment should fail)
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from eth_account import Account
from x402.clients.base import PaymentAmountExceededError
from x402.clients.httpx import x402HttpxClient

# Load environment variables from local .env file in tests/e2e directory
script_dir = Path(__file__).parent
env_path = script_dir / ".env"
load_dotenv(dotenv_path=env_path)

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")


async def test_without_payment(query: str):
    """Test that requests without payment are rejected"""
    print("🔒 Testing without payment (should fail)...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/api/v1/query",
                json={"query": query},
            )
            if response.status_code == 402:
                print("   ✅ Correctly rejected with 402 Payment Required\n")
            else:
                print(f"   ❌ Unexpected status: {response.status_code}\n")
                print(f"   Response: {response.text}\n")
        except Exception as e:
            print(f"   ❌ Error: {e}\n")


async def test_payment_reuse(query: str, payment_header: str):
    """Test that reusing the same payment is rejected"""
    print("🔒 Testing payment reuse (should fail)...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{API_URL}/api/v1/query",
                json={"query": query},
                headers={"X-Payment": payment_header},
            )
            if response.status_code == 402:
                print("   ✅ Correctly rejected payment reuse with 402\n")
            elif response.status_code == 400:
                print("   ✅ Correctly rejected payment reuse with 400\n")
            else:
                print(f"   ❌ Unexpected status: {response.status_code}\n")
                print(f"   Response: {response.text}\n")
        except Exception as e:
            print(f"   ❌ Error: {e}\n")


async def test_insufficient_payment(query: str, account):
    """Test that insufficient payment is rejected"""
    print("🔒 Testing insufficient payment (should fail)...")
    # Set max_value very low (100 wei) - definitely insufficient for $0.001
    async with x402HttpxClient(account, max_value=100, timeout=60.0) as client:
        try:
            response = await client.post(
                f"{API_URL}/api/v1/query",
                json={"query": query},
            )
            # Should not reach here - should raise PaymentAmountExceededError before making request
            print(f"   ❌ Unexpected success with status: {response.status_code}\n")
            print(f"   Response: {response.text}\n")
        except PaymentAmountExceededError:
            print("   ✅ Correctly rejected insufficient payment with PaymentAmountExceededError\n")
        except Exception as e:
            print(f"   ❌ Unexpected error type {type(e).__name__}: {e}\n")


async def test_oracle_query_with_payment(query: str):
    """
    Test the oracle query endpoint with automatic payment handling.

    Args:
        query: The dispute question to resolve
    """
    print("🚀 Starting Verisage x402 payment flow test...\n")

    # Check for private key
    if not PRIVATE_KEY:
        print("❌ Error: PRIVATE_KEY environment variable not set")
        print("   Set PRIVATE_KEY in .env with a funded Base Sepolia wallet")
        sys.exit(1)

    # Create account from private key
    print("💼 Setting up wallet...")
    account = Account.from_key(PRIVATE_KEY)
    print(f"   Wallet address: {account.address}\n")

    # Test without payment first
    await test_without_payment(query)

    # Test with insufficient payment
    await test_insufficient_payment(query, account)

    # Create x402-enabled HTTP client
    print("📡 Creating x402 HTTP client...")
    async with x402HttpxClient(account, max_value=10000, timeout=60.0) as client:
        print("   Client ready with automatic payment handling\n")

        # Make request - payment will be handled automatically
        print(f"📝 Submitting oracle query to {API_URL}/api/v1/query...")
        print(f"   Query: {query}")
        print("   (Payment will be handled automatically if required)\n")

        try:
            start_time = time.time()
            response = await client.post(
                f"{API_URL}/api/v1/query",
                json={"query": query},
            )
            elapsed = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Job created (took {elapsed:.2f}s)")
                print(f"   Job ID: {result['job_id']}")
                print(f"   Status: {result['status']}")
                print(f"   Query: {result['query']}\n")

                # Test payment reuse with the same payment header
                payment_header = response.request.headers.get("X-Payment")
                if payment_header:
                    await test_payment_reuse(query, payment_header)

                # Poll for result
                job_id = result["job_id"]
                print("⏳ Polling for result...")

                max_polls = 60  # Poll for up to 4 minutes
                poll_interval = 4  # seconds

                for i in range(max_polls):
                    await asyncio.sleep(poll_interval)

                    status_response = await client.get(f"{API_URL}/api/v1/query/{job_id}")
                    status_data = status_response.json()

                    if status_data["status"] == "completed":
                        print(f"   ✅ Completed after ~{(i + 1) * poll_interval}s\n")

                        result = status_data["result"]
                        print("📊 Oracle Result:")
                        print(f"   Final Decision: {result['final_decision'].upper()}")
                        print(f"   Confidence: {result['final_confidence']}")
                        print("\n📝 Explanation:")
                        print(f"{result['explanation']}\n")

                        return status_data
                    elif status_data["status"] == "failed":
                        print(f"   ❌ Job failed: {status_data.get('error')}")
                        sys.exit(1)
                    else:
                        print(f"   Still processing... ({i + 1}/{max_polls})")

                print("   ❌ Timeout waiting for result")
                sys.exit(1)

            else:
                print(
                    f"❌ Request failed with status {response.status_code} (after {elapsed:.2f}s)"
                )
                print(f"   Response: {response.text}")
                sys.exit(1)

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Error after {elapsed:.2f}s: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    # Default test query or use command line argument
    if len(sys.argv) > 1:
        test_query = sys.argv[1]
    else:
        test_query = "Did the Los Angeles Lakers defeat the Sacramento Kings on October 26, 2025?"

    print(f"Testing query: {test_query}\n")
    asyncio.run(test_oracle_query_with_payment(test_query))
