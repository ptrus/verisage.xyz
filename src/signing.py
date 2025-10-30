"""ROFL TEE signing service for cryptographic attestation."""

import hashlib
import json
import logging

from src.config import settings
from src.models import OracleResult

logger = logging.getLogger(__name__)


class SigningService:
    """Service for signing oracle results using ROFL keymanager."""

    def __init__(self):
        """Initialize signing service."""
        self.rofl_client = None
        self.private_key_hex = None
        self.public_key_hex = None

    async def initialize(self):
        """Initialize ROFL client and generate signing key (production only)."""
        if settings.debug_signing:
            import secrets

            logger.info("Using mock signing key (DEBUG_SIGNING=true)")
            # Generate a random mock key for testing.
            self.private_key_hex = secrets.token_hex(32)  # 32 bytes = 64 hex chars.
            self.public_key_hex = self._derive_public_key(self.private_key_hex)
            logger.info(f"Mock signing public key: {self.public_key_hex}")
            return

        if settings.environment != "production":
            logger.info("Signing disabled in non-production environment")
            return

        try:
            from oasis_rofl_client import KeyKind, RoflClient

            logger.info("Initializing ROFL client for TEE signing...")
            self.rofl_client = RoflClient()

            # Generate SECP256K1 key using ROFL keymanager.
            # This returns the private key as a hex string.
            logger.info("Generating SECP256K1 signing key...")
            self.private_key_hex = await self.rofl_client.generate_key(
                "verisage-oracle-key-v1", kind=KeyKind.SECP256K1
            )
            logger.info("Signing key generated")

            # Derive public key from private key.
            self.public_key_hex = self._derive_public_key(self.private_key_hex)
            logger.info(f"Public key: {self.public_key_hex}")

            # Upload public key to metadata.
            logger.info("Updating ROFL metadata...")
            await self.rofl_client.set_metadata({"signing_public_key": self.public_key_hex})
            logger.info("Metadata updated")

            logger.info("ROFL signing service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize ROFL signing service: {e}", exc_info=True)
            # Don't raise - allow service to continue without signing.

    def _derive_public_key(self, private_key_hex: str) -> str:
        """Derive SECP256K1 public key from private key.

        Args:
            private_key_hex: Hex-encoded private key

        Returns:
            Hex-encoded compressed public key
        """
        try:
            from coincurve import PrivateKey

            private_key_bytes = bytes.fromhex(private_key_hex)
            privkey = PrivateKey(private_key_bytes)
            pubkey_bytes = privkey.public_key.format(compressed=True)
            return pubkey_bytes.hex()
        except ImportError:
            logger.error("coincurve library not installed, cannot derive public key")
            raise

    def sign_result(self, result: OracleResult) -> OracleResult:
        """Sign an oracle result with ROFL TEE key.

        Args:
            result: The oracle result to sign

        Returns:
            Result with signature and public key fields populated
        """
        if not self.private_key_hex:
            # Signing not initialized - return unsigned result.
            return result

        try:
            from coincurve import PrivateKey

            # Create canonical JSON representation for signing using Pydantic's serialization.
            # Exclude signature and public_key fields from the data being signed.
            # Use mode='json' to ensure datetime objects are properly serialized.
            data_to_sign = result.model_dump(exclude={"signature", "public_key"}, mode="json")
            canonical_json = json.dumps(data_to_sign, sort_keys=True, separators=(",", ":"))

            # Hash the canonical JSON.
            message_hash = hashlib.sha256(canonical_json.encode()).digest()

            # Sign the hash using SECP256K1.
            private_key_bytes = bytes.fromhex(self.private_key_hex)
            privkey = PrivateKey(private_key_bytes)
            signature_bytes = privkey.sign_recoverable(message_hash, hasher=None)
            signature_hex = signature_bytes.hex()

            # Return result with signature.
            return result.model_copy(
                update={"signature": signature_hex, "public_key": self.public_key_hex}
            )

        except Exception as e:
            logger.error(f"Failed to sign result: {e}", exc_info=True)
            # Return unsigned result rather than failing.
            return result


# Global signing service instance.
signing_service = SigningService()
