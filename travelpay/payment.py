"""
TravelPay SDK - Solana Payment Verification Module
Secure transaction verification with SOL and USDC support.
"""

import os
import asyncio
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.pubkey import Pubkey
from solders.signature import Signature
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("travelpay.payment")


class VerificationError(Enum):
    """Enumeration of possible verification failures."""
    NONE = "none"
    INVALID_SIGNATURE = "invalid_signature"
    TX_NOT_FOUND = "transaction_not_found"
    TX_FAILED = "transaction_failed"
    WRONG_RECIPIENT = "wrong_recipient"
    INSUFFICIENT_AMOUNT = "insufficient_amount"
    SELF_TRANSFER = "self_transfer"
    RPC_UNAVAILABLE = "rpc_unavailable"
    UNSUPPORTED_TOKEN = "unsupported_token"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class VerificationResult:
    """Result of a transaction verification attempt."""
    success: bool
    error: VerificationError
    message: str
    amount_received_lamports: Optional[int] = None
    amount_received_usd: Optional[float] = None
    token: Optional[str] = None
    sender: Optional[str] = None


class PaymentVerifier:
    """
    Verifies Solana transactions for payment validity.
    Supports both native SOL and USDC SPL token payments.
    
    Args:
        merchant_wallet: Your Solana wallet address to receive payments
        rpc_url: Solana RPC endpoint URL
        sol_usd_price: Current SOL/USD exchange rate
        max_retries: Number of RPC retry attempts
        retry_delay: Delay between retries in seconds
    
    Example:
        verifier = PaymentVerifier(
            merchant_wallet="YourWalletAddress...",
            rpc_url="https://api.mainnet-beta.solana.com",
            sol_usd_price=150.0
        )
        
        result = await verifier.verify_transaction(signature, required_usd=0.05)
        if result.success:
            print(f"Payment verified: ${result.amount_received_usd}")
    """
    
    LAMPORTS_PER_SOL = 1_000_000_000
    USDC_DECIMALS = 6
    
    # USDC Mint addresses
    USDC_MINTS = {
        'mainnet': 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
        'devnet': '4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU'
    }
    
    TOKEN_PROGRAM_ID = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA'
    
    def __init__(
        self,
        merchant_wallet: str = None,
        rpc_url: str = None,
        sol_usd_price: float = None,
        max_retries: int = None,
        retry_delay: float = None
    ):
        # Load from env or use parameters
        self.rpc_url = rpc_url or os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        self.merchant_wallet_str = merchant_wallet or os.getenv("MERCHANT_WALLET", "")
        self.sol_usd_price = sol_usd_price or float(os.getenv("SOL_USD_PRICE", "150.0"))
        self.max_retries = max_retries or int(os.getenv("RPC_MAX_RETRIES", "3"))
        self.retry_delay = retry_delay or float(os.getenv("RPC_RETRY_DELAY_SECONDS", "1.0"))
        
        # Determine network
        self.network = 'devnet' if 'devnet' in self.rpc_url else 'mainnet'
        self.usdc_mint = self.USDC_MINTS.get(self.network, self.USDC_MINTS['mainnet'])
        
        # Validate merchant wallet
        self.merchant_pubkey = None
        if self.merchant_wallet_str and self.merchant_wallet_str != "YourActualMerchantWalletAddressHere123456789":
            try:
                self.merchant_pubkey = Pubkey.from_string(self.merchant_wallet_str)
                logger.info(f"Merchant wallet: {self.merchant_wallet_str[:8]}...{self.merchant_wallet_str[-8:]}")
            except Exception as e:
                logger.error(f"Invalid MERCHANT_WALLET: {e}")
        else:
            logger.warning("MERCHANT_WALLET not configured - payments will be rejected")
        
        # Initialize RPC client
        self.client = AsyncClient(self.rpc_url)
        logger.info(f"Connected to Solana RPC: {self.rpc_url} ({self.network})")

    async def close(self):
        """Close the Solana RPC client."""
        if self.client:
            await self.client.close()

    def usd_to_lamports(self, usd_amount: float) -> int:
        """Convert USD to lamports using configured SOL/USD price."""
        sol_amount = usd_amount / self.sol_usd_price
        return int(sol_amount * self.LAMPORTS_PER_SOL)
    
    def lamports_to_usd(self, lamports: int) -> float:
        """Convert lamports to USD using configured SOL/USD price."""
        sol_amount = lamports / self.LAMPORTS_PER_SOL
        return sol_amount * self.sol_usd_price

    def usd_to_usdc_units(self, usd_amount: float) -> int:
        """Convert USD to USDC smallest units (6 decimals)."""
        return int(usd_amount * (10 ** self.USDC_DECIMALS))
    
    def usdc_units_to_usd(self, units: int) -> float:
        """Convert USDC units to USD."""
        return units / (10 ** self.USDC_DECIMALS)

    async def get_required_amount_display(self, usd_amount: float) -> dict:
        """
        Get payment amount display info for 402 response.
        
        Returns dict with amounts in all supported formats.
        """
        sol_amount = usd_amount / self.sol_usd_price
        
        return {
            "usd": usd_amount,
            "sol": round(sol_amount, 9),
            "lamports": self.usd_to_lamports(usd_amount),
            "usdc": usd_amount,
            "usdc_units": self.usd_to_usdc_units(usd_amount),
            "usdc_mint": self.usdc_mint,
            "sol_usd_rate": self.sol_usd_price,
            "recipient_wallet": self.merchant_wallet_str
        }

    async def _fetch_transaction_with_retry(self, sig: Signature):
        """Fetch transaction with retry logic for RPC resilience."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                response = await self.client.get_transaction(
                    sig,
                    max_supported_transaction_version=0,
                    commitment=Confirmed
                )
                return response
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"RPC attempt {attempt + 1} failed, retrying...")
                    await asyncio.sleep(self.retry_delay)
        
        logger.error(f"RPC unavailable after {self.max_retries} attempts: {last_error}")
        return None

    def _extract_sol_transfer(self, tx_response) -> Tuple[Optional[str], Optional[str], Optional[int]]:
        """Extract sender, receiver, and amount from a SOL transfer."""
        try:
            tx = tx_response.value.transaction
            meta = tx.meta
            message = tx.transaction.message
            account_keys = message.account_keys
            
            pre_balances = meta.pre_balances
            post_balances = meta.post_balances
            
            sender_idx = None
            receiver_idx = None
            transfer_amount = 0
            
            for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                diff = post - pre
                if diff < 0:
                    if sender_idx is None or abs(diff) > abs(post_balances[sender_idx] - pre_balances[sender_idx]):
                        sender_idx = i
                elif diff > 0:
                    if receiver_idx is None or diff > (post_balances[receiver_idx] - pre_balances[receiver_idx]):
                        receiver_idx = i
                        transfer_amount = diff
            
            if sender_idx is not None and receiver_idx is not None:
                sender = str(account_keys[sender_idx])
                receiver = str(account_keys[receiver_idx])
                return sender, receiver, transfer_amount
            
            return None, None, None
            
        except Exception as e:
            logger.warning(f"Error extracting SOL transfer: {e}")
            return None, None, None

    def _extract_spl_transfer(self, tx_response) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[str]]:
        """Extract sender, receiver, amount, and mint from an SPL token transfer."""
        try:
            tx = tx_response.value.transaction
            meta = tx.meta
            
            pre_token_balances = meta.pre_token_balances or []
            post_token_balances = meta.post_token_balances or []
            
            if not post_token_balances:
                return None, None, None, None
            
            changes = {}
            
            for post_bal in post_token_balances:
                account_idx = post_bal.account_index
                mint = str(post_bal.mint)
                owner = str(post_bal.owner) if post_bal.owner else None
                post_amount = int(post_bal.ui_token_amount.amount)
                
                pre_amount = 0
                for pre_bal in pre_token_balances:
                    if pre_bal.account_index == account_idx:
                        pre_amount = int(pre_bal.ui_token_amount.amount)
                        break
                
                change = post_amount - pre_amount
                if owner and change != 0:
                    if mint not in changes:
                        changes[mint] = []
                    changes[mint].append({'owner': owner, 'change': change})
            
            usdc_changes = changes.get(self.usdc_mint, [])
            
            sender = None
            receiver = None
            amount = 0
            
            for entry in usdc_changes:
                if entry['change'] < 0:
                    sender = entry['owner']
                elif entry['change'] > 0:
                    receiver = entry['owner']
                    amount = entry['change']
            
            if sender and receiver and amount > 0:
                return sender, receiver, amount, self.usdc_mint
            
            return None, None, None, None
            
        except Exception as e:
            logger.warning(f"Error extracting SPL transfer: {e}")
            return None, None, None, None

    async def verify_transaction(
        self, 
        signature_str: str, 
        required_usd: float,
        accepted_tokens: List[str] = None
    ) -> VerificationResult:
        """
        Verify a Solana transaction for payment validity.
        
        Args:
            signature_str: The transaction signature to verify
            required_usd: The minimum USD amount required
            accepted_tokens: List of accepted tokens ['SOL', 'USDC'], default both
            
        Returns:
            VerificationResult with success status and details
        """
        accepted_tokens = accepted_tokens or ['SOL', 'USDC']
        
        # Check merchant wallet configured
        if not self.merchant_pubkey:
            return VerificationResult(
                success=False,
                error=VerificationError.WRONG_RECIPIENT,
                message="Merchant wallet not configured"
            )
        
        # Parse signature
        try:
            sig = Signature.from_string(signature_str)
        except Exception as e:
            return VerificationResult(
                success=False,
                error=VerificationError.INVALID_SIGNATURE,
                message=f"Invalid signature format: {e}"
            )
        
        # Fetch transaction
        tx_response = await self._fetch_transaction_with_retry(sig)
        
        if not tx_response:
            return VerificationResult(
                success=False,
                error=VerificationError.RPC_UNAVAILABLE,
                message="Could not fetch transaction from Solana RPC"
            )
        
        if not tx_response.value:
            return VerificationResult(
                success=False,
                error=VerificationError.TX_NOT_FOUND,
                message="Transaction not found on chain"
            )
        
        # Check transaction success
        meta = tx_response.value.transaction.meta
        if meta.err:
            return VerificationResult(
                success=False,
                error=VerificationError.TX_FAILED,
                message=f"Transaction failed: {meta.err}"
            )
        
        # Try SOL transfer first
        if 'SOL' in accepted_tokens:
            sender, receiver, lamports = self._extract_sol_transfer(tx_response)
            
            if receiver == self.merchant_wallet_str and lamports:
                # Verify not self-transfer
                if sender == receiver:
                    return VerificationResult(
                        success=False,
                        error=VerificationError.SELF_TRANSFER,
                        message="Self-transfers not allowed"
                    )
                
                received_usd = self.lamports_to_usd(lamports)
                
                # Check amount
                if received_usd < required_usd * 0.99:  # 1% tolerance
                    return VerificationResult(
                        success=False,
                        error=VerificationError.INSUFFICIENT_AMOUNT,
                        message=f"Received ${received_usd:.4f}, required ${required_usd:.4f}"
                    )
                
                return VerificationResult(
                    success=True,
                    error=VerificationError.NONE,
                    message="SOL payment verified",
                    amount_received_lamports=lamports,
                    amount_received_usd=received_usd,
                    token="SOL",
                    sender=sender
                )
        
        # Try USDC transfer
        if 'USDC' in accepted_tokens:
            sender, receiver, units, mint = self._extract_spl_transfer(tx_response)
            
            if receiver == self.merchant_wallet_str and units and mint == self.usdc_mint:
                # Verify not self-transfer
                if sender == receiver:
                    return VerificationResult(
                        success=False,
                        error=VerificationError.SELF_TRANSFER,
                        message="Self-transfers not allowed"
                    )
                
                received_usd = self.usdc_units_to_usd(units)
                
                # Check amount
                if received_usd < required_usd * 0.99:  # 1% tolerance
                    return VerificationResult(
                        success=False,
                        error=VerificationError.INSUFFICIENT_AMOUNT,
                        message=f"Received ${received_usd:.4f} USDC, required ${required_usd:.4f}"
                    )
                
                return VerificationResult(
                    success=True,
                    error=VerificationError.NONE,
                    message="USDC payment verified",
                    amount_received_lamports=units,
                    amount_received_usd=received_usd,
                    token="USDC",
                    sender=sender
                )
        
        # No valid transfer found
        return VerificationResult(
            success=False,
            error=VerificationError.WRONG_RECIPIENT,
            message=f"No transfer to merchant wallet found. Expected: {self.merchant_wallet_str[:8]}..."
        )
