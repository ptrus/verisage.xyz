#!/bin/bash
set -e

echo "=== Verisage E2E Payment Test ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PORT=8000
MAX_WAIT=30
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load environment variables
# Load client config from tests/e2e/.env (for PRIVATE_KEY)
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Load server config from tests/e2e/.env.test-payments (for payment testing)
if [ -f "$SCRIPT_DIR/.env.test-payments" ]; then
    set -a
    source "$SCRIPT_DIR/.env.test-payments"
    set +a
fi

# Check for required environment variables
if [ -z "$PRIVATE_KEY" ]; then
    echo -e "${RED}❌ Error: PRIVATE_KEY environment variable not set${NC}"
    echo "   Please set PRIVATE_KEY in tests/e2e/.env with a funded Base Sepolia wallet"
    echo "   See tests/e2e/.env.example for template"
    exit 1
fi

# Set default payment address for Base Sepolia testing if not provided
if [ -z "$X402_PAYMENT_ADDRESS" ]; then
    X402_PAYMENT_ADDRESS="0xe9Ee0938479fFf5B58a367EA918561Ed97B6f57D"
    echo -e "${YELLOW}Using default payment address for testing: $X402_PAYMENT_ADDRESS${NC}"
fi

echo -e "${BLUE}Payment Configuration:${NC}"
echo "  Network: $X402_NETWORK"
echo "  Price: $X402_PRICE"
echo "  Payment Address: $X402_PAYMENT_ADDRESS"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Cleaning up...${NC}"
    cd "$PROJECT_ROOT"
    docker compose --env-file tests/e2e/.env.test-payments down -v 2>/dev/null || true
    echo -e "${GREEN}Cleanup complete${NC}"
}

# Set trap to cleanup on exit
trap cleanup EXIT

cd "$PROJECT_ROOT"

echo -e "${BLUE}1. Building and starting services with docker compose (payment mode)...${NC}"
docker compose --env-file tests/e2e/.env.test-payments up -d --build

echo ""
echo -e "${BLUE}2. Waiting for server to be ready...${NC}"
WAIT_COUNT=0
until curl -s http://localhost:$PORT/health > /dev/null 2>&1; do
    WAIT_COUNT=$((WAIT_COUNT + 1))
    if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
        echo -e "${RED}✗ Server failed to start after ${MAX_WAIT}s${NC}"
        echo ""
        echo "Container logs:"
        docker compose logs
        exit 1
    fi
    sleep 1
    echo -n "."
done
echo ""
echo -e "${GREEN}✓ Server is ready${NC}"

echo ""
echo -e "${BLUE}3. Running payment flow test...${NC}"
echo ""

# Run the Python payment test using uv
cd "$SCRIPT_DIR"
API_URL="http://localhost:$PORT" uv run test_payments.py

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Payment test completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
