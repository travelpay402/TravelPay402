"""
TravelPay SDK - HTTP 402 Micropayment Protocol for Solana

A Python library for implementing pay-per-request API monetization
using Solana blockchain payments (SOL & USDC).

Update 5 Features:
- Verifiable Oracle Protocol (Ed25519 signed responses)
- Smart Subscriptions Engine (webhook push notifications)
- Redis high-performance caching

Usage:
    from travelpay import PaymentVerifier, Layer402Middleware, Ledger
    from travelpay import DataSigner, SubscriptionManager  # New in Update 5

    # Initialize components
    ledger = Ledger("payments.db")
    verifier = PaymentVerifier()
    signer = DataSigner()  # Cryptographic signing

    # Add to FastAPI
    app.add_middleware(
        Layer402Middleware,
        ledger=ledger,
        payment_verifier=verifier,
        price_per_request=0.05
    )
    
    # Sign responses for trustless verification
    signed_response = signer.sign_response({"data": "value"})
"""

# Core components
from .payment import PaymentVerifier, VerificationResult, VerificationError
from .middleware import Layer402Middleware
from .ledger import Ledger

# Data agents
from .border_agent import BorderWaitAgent

# Update 5: Oracle & Subscriptions
from .security import DataSigner, SignedEnvelope, OracleKeyManager
from .subscription_manager import (
    SubscriptionManager,
    SubscriptionStore,
    Subscription,
    SubscriptionTarget,
    SubscriptionStatus,
    ConditionEvaluator
)

__version__ = "0.5.0"
__author__ = "TravelPay402"

__all__ = [
    # Core components
    "PaymentVerifier",
    "Layer402Middleware", 
    "Ledger",
    
    # Data agents
    "BorderWaitAgent",
    
    # Payment types
    "VerificationResult",
    "VerificationError",
    
    # Update 5: Oracle (Cryptographic Signing)
    "DataSigner",
    "SignedEnvelope",
    "OracleKeyManager",
    
    # Update 5: Subscriptions (Push Notifications)
    "SubscriptionManager",
    "SubscriptionStore",
    "Subscription",
    "SubscriptionTarget",
    "SubscriptionStatus",
    "ConditionEvaluator",
    
    # Metadata
    "__version__",
]
