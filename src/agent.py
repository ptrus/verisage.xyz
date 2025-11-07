"""Agent0 SDK integration for agent registration and discovery."""

import logging
import os
import time
from pathlib import Path

from agent0_sdk import SDK

logger = logging.getLogger(__name__)

# ROFL metadata field name for storing agent ID.
AGENT_ID_METADATA_FIELD = "erc8004_agent_id"

# Lock file to ensure only one worker initializes the agent.
# Use DATA_DIR (persisted volume) so lock works across container restarts and is shared between containers.
DATA_DIR = os.getenv("DATA_DIR", ".")
AGENT_INIT_LOCK_FILE = Path(DATA_DIR) / "agent_init.lock"


def _acquire_init_lock(timeout: int = 30) -> bool:
    """Try to acquire the initialization lock.

    Args:
        timeout: Maximum time to wait for lock in seconds

    Returns:
        True if lock was acquired, False if another worker has it
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Try to create lock file exclusively (fails if it exists).
            fd = os.open(str(AGENT_INIT_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            logger.info(f"Acquired agent initialization lock (PID: {os.getpid()})")
            return True
        except FileExistsError:
            # Lock file exists - check if it's stale (older than 30 seconds).
            # In production, if the lock is older than 30s, it's from a previous deployment.
            try:
                lock_age = time.time() - AGENT_INIT_LOCK_FILE.stat().st_mtime
                if lock_age > 30:  # 30 seconds - enough time for startup
                    logger.warning(f"Removing stale lock file (age: {lock_age:.0f}s)")
                    AGENT_INIT_LOCK_FILE.unlink()
                    continue
            except FileNotFoundError:
                # Lock was removed, try again.
                continue

            # Wait a bit and retry.
            time.sleep(1)

    logger.info("Another worker is handling agent initialization")
    return False


def _release_init_lock():
    """Release the initialization lock."""
    try:
        AGENT_INIT_LOCK_FILE.unlink()
        logger.info(f"Released agent initialization lock (PID: {os.getpid()})")
    except FileNotFoundError:
        pass


async def initialize_agent(
    agent0_chain_id: int,
    agent0_rpc_url: str | None,
    agent0_private_key: str | None,
    agent0_ipfs_provider: str,
    agent0_pinata_jwt: str | None,
    agent_name: str,
    agent_description: str,
    agent_image: str,
    agent_wallet_address: str | None,
    x402_endpoint_url: str,
    force_reregister: bool = False,
) -> tuple[object | None, object | None]:
    """Initialize Agent0 SDK and register agent.

    Args:
        agent0_chain_id: Blockchain chain ID for Agent0
        agent0_rpc_url: RPC URL for blockchain connection
        agent0_private_key: Private key for signing transactions
        agent0_ipfs_provider: IPFS provider URL
        agent0_pinata_jwt: Pinata JWT token for IPFS pinning
        agent_name: Agent name for registration
        agent_description: Agent description
        agent_image: URL to agent image/logo
        agent_wallet_address: Optional wallet address for receiving payments
        x402_endpoint_url: x402 payment endpoint URL
        force_reregister: Force new agent registration (ignore existing agent ID)

    Returns:
        Tuple of (sdk, agent) instances, or (None, None) if not configured
    """
    # Only initialize if Agent0 configuration is provided.
    if not agent0_rpc_url or not agent0_private_key:
        logger.info("Agent0 SDK not configured - skipping agent registration")
        return None, None

    try:
        # Initialize SDK.
        logger.info("Initializing Agent0 SDK...")
        initialized_sdk = SDK(
            chainId=agent0_chain_id,
            rpcUrl=agent0_rpc_url,
            signer=agent0_private_key,
            ipfs=agent0_ipfs_provider,
            pinataJwt=agent0_pinata_jwt,
        )

        # Check if we have an existing agent ID stored in database.
        from src.job_store import job_store

        metadata = job_store.get_all_metadata()
        existing_agent_id = metadata.get(AGENT_ID_METADATA_FIELD)

        # Load or create agent.
        initialized_agent = None
        if existing_agent_id and not force_reregister:
            try:
                logger.info(f"Loading existing agent: {existing_agent_id}")
                initialized_agent = initialized_sdk.loadAgent(existing_agent_id)
            except Exception as e:
                logger.warning(f"Could not load existing agent: {e}")
        elif force_reregister and existing_agent_id:
            logger.info(
                f"Force re-registration enabled - ignoring existing agent ID: {existing_agent_id}"
            )

        if not initialized_agent:
            logger.info("Creating new agent...")
            initialized_agent = initialized_sdk.createAgent(
                name=agent_name,
                description=agent_description,
                image=agent_image,
            )

        # Configure wallet if provided.
        if agent_wallet_address:
            logger.info(f"Setting agent wallet: {agent_wallet_address}")
            initialized_agent.setAgentWallet(agent_wallet_address, chainId=agent0_chain_id)

        # Set trust with reputation and TEE attestation.
        initialized_agent.setTrust(reputation=True, teeAttestation=True)

        # Enable x402 payment support.
        initialized_agent.setX402Support(True)

        # Register x402 endpoint as A2A endpoint.
        logger.info(f"Registering x402 endpoint: {x402_endpoint_url}")
        initialized_agent.setA2A(x402_endpoint_url, version="1.0", auto_fetch=False)

        # Add metadata (optional key-value pairs for discovery).
        initialized_agent.setMetadata(
            {
                "service_type": "oracle",
                "capabilities": "fact-verification,multi-llm-consensus,cryptographic-signing",
                "tee_platform": "oasis-rofl",
            }
        )

        # Set agent as active.
        initialized_agent.setActive(True)

        # Register on-chain with IPFS.
        logger.info("Registering agent on-chain with IPFS...")
        initialized_agent.registerIPFS()

        logger.info(f"Agent registered successfully: {initialized_agent.agentId}")

        # Save agent ID to database for future use.
        # Update if force_reregister is enabled or if there's no existing agent ID.
        if initialized_agent.agentId and (not existing_agent_id or force_reregister):
            from src.job_store import job_store

            job_store.set_metadata_key(AGENT_ID_METADATA_FIELD, initialized_agent.agentId)
            if force_reregister and existing_agent_id:
                logger.info(
                    f"Updated agent ID from {existing_agent_id} to {initialized_agent.agentId}"
                )

        return initialized_sdk, initialized_agent

    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}", exc_info=True)
        return None, None
