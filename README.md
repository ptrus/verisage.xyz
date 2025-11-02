# Verisage.xyz

**Verifiable Multi-LLM Oracle for Truth Verification**

Verisage answers objective yes/no questions by querying multiple independent AI providers (Claude, Gemini, Perplexity, OpenAI) and aggregating their responses with weighted voting. Designed as a trustless resolution mechanism for protocols requiring factual verification—an AI-powered alternative to human-based dispute systems like UMA.

Built for deployment on [Oasis ROFL](https://docs.oasis.io/rofl/), the service will provide cryptographic attestation that proves the exact code executing in the TEE.

**Live deployment:**
- Demo UI: https://verisage.xyz
- API for agents: https://api.verisage.xyz

---

## Why ROFL

Protocols using oracles for resolution (like prediction markets, insurance, derivatives) need trustless verification. ROFL provides this:

- **Remote attestation** – cryptographically proves the exact Docker image running in the TEE
- **Verifiable execution** – anyone can confirm the exact code running matches this repository
- **Tamper-proof execution** – operators cannot modify code or manipulate results

Built for ROFL from day one: reproducible builds, transparent operation, no trust assumptions.

---

## Key Features

**Multi-Provider Consensus**
- Concurrent queries to 4+ LLM providers with grounding/web-search enabled
- Real-time data access: all providers query up-to-date information from the web
- Weighted voting with configurable thresholds
- Full transparency: individual responses, reasoning, confidence scores

**x402 Micropayments**
- Pay-per-query via browser UI or via API directly
- Can be used by other AI agents for factual checks and verification
- Listed on [x402scan.com](https://www.x402scan.com/resources) (coming soon)

**Verifiable & Auditable**
- Complete source code open and auditable
- Reproducible Docker builds ensure deployed code matches repository
- ROFL attestation provides cryptographic proof of execution integrity
- Cryptographic signatures on all responses using TEE-generated SECP256K1 keys
- Public key verification against on-chain attested state

---

## Running Locally

```bash
# Configure
cp .env.example .env
# Add API keys or set DEBUG_MOCK=true

# Start
docker compose up --build

# Access
open http://localhost:8000
```

**Testing:**
```bash
# Basic E2E (mock providers, no payments)
bash tests/e2e/test-e2e.sh

# Payment E2E (mock providers, real x402 payments on Base Sepolia)
bash tests/e2e/test-e2e-payments.sh
```

---

## API Reference

**Submit Query**
```http
POST /api/query
X-PAYMENT: <base64-payment-proof>

{"query": "Did the Lakers win the 2020 NBA Championship?"}
```

**Poll Results**
```http
GET /api/query/{job_id}
```

**Recent Queries**
```http
GET /api/recent?limit=10
```

Full API docs at `/docs`

---

## Verifying the Deployment

Anyone can verify that the deployed on-chain code measurement matches this repository's source code using the Oasis CLI:

```bash
oasis rofl build --verify --deployment verisage
```

This command builds the Docker image from source and compares the enclave identity across three layers:
- Built enclave identity (from local build)
- Manifest enclave identity (from deployment config)
- On-chain enclave identity (from ROFL registry)

**Expected output:**
```
✓ Built enclave identities MATCH latest manifest enclave identities
✓ Manifest enclave identities MATCH on-chain enclave identities
```

This proves the exact code running in the TEE corresponds to this repository.

The Oasis Consensus Network continuously ensures that the on-chain enclave identities match the running ones, providing ongoing verification of execution integrity.

### Verifying Response Signatures

All oracle responses are cryptographically signed using a SECP256K1 key generated inside the ROFL TEE. Each response includes:
- `signature` - Recoverable ECDSA signature over the canonical JSON representation of the result
- `public_key` - The compressed public key used for signing

**How to verify a response came from the oracle:**

1. **Get the oracle's published public key** from the Oasis Network chain:
   - Via [Oasis Explorer](https://explorer.oasis.io/) (search for the ROFL app)
   - Via Oasis CLI: `oasis rofl show verisage`
   - Via [rofl-registry](https://github.com/ptrus/rofl-registry) example code

2. **Verify the response signature** matches the public key:
   - The `public_key` field in the response should match the on-chain published key
   - Verify the `signature` is valid for the response data using the public key
   - This proves the response was generated inside the TEE, not modified by operators

**Example verification** (see `rofl-registry` for complete code):
```python
from eth_account.messages import encode_defunct
from eth_keys import keys

# Get response from oracle
response = oracle_response['result']
signature = response['signature']
public_key = response['public_key']

# Verify signature matches the data
message_hash = hash_oracle_result(response)
recovered_pubkey = keys.Signature(bytes.fromhex(signature)).recover_public_key_from_msg_hash(message_hash)

assert recovered_pubkey.to_compressed_bytes().hex() == public_key
```

For complete verification examples and details on the ROFL registry, see:
**https://github.com/ptrus/rofl-registry**

---

## How Can I Trust This Service?

Verisage is designed for complete verifiability. You don't need to trust the operators—you can verify everything yourself:

### 1. Audit the Source Code

The entire codebase is open source and auditable. Key trust properties you can verify:

- **No caching** - Every request queries all AI models in real-time. Check `src/workers/oracle_worker.py` to verify no response caching exists.
- **You get what you pay for** - All configured providers are queried for every request. No shortcuts, no substitutions.
- **Transparent scoring** - The weighted voting logic in `src/scoring.py` is fully visible and auditable.
- **No hidden logic** - All LLM provider clients in `src/llm_clients/` show exactly what prompts are sent and how responses are processed.

### 2. Verify the Docker Image

Verisage uses reproducible builds. You can verify the deployed Docker image matches this exact source code:

```bash
# Build locally with reproducible settings
./scripts/build_and_push_container_image.sh

# Compare your build's SHA256 with the deployed image
# (check docker-compose.yaml or deployment config for the deployed SHA256)
```

The built image SHA256 should exactly match the deployed image SHA256. This proves no code has been modified.

**Alternative:** Check the `docker-reproducibility` CI job (coming soon) to see automated verification.

### 3. Verify the ROFL Enclave

The ultimate verification: confirm the code running inside the TEE matches this repository.

```bash
# Build the entire ROFL app locally and verify measurements
oasis rofl build --verify --deployment verisage
```

This verifies that the enclave identity (code measurements) match across:
- Your local build from source
- The deployment manifest
- The on-chain attested state

**Alternative:** Check the `rofl-reproducibility` CI job (coming soon) for automated verification.

### 4. Ongoing Attestation

The Oasis Network continuously verifies that the running code matches the on-chain attestation:

- ROFL apps must periodically prove they're running the correct code
- The network automatically rejects apps that fail attestation
- All attestations are publicly verifiable on-chain

Learn more about continuous attestation at the [ROFL Registry](https://github.com/ptrus/rofl-registry).

### Trust Model Summary

**You don't need to trust:**
- The service operators
- That the correct code is running
- That responses haven't been manipulated
- That the service queries all providers as claimed

**You only need to trust:**
- The Oasis Network's TEE attestation mechanism
- The open source code you've audited
- The cryptographic primitives (ECDSA signatures, SGX/TDX attestation)

Everything else is verifiable.

---

## Development

**Prerequisites:**
- Python 3.11+ with [uv](https://docs.astral.sh/uv/) package manager
- Node.js 20+ for frontend development
- Docker for container builds

**Setup:**
```bash
# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend-src && npm install
```

**Frontend Development:**
```bash
cd frontend-src
npm run dev  # Starts dev server at http://localhost:3000
```

**Run Linting:**
```bash
uv run ruff check src/      # Check for issues
uv run ruff format src/      # Format code
```

**Build Container:**
```bash
./scripts/build_and_push_container_image.sh
```

**Add LLM Provider:** Create client in `src/llm_clients/`, inherit from `BaseLLMClient`
**Modify Scoring:** Edit `src/scoring.py` weighted voting logic

---

## Links

- **Live Service:** https://verisage.xyz
- **Oasis ROFL:** https://docs.oasis.io/rofl/
- **x402 Protocol:** https://x402.org

---

Built for trustless AI verification on Oasis Network.
