"""Pydantic models for request/response validation."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class DecisionType(str, Enum):
    """Possible decision types from LLM."""

    YES = "yes"
    NO = "no"
    UNCERTAIN = "uncertain"


class LLMResponse(BaseModel):
    """Response from a single LLM backend."""

    provider: str = Field(..., description="LLM provider name (claude, gemini, perplexity)")
    model: str = Field(..., description="Model name used (e.g., claude-haiku-4-5-20251001, gpt-4o)")
    decision: DecisionType = Field(..., description="The LLM's decision")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)")
    reasoning: str = Field(..., description="Explanation for the decision")
    raw_response: str = Field(..., description="Raw text response from LLM")
    error: str | None = Field(None, description="Error message if request failed")


class OracleQuery(BaseModel):
    """Input query for the oracle."""

    query: str = Field(
        ...,
        min_length=10,
        max_length=256,
        pattern=r'^[a-zA-Z0-9\s.,?!\-\'"":;()/@#$%&+=]+$',
        description="The dispute question to resolve (alphanumeric and common punctuation only)",
    )


class OracleResult(BaseModel):
    """Aggregated result from all LLM backends."""

    query: str = Field(..., description="The original query")
    final_decision: DecisionType = Field(..., description="Weighted final decision")
    final_confidence: float = Field(..., ge=0.0, le=1.0, description="Aggregated confidence score")
    explanation: str = Field(..., description="Summary of how decision was reached")
    llm_responses: list[LLMResponse] = Field(..., description="Individual LLM responses")
    total_weight: float = Field(..., description="Total weight used in calculation")
    timestamp: datetime = Field(..., description="UTC timestamp when the result was generated")
    signature: str | None = Field(
        None,
        description="Recoverable ECDSA signature (hex) over the canonical JSON representation of the result. Generated inside the ROFL TEE using a SECP256K1 key.",
    )
    public_key: str | None = Field(
        None,
        description="Compressed SECP256K1 public key (hex) used for signing. Can be verified against the on-chain attested state in the Oasis ROFL registry (https://github.com/ptrus/rofl-registry).",
    )


class JobStatus(str, Enum):
    """Job processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobResponse(BaseModel):
    """Response when creating a new job."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    query: str = Field(..., description="The submitted query")
    created_at: datetime = Field(..., description="Job creation timestamp")


class JobResultResponse(BaseModel):
    """Response when polling for job results."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status")
    query: str = Field(..., description="The original query")
    result: OracleResult | None = Field(None, description="Oracle result if completed")
    error: str | None = Field(None, description="Error message if job failed")
    created_at: datetime = Field(..., description="Job creation timestamp")
    completed_at: datetime | None = Field(None, description="Job completion timestamp")
    payer_address: str | None = Field(None, description="Address of the payer")
    tx_hash: str | None = Field(None, description="Transaction hash of the payment")
    network: str | None = Field(None, description="Network the payment was made on")
