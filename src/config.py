"""Configuration management using pydantic-settings."""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Process type (server or worker) - used for validation.
    process_type: str | None = None  # "server" or "worker", None means both (for tests).

    # Environment (development or production).
    environment: str = "development"

    # Debug modes.
    debug_mock: bool = False  # Use mock LLM clients instead of real APIs.
    debug_payments: bool = False  # Disable x402 payment requirements.
    debug_signing: bool = False  # Disable ROFL signing.

    # API Keys (optional in debug mode).
    claude_api_key: str | None = None
    gemini_api_key: str | None = None
    perplexity_api_key: str | None = None
    openai_api_key: str | None = None

    # LLM Weights (equal by default).
    claude_weight: float = 1.0
    gemini_weight: float = 1.0
    perplexity_weight: float = 1.0
    openai_weight: float = 1.0

    # LLM Model names.
    claude_model: str = "claude-haiku-4-5-20251001"
    gemini_model: str = "gemini-2.0-flash-exp"
    openai_model: str = "gpt-4o"
    perplexity_model: str = "sonar-pro"

    # x402 Payment Configuration (optional if debug_payments=True).
    x402_payment_address: str | None = None
    x402_network: str = "base-sepolia"
    x402_price: str = "$0.1"

    # CDP API Keys for x402 payment facilitator (required in production).
    cdp_api_key_id: str | None = None
    cdp_api_key_secret: str | None = None
    facilitator_url: str = ""  # Custom facilitator URL (empty = use Coinbase default)

    # CORS configuration (comma-separated origins).
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # Proxy configuration.
    behind_cloudflare: bool = False  # Set to true if behind CloudFlare proxy.

    # Worker configuration.
    worker_count: int = 8
    job_retention_count: int = 1000  # Number of jobs to keep in database.

    # Agent0 SDK Configuration (optional).
    agent0_chain_id: int = 84532  # Base Sepolia chain ID.
    agent0_rpc_url: str | None = None
    agent0_private_key: str | None = None
    agent0_ipfs_provider: str = "pinata"
    agent0_pinata_jwt: str | None = None
    agent0_wallet_address: str | None = None
    agent0_force_reregister: bool = False  # Force agent re-registration (ignore existing agent ID).

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_production_settings(self):
        """Ensure production environment has secure settings."""
        is_server = self.process_type in ("server", None)  # None for backward compatibility.
        is_worker = self.process_type in ("worker", None)

        if self.environment == "production":
            # These checks apply to ALL processes.
            if self.debug_payments:
                raise ValueError(
                    "CRITICAL: Cannot run with DEBUG_PAYMENTS=true in production! "
                    "Set DEBUG_PAYMENTS=false or ENVIRONMENT=development"
                )
            if self.debug_mock:
                raise ValueError(
                    "CRITICAL: Cannot run with DEBUG_MOCK=true in production! "
                    "Set DEBUG_MOCK=false or ENVIRONMENT=development"
                )
            if self.debug_signing:
                raise ValueError(
                    "CRITICAL: Cannot run with DEBUG_SIGNING=true in production! "
                    "Set DEBUG_SIGNING=false or ENVIRONMENT=development"
                )

            # Server-only requirements (payment processing).
            if is_server:
                if not self.x402_payment_address:
                    raise ValueError(
                        "CRITICAL: X402_PAYMENT_ADDRESS is required for server in ENVIRONMENT=production"
                    )
                # CDP keys are only required if not using a custom facilitator URL
                if not self.facilitator_url and (
                    not self.cdp_api_key_id or not self.cdp_api_key_secret
                ):
                    raise ValueError(
                        "CRITICAL: CDP_API_KEY_ID and CDP_API_KEY_SECRET are required for server in ENVIRONMENT=production "
                        "(needed for x402 payment facilitator), or set FACILITATOR_URL to use a custom facilitator"
                    )

        # Worker-only requirements (LLM API access) - applies in both dev and prod.
        if is_worker and not self.debug_mock:
            # At least one API key must be provided.
            has_any_key = any(
                [
                    self.claude_api_key,
                    self.gemini_api_key,
                    self.openai_api_key,
                    self.perplexity_api_key,
                ]
            )
            if not has_any_key:
                raise ValueError(
                    "CRITICAL: At least one LLM API key is required for worker when DEBUG_MOCK=false. "
                    "Set CLAUDE_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, or PERPLEXITY_API_KEY"
                )

        return self

    def get_cors_origins(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


# Global settings instance.
settings = Settings()
