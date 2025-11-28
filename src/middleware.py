from fastapi import Request, HTTPException
# Обрати внимание: импорты относительные (с точкой), так как мы внутри пакета
from .payment import SolanaPaymentVerifier
from .ledger import CreditLedger

class Layer402Middleware:
    """
    Middleware that enforces the Payment 402 protocol.
    Checks: Free Credits -> Crypto Payment -> 402 Error.
    """
    def __init__(self, verifier: SolanaPaymentVerifier, ledger: CreditLedger, price_usd: float, welcome_bonus: float):
        self.verifier = verifier
        self.ledger = ledger
        self.price = price_usd
        self.welcome_bonus = welcome_bonus

    async def check_access(self, request: Request):
        # 1. Identify User
        user_wallet = request.headers.get("X-User-Wallet")
        if not user_wallet:
            raise HTTPException(
                status_code=400, 
                detail="Missing Header: X-User-Wallet is required for identification."
            )

        # 2. Attempt to pay with Free Credits (Freemium)
        if self.ledger.attempt_deduction(user_wallet, self.price, self.welcome_bonus):
            return True  # Access Granted via Ledger

        # 3. If credits exhausted, check for On-Chain Payment
        tx_signature = request.headers.get("X-Solana-Payment-Tx")

        if not tx_signature:
            # RETURN 402 PAYMENT REQUIRED
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Payment Required",
                    "message": "Free credits exhausted. Please pay via Solana.",
                    "amount_usd": self.price,
                    "recipient": str(self.verifier.merchant_wallet),
                    "accepted_tokens": ["SOL", "USDC"]
                }
            )

        # 4. Verify the Crypto Transaction
        # Mock conversion: 1 SOL = $100 -> 0.05 USD = 0.0005 SOL
        required_sol = self.price / 100.0 
        is_valid = self.verifier.verify_transaction(tx_signature, required_sol)
        
        if not is_valid:
            raise HTTPException(status_code=403, detail="Invalid transaction signature.")

        return True