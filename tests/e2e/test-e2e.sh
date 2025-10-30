#!/bin/bash
set -e

echo "=== Verisage E2E Test ==="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PORT=8000
MAX_WAIT=30
POLL_INTERVAL=2
MAX_POLLS=15
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    cd "$PROJECT_ROOT"
    docker compose --env-file tests/e2e/.env.test-mock down -v 2>/dev/null || true
}

# Set trap to cleanup on exit
trap cleanup EXIT

cd "$PROJECT_ROOT"

echo "1. Building and starting services with docker compose (mock mode)..."
docker compose --env-file tests/e2e/.env.test-mock up -d --build

echo ""
echo "2. Waiting for server to be ready..."
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
echo "3. Submitting test query..."
RESPONSE=$(curl -s -X POST http://localhost:$PORT/api/v1/query \
    -H "Content-Type: application/json" \
    -d '{"query": "Did the Lakers win the 2020 NBA Championship?"}')

echo "Response: $RESPONSE"

# Extract job_id using grep and sed (more portable than jq)
JOB_ID=$(echo "$RESPONSE" | grep -o '"job_id":"[^"]*"' | sed 's/"job_id":"\([^"]*\)"/\1/')

if [ -z "$JOB_ID" ]; then
    echo -e "${RED}✗ Failed to get job_id from response${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Got job_id: $JOB_ID${NC}"

echo ""
echo "4. Polling for results..."
POLL_COUNT=0
while [ $POLL_COUNT -lt $MAX_POLLS ]; do
    POLL_COUNT=$((POLL_COUNT + 1))

    RESULT=$(curl -s http://localhost:$PORT/api/v1/query/$JOB_ID)
    STATUS=$(echo "$RESULT" | grep -o '"status":"[^"]*"' | head -1 | sed 's/"status":"\([^"]*\)"/\1/')

    echo "  Poll $POLL_COUNT: status=$STATUS"

    if [ "$STATUS" = "completed" ]; then
        echo -e "${GREEN}✓ Job completed${NC}"
        echo ""
        echo "5. Validating result..."

        # Check if result field exists and has content
        if echo "$RESULT" | grep -q '"result":{' ; then
            echo -e "${GREEN}✓ Result field present${NC}"

            # Check for expected mock response fields
            if echo "$RESULT" | grep -q '"final_decision"' && \
               echo "$RESULT" | grep -q '"final_confidence"' && \
               echo "$RESULT" | grep -q '"explanation"' && \
               echo "$RESULT" | grep -q '"llm_responses"' ; then
                echo -e "${GREEN}✓ All required fields present${NC}"

                # Check for mock provider
                if echo "$RESULT" | grep -q '"provider":"mock"' ; then
                    echo -e "${GREEN}✓ Mock provider used${NC}"
                else
                    echo -e "${YELLOW}⚠ Mock provider not found in response${NC}"
                fi

                echo ""
                echo -e "${GREEN}=== E2E TEST PASSED ===${NC}"
                echo ""
                echo "Full result:"
                echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"
                exit 0
            else
                echo -e "${RED}✗ Missing required fields in result${NC}"
                echo "Result: $RESULT"
                exit 1
            fi
        else
            echo -e "${RED}✗ No result field in response${NC}"
            echo "Response: $RESULT"
            exit 1
        fi
    elif [ "$STATUS" = "failed" ]; then
        echo -e "${RED}✗ Job failed${NC}"
        echo "Response: $RESULT"
        exit 1
    fi

    sleep $POLL_INTERVAL
done

echo -e "${RED}✗ Job did not complete within expected time${NC}"
echo "Last response: $RESULT"
exit 1
