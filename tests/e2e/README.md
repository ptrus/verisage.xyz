# E2E Tests

This directory contains end-to-end tests for Verisage.

## Tests

### 1. Basic E2E Test (Mock Mode)
Tests the basic flow without payments using mock LLM providers.

```bash
./test-e2e.sh
```

**What it tests:**
- Server and worker container startup
- Job submission and polling
- Mock LLM responses
- Result validation

**Requirements:**
- Docker and docker compose

---

### 2. Payment E2E Test (Real Payments)
Tests the complete x402 payment flow on Base Sepolia.

```bash
./test-e2e-payments.sh
```

**What it tests:**
1. Request without payment (should get 402 Payment Required)
2. Request with insufficient payment (max_value too low, should fail)
3. Request with automatic payment handling via x402HttpxClient
4. Payment verification and transaction on Base Sepolia
5. Payment reuse prevention (should fail)
6. Oracle query processing with real LLM providers
7. Result polling and validation

**Requirements:**

1. **Server Configuration (`/project-root/.env`):**
   - Configure LLM API keys (required)
   - Payment address is optional (defaults to 0xe9Ee0938479fFf5B58a367EA918561Ed97B6f57D for testing)
   - See main `.env.example` for reference
   ```bash
   # In project root .env
   DEBUG_MOCK=false
   DEBUG_PAYMENTS=false
   X402_PAYMENT_ADDRESS=0xe9Ee0938479fFf5B58a367EA918561Ed97B6f57D  # Optional, this is the default for testing
   X402_NETWORK=base-sepolia
   X402_PRICE=$0.001                  # Lower price for testing
   CLAUDE_API_KEY=sk-ant-...
   GEMINI_API_KEY=AI...
   ```

2. **Client Configuration (`tests/e2e/.env`):**
   - Create `.env` file in `tests/e2e/` directory
   - Copy from `tests/e2e/.env.example`
   ```bash
   # In tests/e2e/.env
   PRIVATE_KEY=0x...                  # Funded Base Sepolia wallet
   API_URL=http://localhost:8000      # Optional, defaults to localhost:8000
   ```

3. **Funded Base Sepolia Wallet:**
   - Get Base Sepolia ETH from faucet: https://www.coinbase.com/faucets/base-ethereum-sepolia-faucet
   - Add private key to `tests/e2e/.env` (NOT the main .env!)

4. **Python Dependencies:**
   ```bash
   uv pip install x402 eth-account httpx python-dotenv
   ```

**File Structure:**
```
project-root/
├── .env                    # Server config (PAYMENT_ADDRESS, API keys)
└── tests/e2e/
    ├── .env                # Client config (PRIVATE_KEY for testing)
    └── .env.example        # Template for client .env
```

---

## Running Tests Locally

### Mock Mode (No Payments)
```bash
# From project root
cd tests/e2e
./test-e2e.sh
```

### Payment Mode (With Real Payments)
```bash
# From project root
# 1. Set up .env with PRIVATE_KEY and PAYMENT_ADDRESS
# 2. Fund your Base Sepolia wallet
# 3. Run test
cd tests/e2e
./test-e2e-payments.sh
```

### Custom Query (Payment Test)
```bash
# Test with a specific query
cd tests/e2e
API_URL="http://localhost:8000" python3 test_payments.py "Did Bitcoin reach $100k in 2024?"
```

---

## Test Output

Both tests provide colored output:
- 🔒 Security tests (payment verification)
- ✅ Success indicators
- ❌ Error indicators
- 📊 Result summaries

The payment test shows:
- Wallet address being used
- Payment transaction details
- Oracle processing status
- Final decision and confidence score
- Detailed explanation from LLM consensus

---

## Troubleshooting

**402 Payment Required even with x402HttpxClient:**
- Check that PRIVATE_KEY is set correctly in `tests/e2e/.env`
- Ensure wallet has sufficient Base Sepolia ETH
- PAYMENT_ADDRESS uses default test address (0xe9Ee0938479fFf5B58a367EA918561Ed97B6f57D) if not specified

**Test times out:**
- LLM API might be slow or rate-limited
- Check container logs: `docker compose logs`
- Increase poll timeout in test script

**Payment reuse test fails:**
- This is expected! Payment reuse should be rejected
- If it succeeds, there's a security issue

---

## CI/CD Integration

For automated testing in CI/CD:
- Use `test-e2e.sh` (mock mode, no payments)
- Payment tests require funded wallet (not suitable for public CI)
- Consider running payment tests on scheduled basis with secret management
