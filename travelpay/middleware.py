"""
TravelPay SDK - Layer 402 Middleware
FastAPI middleware for HTTP 402 Payment Required protocol.
"""

import os
import logging
from typing import Callable, Set

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv

from .payment import PaymentVerifier, VerificationError
from .ledger import Ledger

load_dotenv()

logger = logging.getLogger("travelpay.middleware")


class Layer402Middleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that enforces HTTP 402 Payment Required protocol.
    
    Implements a freemium model with Solana payments:
    1. New users get free credits (welcome bonus)
    2. Credits are deducted per request
    3. When exhausted, users must pay with SOL or USDC
    
    Args:
        app: FastAPI application instance
        ledger: Ledger instance for tracking user balances
        payment_verifier: PaymentVerifier instance for on-chain verification
        price_per_request: USD price per API request
        welcome_bonus: USD credits given to new users
        exclude_paths: Set of paths that don't require payment
    
    Example:
        from travelpay import Layer402Middleware, Ledger, PaymentVerifier
        
        ledger = Ledger("payments.db")
        verifier = PaymentVerifier(merchant_wallet="...")
        
        app.add_middleware(
            Layer402Middleware,
            ledger=ledger,
            payment_verifier=verifier,
            price_per_request=0.05,
            exclude_paths={"/", "/docs", "/health"}
        )
    """
    
    DEFAULT_EXCLUDED_PATHS = {
        "/", "/docs", "/openapi.json", "/redoc", "/health", 
        "/balance", "/static", "/favicon.ico", "/oracle-key"
    }
    
    def __init__(
        self, 
        app,
        ledger: Ledger,
        payment_verifier: PaymentVerifier,
        price_per_request: float = None,
        welcome_bonus: float = None,
        exclude_paths: Set[str] = None
    ):
        super().__init__(app)
        self.ledger = ledger
        self.payment_verifier = payment_verifier
        
        # Configuration
        self.price_per_request = price_per_request or float(os.getenv("PRICE_PER_REQUEST_USD", "0.05"))
        self.welcome_bonus = welcome_bonus or float(os.getenv("WELCOME_BONUS_USD", "2.00"))
        self.exclude_paths = exclude_paths or self.DEFAULT_EXCLUDED_PATHS
        
        logger.info(f"Layer402 Middleware initialized:")
        logger.info(f"  - Price: ${self.price_per_request}/request")
        logger.info(f"  - Welcome bonus: ${self.welcome_bonus}")
        logger.info(f"  - Accepted: SOL, USDC")

    def _should_skip_payment(self, request: Request) -> bool:
        """Check if the request path is excluded from payment."""
        path = request.url.path
        
        if path in self.exclude_paths:
            return True
        
        for excluded in self.exclude_paths:
            if path.startswith(excluded.rstrip("/") + "/"):
                return True
        
        return False

    async def dispatch(self, request: Request, call_next: Callable):
        """Process each request through the payment middleware."""
        
        if self._should_skip_payment(request):
            return await call_next(request)
        
        try:
            access_granted = await self._check_access(request)
            if access_granted:
                return await call_next(request)
                
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        except Exception as e:
            logger.error(f"Middleware error: {e}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal payment processing error."}
            )

    async def _check_access(self, request: Request) -> bool:
        """Check if the request has valid payment credentials."""
        
        # Step 1: Identify user
        user_wallet = request.headers.get("X-User-Wallet")
        
        if not user_wallet:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Missing Header",
                    "message": "X-User-Wallet header required.",
                    "hint": "Include your Solana wallet address."
                }
            )
        
        user_wallet = user_wallet.strip()
        
        # Step 2: Check/create balance
        current_balance = await self.ledger.get_balance(user_wallet)
        
        if current_balance == 0.0:
            await self.ledger.credit_user(user_wallet, self.welcome_bonus, "Welcome bonus")
            current_balance = self.welcome_bonus
            logger.info(f"New user {user_wallet[:8]}... got ${self.welcome_bonus} bonus")
        
        # Step 3: Try free credits
        if await self.ledger.charge_user(user_wallet, self.price_per_request):
            new_balance = await self.ledger.get_balance(user_wallet)
            logger.info(f"Charged ${self.price_per_request} from {user_wallet[:8]}... (${new_balance:.2f})")
            return True
        
        # Step 4: Check for payment
        tx_signature = request.headers.get("X-Solana-Payment-Tx")
        
        if not tx_signature:
            payment_info = await self.payment_verifier.get_required_amount_display(self.price_per_request)
            
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Payment Required",
                    "message": "Free credits exhausted. Pay with SOL or USDC.",
                    "current_balance_usd": current_balance,
                    "payment": {
                        "amount_usd": payment_info["usd"],
                        "options": {
                            "SOL": {
                                "amount": payment_info["sol"],
                                "lamports": payment_info["lamports"],
                                "rate": f"1 SOL = ${payment_info['sol_usd_rate']}"
                            },
                            "USDC": {
                                "amount": payment_info["usdc"],
                                "units": payment_info["usdc_units"],
                                "mint": payment_info["usdc_mint"],
                                "rate": "1 USDC = $1.00"
                            }
                        },
                        "recipient_wallet": payment_info["recipient_wallet"],
                        "accepted_tokens": ["SOL", "USDC"]
                    },
                    "instructions": [
                        "Send SOL or USDC to recipient wallet",
                        "Wait for confirmation (~1-2 blocks)",
                        "Retry with X-Solana-Payment-Tx header"
                    ]
                }
            )
        
        # Step 5: Verify payment
        verification = await self.payment_verifier.verify_transaction(
            tx_signature.strip(),
            self.price_per_request,
            accepted_tokens=['SOL', 'USDC']
        )
        
        if not verification.success:
            status_code = self._get_status_for_error(verification.error)
            raise HTTPException(
                status_code=status_code,
                detail={
                    "error": verification.error.value,
                    "message": verification.message
                }
            )
        
        logger.info(f"Payment verified: {verification.token} ${verification.amount_received_usd:.4f} from {user_wallet[:8]}...")
        return True

    def _get_status_for_error(self, error: VerificationError) -> int:
        """Map verification errors to HTTP status codes."""
        return {
            VerificationError.INVALID_SIGNATURE: 400,
            VerificationError.TX_NOT_FOUND: 404,
            VerificationError.TX_FAILED: 402,
            VerificationError.WRONG_RECIPIENT: 403,
            VerificationError.INSUFFICIENT_AMOUNT: 402,
            VerificationError.SELF_TRANSFER: 403,
            VerificationError.RPC_UNAVAILABLE: 503,
            VerificationError.UNSUPPORTED_TOKEN: 400,
            VerificationError.UNKNOWN_ERROR: 500,
        }.get(error, 500)
