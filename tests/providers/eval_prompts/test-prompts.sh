#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PORT=8000
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_CASES="${1:-$SCRIPT_DIR/test_cases_small.json}"
TIMEOUT="${2:-30}"
USE_MOCK="${DEBUG_MOCK:-true}"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Verisage Evaluation Test Runner${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Test cases: ${TEST_CASES}"
echo -e "Timeout: ${TIMEOUT}s"
echo -e "Mock mode: ${USE_MOCK}"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Cleaning up...${NC}"
    cd "$PROJECT_ROOT"

    # Save container logs before shutting down
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOGS_DIR="$SCRIPT_DIR/test_results"
    mkdir -p "$LOGS_DIR"

    echo -e "${BLUE}Saving container logs...${NC}"
    docker compose logs > "$LOGS_DIR/docker_logs_${TIMESTAMP}.txt" 2>&1
    SAVED_LOGS_FILE="$LOGS_DIR/docker_logs_${TIMESTAMP}.txt"

    docker compose down -v 2>/dev/null || true
    echo -e "${GREEN}Cleanup complete${NC}"
}

# Set trap to cleanup on exit
trap cleanup EXIT INT TERM

# Export DEBUG_MOCK for docker compose
export DEBUG_MOCK=$USE_MOCK

# Start services with docker compose
cd "$PROJECT_ROOT"
echo -e "${BLUE}Starting services with docker compose...${NC}"
docker compose up -d --build

# Wait for server to be ready
echo ""
echo -e "${YELLOW}Waiting for server to be ready...${NC}"
MAX_WAIT=30
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -s http://localhost:$PORT/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Server is healthy!${NC}"
        break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
    echo -ne "\r  Waiting... ${ELAPSED}s"
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo -e "\n${RED}✗ Server failed to start within ${MAX_WAIT}s${NC}"
    echo -e "${YELLOW}Container logs:${NC}"
    docker compose logs
    exit 1
fi

echo ""

# Run tests
echo -e "${BLUE}Running evaluation tests...${NC}"
echo ""

if uv run python "$SCRIPT_DIR/test_prompts.py" \
    --test-cases "$TEST_CASES" \
    --output-dir "$SCRIPT_DIR/test_results" \
    --timeout "$TIMEOUT"; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✓ Tests completed successfully!${NC}"
    echo -e "${GREEN}========================================${NC}"
    EXIT_CODE=0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}✗ Some tests failed${NC}"
    echo -e "${RED}========================================${NC}"
    EXIT_CODE=1
fi

# Show where results are saved
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Results Location${NC}"
echo -e "${BLUE}========================================${NC}"

# Find the most recent report and summary files
LATEST_REPORT=$(ls -t "$SCRIPT_DIR/test_results"/report_*.json 2>/dev/null | head -1)
LATEST_SUMMARY=$(ls -t "$SCRIPT_DIR/test_results"/summary_*.txt 2>/dev/null | head -1)
LATEST_DOCKER_LOGS=$(ls -t "$SCRIPT_DIR/test_results"/docker_logs_*.txt 2>/dev/null | head -1)

if [ -n "$LATEST_REPORT" ]; then
    echo -e "📄 JSON Report:    ${LATEST_REPORT}"
fi

if [ -n "$LATEST_SUMMARY" ]; then
    echo -e "📄 Summary:        ${LATEST_SUMMARY}"
fi

if [ -n "$LATEST_DOCKER_LOGS" ]; then
    echo -e "📄 Container Logs: ${LATEST_DOCKER_LOGS}"
fi

exit $EXIT_CODE
