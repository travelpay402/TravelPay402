"""
TravelPay SDK - Cryptographic Security Module
Ed25519 digital signatures for Verifiable Oracle Protocol.

This module enables trustless data verification by signing all API responses
with the server's private key. Clients can verify data authenticity on-chain
or independently without trusting the API server.
"""

import os
import json
import time
import hashlib
import logging
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict

from nacl.signing import SigningKey, VerifyKey
from nacl.encoding import HexEncoder
from nacl.exceptions import BadSignatureError

logger = logging.getLogger("travelpay.security")


@dataclass
class SignedEnvelope:
    """
    Cryptographic envelope wrapping API response data.
    
    Attributes:
        data: The original response payload
        signature: Ed25519 signature (hex-encoded)
        timestamp: Unix timestamp of signature creation
        provider_pubkey: Public key for verification (hex-encoded)
        data_hash: SHA-256 hash of the data (hex-encoded)
    """
    data: Any
    signature: str
    timestamp: int
    provider_pubkey: str
    data_hash: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert envelope to dictionary for JSON serialization."""
        return asdict(self)


class DataSigner:
    """
    Ed25519 cryptographic signer for API responses.
    
    Implements the Verifiable Oracle Protocol by:
    1. Hashing the response data (SHA-256)
    2. Signing the hash with Ed25519 private key
    3. Wrapping response in SignedEnvelope with verification metadata
    
    The signing key is loaded from environment or generated fresh.
    For production, persist ORACLE_PRIVATE_KEY in .env to maintain key continuity.
    
    Example:
        signer = DataSigner()
        
        # Sign API response
        response_data = {"wait_time": 25, "crossing": "San Ysidro"}
        signed = signer.sign_response(response_data)
        
        # Result includes verification metadata
        # {
        #     "data": {"wait_time": 25, "crossing": "San Ysidro"},
        #     "signature": "a1b2c3...",
        #     "timestamp": 1699999999,
        #     "provider_pubkey": "d4e5f6...",
        #     "data_hash": "789abc..."
        # }
        
        # Verify elsewhere
        is_valid = DataSigner.verify_signature(
            data=signed["data"],
            signature=signed["signature"],
            pubkey_hex=signed["provider_pubkey"],
            data_hash=signed["data_hash"]
        )
    """
    
    def __init__(self, private_key_hex: Optional[str] = None):
        """
        Initialize the DataSigner.
        
        Args:
            private_key_hex: Ed25519 private key in hex format.
                            If None, loads from ORACLE_PRIVATE_KEY env var.
                            If env var empty, generates new keypair.
        """
        key_hex = private_key_hex or os.getenv("ORACLE_PRIVATE_KEY", "")
        
        if key_hex:
            # Load existing key
            try:
                seed = bytes.fromhex(key_hex)
                self._signing_key = SigningKey(seed)
                logger.info("Loaded Oracle signing key from configuration")
            except Exception as e:
                logger.error(f"Invalid ORACLE_PRIVATE_KEY, generating new: {e}")
                self._signing_key = SigningKey.generate()
        else:
            # Generate new keypair
            self._signing_key = SigningKey.generate()
            logger.warning("Generated new Oracle signing key (persist for production)")
            logger.info(f"Export with: ORACLE_PRIVATE_KEY={self.export_private_key()}")
        
        self._verify_key = self._signing_key.verify_key
        self._pubkey_hex = self._verify_key.encode(encoder=HexEncoder).decode('ascii')
        
        logger.info(f"Oracle Public Key: {self._pubkey_hex[:16]}...{self._pubkey_hex[-16:]}")
    
    @property
    def public_key_hex(self) -> str:
        """Get the public key in hex format for external verification."""
        return self._pubkey_hex
    
    def export_private_key(self) -> str:
        """
        Export private key seed in hex format.
        
        WARNING: Keep this secret! Only use for backup/migration.
        """
        return self._signing_key.encode(encoder=HexEncoder).decode('ascii')
    
    @staticmethod
    def _canonicalize_data(data: Any) -> bytes:
        """
        Convert data to canonical byte representation for hashing.
        Uses sorted JSON to ensure consistent hashing.
        """
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        return json_str.encode('utf-8')
    
    @staticmethod
    def _hash_data(data: Any) -> str:
        """
        Compute SHA-256 hash of data in canonical form.
        Returns hex-encoded hash string.
        """
        canonical = DataSigner._canonicalize_data(data)
        return hashlib.sha256(canonical).hexdigest()
    
    def sign_response(self, data: Any, include_timestamp: bool = True) -> Dict[str, Any]:
        """
        Sign response data and wrap in verification envelope.
        
        Args:
            data: The response payload to sign (dict, list, or primitive)
            include_timestamp: Whether to include signing timestamp
            
        Returns:
            SignedEnvelope as dictionary with signature metadata
        """
        timestamp = int(time.time()) if include_timestamp else 0
        
        # Hash the data
        data_hash = self._hash_data(data)
        
        # Create message to sign: hash + timestamp
        message = f"{data_hash}:{timestamp}".encode('utf-8')
        
        # Sign with Ed25519
        signed = self._signing_key.sign(message, encoder=HexEncoder)
        signature = signed.signature.decode('ascii')
        
        envelope = SignedEnvelope(
            data=data,
            signature=signature,
            timestamp=timestamp,
            provider_pubkey=self._pubkey_hex,
            data_hash=data_hash
        )
        
        return envelope.to_dict()
    
    def verify_own_signature(self, envelope: Dict[str, Any]) -> bool:
        """
        Verify a signature created by this signer instance.
        
        Args:
            envelope: SignedEnvelope dictionary from sign_response()
            
        Returns:
            True if signature is valid, False otherwise
        """
        return self.verify_signature(
            data=envelope.get("data"),
            signature=envelope.get("signature", ""),
            pubkey_hex=envelope.get("provider_pubkey", ""),
            data_hash=envelope.get("data_hash", ""),
            timestamp=envelope.get("timestamp", 0)
        )
    
    @staticmethod
    def verify_signature(
        data: Any,
        signature: str,
        pubkey_hex: str,
        data_hash: str,
        timestamp: int = 0
    ) -> bool:
        """
        Verify a signed envelope from any DataSigner instance.
        
        This static method can be used by clients to verify data
        without having access to the private key.
        
        Args:
            data: The original response data
            signature: Hex-encoded Ed25519 signature
            pubkey_hex: Hex-encoded public key
            data_hash: SHA-256 hash of the data
            timestamp: Unix timestamp from envelope
            
        Returns:
            True if signature is valid and data hash matches
        """
        try:
            # Verify data hash
            computed_hash = DataSigner._hash_data(data)
            if computed_hash != data_hash:
                logger.warning("Data hash mismatch - data may be tampered")
                return False
            
            # Reconstruct signed message
            message = f"{data_hash}:{timestamp}".encode('utf-8')
            
            # Verify signature
            verify_key = VerifyKey(bytes.fromhex(pubkey_hex))
            signature_bytes = bytes.fromhex(signature)
            
            verify_key.verify(message, signature_bytes)
            return True
            
        except BadSignatureError:
            logger.warning("Invalid signature - verification failed")
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False


class OracleKeyManager:
    """
    Manages Oracle signing keys with rotation support.
    
    For production deployments requiring key rotation without downtime.
    """
    
    def __init__(self):
        self._primary_signer: Optional[DataSigner] = None
        self._previous_signers: list[DataSigner] = []
    
    def initialize(self, private_key_hex: Optional[str] = None) -> DataSigner:
        """Initialize or replace the primary signing key."""
        if self._primary_signer:
            # Keep old key for verification during transition
            self._previous_signers.append(self._primary_signer)
            # Limit history
            if len(self._previous_signers) > 5:
                self._previous_signers.pop(0)
        
        self._primary_signer = DataSigner(private_key_hex)
        return self._primary_signer
    
    @property
    def signer(self) -> Optional[DataSigner]:
        """Get the current primary signer."""
        return self._primary_signer
    
    def get_all_public_keys(self) -> list[str]:
        """Get all valid public keys (current + recent previous)."""
        keys = []
        if self._primary_signer:
            keys.append(self._primary_signer.public_key_hex)
        for s in self._previous_signers:
            keys.append(s.public_key_hex)
        return keys
