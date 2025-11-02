"""Unit tests for ROFL TEE signing service."""

import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import DecisionType, LLMResponse, OracleResult
from src.signing import SigningService


@pytest.fixture
def mock_private_key():
    """Fixture providing a valid SECP256K1 private key."""
    # Valid 32-byte private key (hex).
    return "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"


@pytest.fixture
def sample_oracle_result():
    """Fixture providing a sample oracle result."""
    return OracleResult(
        query="Test query?",
        final_decision=DecisionType.YES,
        final_confidence=0.85,
        explanation="Test explanation",
        llm_responses=[
            LLMResponse(
                provider="claude",
                model="claude-test",
                decision=DecisionType.YES,
                confidence=0.85,
                reasoning="Test reasoning",
                raw_response="test",
                error=None,
            )
        ],
        total_weight=1.0,
        timestamp=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_initialize_production_mode(mock_private_key):
    """Test signing service initialization in production mode."""
    service = SigningService()

    # Mock RoflClient.
    mock_client = MagicMock()
    mock_client.generate_key = AsyncMock(return_value=mock_private_key)
    mock_client.set_metadata = AsyncMock()

    with (
        patch("src.signing.settings") as mock_settings,
        patch("oasis_rofl_client.RoflClient", return_value=mock_client),
    ):
        mock_settings.debug_signing = False
        mock_settings.environment = "production"

        await service.initialize()

        # Verify key generation was called.
        mock_client.generate_key.assert_called_once()
        call_args = mock_client.generate_key.call_args
        assert call_args[0][0] == "verisage-oracle-key-v1"

        # Verify metadata was set with public key.
        mock_client.set_metadata.assert_called_once()
        metadata = mock_client.set_metadata.call_args[0][0]
        assert "signing_public_key" in metadata
        assert service.public_key_hex is not None


@pytest.mark.asyncio
async def test_initialize_debug_signing_mode():
    """Test signing service uses mock key in debug signing mode."""
    service = SigningService()

    with patch("src.signing.settings") as mock_settings:
        mock_settings.debug_signing = True

        await service.initialize()

        # Verify mock keys were generated.
        assert service.private_key_hex is not None
        assert service.public_key_hex is not None
        assert len(service.private_key_hex) == 64  # 32 bytes hex = 64 chars.


@pytest.mark.asyncio
async def test_initialize_development_mode():
    """Test signing service skips initialization in development mode."""
    service = SigningService()

    with patch("src.signing.settings") as mock_settings:
        mock_settings.debug_signing = False
        mock_settings.environment = "development"

        await service.initialize()

        # Verify no keys were generated.
        assert service.private_key_hex is None
        assert service.public_key_hex is None


@pytest.mark.asyncio
async def test_sign_result_with_debug_signing(sample_oracle_result):
    """Test signing an oracle result with debug signing enabled."""
    service = SigningService()

    with patch("src.signing.settings") as mock_settings:
        mock_settings.debug_signing = True

        await service.initialize()
        signed_result = service.sign_result(sample_oracle_result)

        # Verify signature and public key are present.
        assert signed_result.signature is not None
        assert signed_result.public_key is not None
        assert signed_result.public_key == service.public_key_hex

        # Verify signature is valid hex.
        assert isinstance(signed_result.signature, str)
        bytes.fromhex(signed_result.signature)  # Should not raise.


def test_sign_result_development(sample_oracle_result):
    """Test signing returns unsigned result in development mode."""
    service = SigningService()

    with patch("src.signing.settings") as mock_settings:
        mock_settings.debug_signing = False
        mock_settings.environment = "development"

        result = service.sign_result(sample_oracle_result)

        # Verify no signature was added.
        assert result.signature is None
        assert result.public_key is None


@pytest.mark.asyncio
async def test_signature_verification(sample_oracle_result):
    """Test that signature can be verified with public key."""
    from coincurve import PublicKey

    service = SigningService()

    with patch("src.signing.settings") as mock_settings:
        mock_settings.debug_signing = True

        await service.initialize()
        signed_result = service.sign_result(sample_oracle_result)

        # Recreate the canonical JSON using Pydantic's JSON serialization.
        data_to_verify = signed_result.model_dump(exclude={"signature", "public_key"}, mode="json")
        canonical_json = json.dumps(data_to_verify, sort_keys=True, separators=(",", ":"))
        message_hash = hashlib.sha256(canonical_json.encode()).digest()

        # Verify signature by recovering public key from recoverable signature.
        signature_bytes = bytes.fromhex(signed_result.signature)
        expected_public_key_bytes = bytes.fromhex(signed_result.public_key)

        # Recover public key from signature and verify it matches.
        recovered_pubkey = PublicKey.from_signature_and_message(
            signature_bytes, message_hash, hasher=None
        )
        assert recovered_pubkey.format(compressed=True) == expected_public_key_bytes


def test_derive_public_key(mock_private_key):
    """Test deriving public key from private key."""
    service = SigningService()

    public_key = service._derive_public_key(mock_private_key)

    # Verify it's valid hex.
    public_key_bytes = bytes.fromhex(public_key)

    # Verify it's compressed (33 bytes: 0x02 or 0x03 prefix + 32 bytes).
    assert len(public_key_bytes) == 33
    assert public_key_bytes[0] in (0x02, 0x03)
