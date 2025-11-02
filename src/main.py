"""FastAPI server for Verisage - Multi-LLM Oracle."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from x402.fastapi.middleware import require_payment
from x402.types import HTTPInputSchema, PaywallConfig

from src.config import settings
from src.job_store import job_store
from src.models import (
    JobResponse,
    JobResultResponse,
    JobStatus,
    OracleQuery,
    OracleResult,
)
from src.workers import process_oracle_query

logger = logging.getLogger(__name__)

# Global health status (updated by background task every minute).
health_status = {"status": "healthy", "last_check": None}

# Custom CSS for API docs.
CUSTOM_SWAGGER_CSS = """
body { background: #0a0a0a; }
.swagger-ui { font-family: 'Inter', sans-serif; }
.swagger-ui .topbar { background: #111; border-bottom: 1px solid #222; }
.swagger-ui .topbar .download-url-wrapper { display: none; }
.swagger-ui .info { background: #111; border-bottom: 1px solid #222; margin: 0; padding: 40px; }
.swagger-ui .info .title { color: #e4e4e7; font-family: 'Space Grotesk', sans-serif; font-size: 3em; font-weight: 600; letter-spacing: -0.03em; }
.swagger-ui .info .description p { color: #71717a; font-size: 0.95em; }
.swagger-ui .scheme-container { background: #111; border: none; padding: 20px 40px; border-bottom: 1px solid #222; }
.swagger-ui .opblock-tag { border-bottom: 1px solid #222; color: #a1a1aa; background: transparent; }
.swagger-ui .opblock { background: #111; border: 1px solid #222; border-radius: 0; margin: 0 0 1px 0; }
.swagger-ui .opblock .opblock-summary { background: transparent; border: none; padding: 20px; }
.swagger-ui .opblock.opblock-post { border-left: 3px solid #10b981; }
.swagger-ui .opblock.opblock-get { border-left: 3px solid #10b981; }
.swagger-ui .opblock .opblock-summary-method { background: #10b981; color: #0a0a0a; border-radius: 0; font-weight: 500; }
.swagger-ui .opblock .opblock-summary-path { color: #e4e4e7; }
.swagger-ui .opblock .opblock-summary-description { color: #71717a; }
.swagger-ui .opblock .opblock-section-header { background: #0a0a0a; border-bottom: 1px solid #222; }
.swagger-ui .opblock .opblock-section-header h4 { color: #a1a1aa; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.05em; }
.swagger-ui .opblock-body { background: #0a0a0a; color: #d4d4d8; }
.swagger-ui .parameters-col_description { color: #71717a; }
.swagger-ui .parameter__name { color: #e4e4e7; }
.swagger-ui .parameter__type { color: #10b981; }
.swagger-ui .response-col_status { color: #10b981; }
.swagger-ui .response-col_description { color: #71717a; }
.swagger-ui .btn { border-radius: 0; font-weight: 500; }
.swagger-ui .btn.execute { background: #e4e4e7; color: #0a0a0a; border: none; }
.swagger-ui .btn.execute:hover { background: #fafafa; }
.swagger-ui .btn.cancel { background: transparent; color: #71717a; border: 1px solid #27272a; }
.swagger-ui .btn.cancel:hover { border-color: #10b981; color: #10b981; }
.swagger-ui textarea { background: #0a0a0a; border: 1px solid #27272a; color: #e4e4e7; border-radius: 0; }
.swagger-ui input { background: #0a0a0a; border: 1px solid #27272a; color: #e4e4e7; border-radius: 0; }
.swagger-ui select { background: #0a0a0a; border: 1px solid #27272a; color: #e4e4e7; border-radius: 0; }
.swagger-ui .responses-inner { background: #0a0a0a; }
.swagger-ui .model-box { background: #0a0a0a; border: 1px solid #222; border-radius: 0; }
.swagger-ui .model { color: #d4d4d8; }
.swagger-ui .model-title { color: #e4e4e7; }
.swagger-ui .prop-type { color: #10b981; }
.swagger-ui .prop-format { color: #71717a; }
.swagger-ui table thead tr th { color: #a1a1aa; border-bottom: 1px solid #222; }
.swagger-ui table tbody tr td { color: #d4d4d8; border-bottom: 1px solid #222; }
.swagger-ui .tab li { color: #71717a; }
.swagger-ui .tab li.active { color: #e4e4e7; }
.swagger-ui .markdown p, .swagger-ui .markdown code { color: #d4d4d8; }
"""

# OpenAPI tags metadata.
tags_metadata = [
    {
        "name": "Oracle (Paid)",
        "description": "Submit queries to the multi-LLM oracle. **Requires payment via x402 protocol.**",
    },
    {
        "name": "Oracle",
        "description": "Check status and retrieve results for oracle queries.",
    },
    {
        "name": "Public Feed",
        "description": "Browse recent dispute resolutions submitted by the community.",
    },
    {
        "name": "System",
        "description": "Health checks and system status.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    health_task = None
    if settings.debug_payments or settings.debug_mock:
        logger.warning("=" * 80)
        if settings.debug_payments:
            logger.warning("WARNING: Running with DEBUG_PAYMENTS=true - NO PAYMENT REQUIRED!")
        if settings.debug_mock:
            logger.warning("WARNING: Running with DEBUG_MOCK=true - USING MOCK LLM CLIENTS!")
        logger.warning("=" * 80)

    # Start background task for health status updates.
    health_task = asyncio.create_task(update_health_status_periodically())

    try:
        yield
    finally:
        if health_task:
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass


# Configure FastAPI application.
app = FastAPI(
    title="Verisage",
    description=(
        "Multi-LLM oracle for dispute resolution and fact verification. "
        "All responses are cryptographically signed inside the ROFL TEE using SECP256K1 keys. "
        "Public keys can be verified against on-chain attested state at https://github.com/ptrus/rofl-registry"
    ),
    version="0.1.0",
    docs_url=None,  # Disable default docs.
    redoc_url=None,
    openapi_tags=tags_metadata,
    swagger_ui_parameters={
        "syntaxHighlight.theme": "nord",
        "defaultModelsExpandDepth": 1,
    },
    lifespan=lifespan,
)


# Custom key function for rate limiting.
def get_client_ip(request: Request) -> str:
    """Get client IP, respecting CloudFlare proxy if configured."""
    if settings.behind_cloudflare:
        # Trust CF-Connecting-IP header only when behind CloudFlare.
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip
    # Fall back to direct connection IP.
    return get_remote_address(request)


# Initialize rate limiter.
limiter = Limiter(key_func=get_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Background task to update health status every minute.
async def update_health_status_periodically():
    """Background task that updates health status every 60 seconds."""
    global health_status

    while True:
        try:
            await asyncio.sleep(60)

            stats = job_store.get_recent_job_stats(limit=10)
            queued_count = job_store.get_queued_job_count()

            status = "healthy"
            status_details = {}

            # Check if queue is overloaded.
            if queued_count > 100:
                status = "unhealthy"
                status_details["queue_status"] = "overloaded"
                status_details["queued_jobs"] = queued_count
            elif stats["total"] > 0:
                failure_rate = stats["failed"] / stats["total"]
                # Mark as degraded if >50% of last 10 jobs failed.
                if failure_rate > 0.5:
                    status = "degraded"

            health_status = {
                "status": status,
                "last_check": datetime.now(UTC).isoformat(),
                "recent_jobs": {
                    "total": stats["total"],
                    "failed": stats["failed"],
                },
                "queued_jobs": queued_count,
                **status_details,
            }

        except Exception as e:
            logger.error(f"Health status update failed: {e}", exc_info=True)
            health_status = {
                "status": "unhealthy",
                "last_check": datetime.now(UTC).isoformat(),
                "error": str(e),
            }


# Mount static files.
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create API v1 router.
api_v1 = APIRouter(prefix="/api/v1")

# Configure x402 payment middleware for POST endpoint (if not in debug mode).
if not settings.debug_payments:
    if not settings.x402_payment_address:
        raise ValueError(
            "X402_PAYMENT_ADDRESS is required when DEBUG_PAYMENTS=false. "
            "Set DEBUG_PAYMENTS=true for testing without payments."
        )

    # Create facilitator config for production (required for payment verification infrastructure).
    facilitator_config = None
    if settings.environment == "production":
        from cdp.x402 import create_facilitator_config

        facilitator_config = create_facilitator_config(
            api_key_id=settings.cdp_api_key_id,
            api_key_secret=settings.cdp_api_key_secret,
        )
        logger.info("✓ CDP facilitator configured for production payment verification")

    # Wrap payment middleware to skip OPTIONS requests for CORS.
    payment_middleware = require_payment(
        path="/api/v1/query",
        price=settings.x402_price,
        pay_to_address=settings.x402_payment_address,
        network=settings.x402_network,
        description="Trustless Multi-LLM Dispute Oracle - Get consensus from multiple AI providers on any question. Verifiable/attested code running in Oasis Network ROFL TEE.",
        paywall_config=PaywallConfig(
            app_name="Verisage.xyz",
            app_logo="/static/logo.png",
        ),
        input_schema=HTTPInputSchema(
            body_type="json",
            body_fields={
                "query": {
                    "type": "string",
                    "description": "The dispute question to resolve (10-256 characters, alphanumeric and common punctuation only)",
                    "minLength": 10,
                    "maxLength": 256,
                    "pattern": r'^[a-zA-Z0-9\s.,?!\-\'"":;()/@#$%&+=]+$',
                }
            },
        ),
        output_schema=JobResponse.model_json_schema(),
        facilitator_config=facilitator_config,
    )

    @app.middleware("http")
    async def payment_with_cors(request: Request, call_next):
        """Payment middleware that skips OPTIONS requests for CORS preflight."""
        if request.method == "OPTIONS":
            return await call_next(request)
        response = await payment_middleware(request, call_next)
        # Ensure CORS headers are on 402 responses.
        if response.status_code == 402:
            origin = request.headers.get("origin")
            allowed_origins = settings.get_cors_origins()
            if origin and origin in allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Allow-Methods"] = "*"
                response.headers["Access-Control-Allow-Headers"] = "*"
        return response


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Serve custom styled API documentation."""
    html = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - API Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

    # Inject custom CSS into the HTML.
    html_str = html.body.decode()
    html_str = html_str.replace("</head>", f"<style>{CUSTOM_SWAGGER_CSS}</style></head>")

    return HTMLResponse(content=html_str)


@api_v1.post("/query", response_model=JobResponse, tags=["Oracle (Paid)"])
@limiter.limit("100/minute")
async def query_oracle(query: OracleQuery, request: Request) -> JobResponse:
    """Submit a query to the oracle for processing.

    This endpoint requires payment via the x402 protocol.

    Rate limit: 100 requests per minute per IP.

    **IMPORTANT:** Check the `/health` endpoint before submitting jobs. If the service
    is overloaded (status: "unhealthy"), your payment will be accepted but the job
    will be rejected with HTTP 503. Wait until status returns to "healthy" or "degraded"
    before submitting.

    Args:
        query: The dispute question to resolve
        request: FastAPI request object (for payment info)

    Returns:
        JobResponse with job_id for polling

    Raises:
        HTTPException: If service is overloaded (queue full)
    """
    # Check if service is overloaded before accepting new jobs.
    if health_status.get("status") == "unhealthy":
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Service temporarily overloaded",
                "queue_status": health_status.get("queue_status"),
                "queued_jobs": health_status.get("queued_jobs"),
                "message": "The job queue is currently full. Please try again in a few minutes.",
            },
        )

    # Extract payment info if available (from x402 middleware).
    payer_address = None
    tx_hash = None
    network = None

    try:
        # Extract payment info from x402 middleware
        if hasattr(request.state, "verify_response"):
            verify_resp = request.state.verify_response
            if hasattr(verify_resp, "payer"):
                payer_address = verify_resp.payer

        if hasattr(request.state, "payment_details"):
            payment_details = request.state.payment_details
            if hasattr(payment_details, "network"):
                network = payment_details.network

        # Note: tx_hash is not available from x402 verify response
        # It would only be available in SettleResponse which happens after settlement
    except Exception as e:
        # If payment info extraction fails, continue without it.
        logger.warning(f"Failed to extract payment info: {e}", exc_info=True)

    job_id, created_at = job_store.create_job(
        query.query,
        payer_address=payer_address,
        tx_hash=tx_hash,
        network=network,
    )

    # Enqueue task for background processing.
    process_oracle_query(job_id, query.query)

    return JobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        query=query.query,
        created_at=created_at,
    )


@api_v1.get("/query/{job_id}", response_model=JobResultResponse, tags=["Oracle"])
@limiter.limit("100/minute")
async def get_query_result(job_id: str, request: Request) -> JobResultResponse:
    """Get the status and result of a query job.

    Completed results include cryptographic signatures generated inside the ROFL TEE using a
    SECP256K1 key. The signature and public_key fields can be used to verify the response
    authenticity. The public key can be verified against the on-chain attested state in the
    Oasis ROFL registry: https://github.com/ptrus/rofl-registry

    Args:
        job_id: The job identifier

    Returns:
        JobResultResponse with status and result if completed (including signature and public_key)

    Raises:
        HTTPException: If job not found
    """
    job_data = job_store.get_job(job_id)

    if job_data is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Parse result if completed.
    result = None
    if job_data["result_json"]:
        result = OracleResult.model_validate_json(job_data["result_json"])

    return JobResultResponse(
        job_id=job_data["id"],
        status=JobStatus(job_data["status"]),
        query=job_data["query"],
        result=result,
        error=job_data["error"],
        created_at=datetime.fromisoformat(job_data["created_at"]),
        completed_at=(
            datetime.fromisoformat(job_data["completed_at"]) if job_data["completed_at"] else None
        ),
        payer_address=job_data.get("payer_address"),
        tx_hash=job_data.get("tx_hash"),
        network=job_data.get("network"),
    )


@api_v1.get("/recent", tags=["Public Feed"])
@limiter.limit("100/minute")
async def get_recent_jobs(request: Request, limit: int = 5, exclude_uncertain: bool = True):
    """Get recently completed jobs (public feed).

    Results include cryptographic signatures generated inside the ROFL TEE. The public key
    can be verified against the on-chain attested state to prove response authenticity.

    Args:
        limit: Maximum number of jobs to return (default: 5, max: 20)
        exclude_uncertain: Exclude jobs with uncertain results (default: True)

    Returns:
        List of recent completed jobs with results (including signatures and public keys)
    """
    # Limit to max 20 to prevent abuse.
    limit = min(limit, 20)

    jobs_data = job_store.get_recent_completed_jobs(limit, exclude_uncertain)

    jobs = []
    for job_data in jobs_data:
        result = None
        if job_data["result_json"]:
            result = OracleResult.model_validate_json(job_data["result_json"])

        jobs.append(
            JobResultResponse(
                job_id=job_data["id"],
                status=JobStatus(job_data["status"]),
                query=job_data["query"],
                result=result,
                error=job_data["error"],
                created_at=datetime.fromisoformat(job_data["created_at"]),
                completed_at=(
                    datetime.fromisoformat(job_data["completed_at"])
                    if job_data["completed_at"]
                    else None
                ),
                payer_address=job_data.get("payer_address"),
                tx_hash=job_data.get("tx_hash"),
                network=job_data.get("network"),
            )
        )

    return jobs


# Include v1 API router.
app.include_router(api_v1)


@app.get("/health", tags=["System"])
@limiter.limit("100/minute")
async def health_check(request: Request):
    """Health check endpoint (updated every minute by worker)."""
    return health_status


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
