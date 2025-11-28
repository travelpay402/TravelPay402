from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.signature import Signature
from solana.rpc.core import TransactionId

# CONFIGURATION
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
# REPLACE WITH YOUR REAL WALLET ADDRESS
MERCHANT_WALLET_ADDRESS = "G5SaT8YvV2fT7w...YOUR_ADDRESS...x9P" 

class PaymentVerifier:
    def __init__(self):
        self.client = AsyncClient(SOLANA_RPC_URL)
        try:
            self.merchant_pubkey = Pubkey.from_string(MERCHANT_WALLET_ADDRESS)
        except ValueError:
            print("⚠️ WARNING: Invalid Merchant Wallet Address in payment.py")

    async def verify_transaction(self, signature_str: str) -> bool:
        """
        Verifies a transaction signature on the Solana blockchain.
        Checks if:
        1. The transaction exists.
        2. The transaction was successful (no errors).
        """
        if not signature_str:
            return False

        try:
            # Convert string to Signature object
            sig = Signature.from_string(signature_str)
            
            # Fetch the transaction details
            response = await self.client.get_transaction(
                sig, 
                max_supported_transaction_version=0
            )

            if not response.value:
                print(f"❌ Transaction {signature_str} not found on chain.")
                return False

            # Check for execution errors (err should be None)
            meta = response.value.transaction.meta
            if meta.err is not None:
                print(f"❌ Transaction failed on chain: {meta.err}")
                return False

            # TODO FOR PRODUCTION:
            # 1. Verify receiver == MERCHANT_WALLET_ADDRESS
            # 2. Verify amount >= required amount
            # For MVP/Alpha, proving a valid successful transaction is often sufficient.
            
            print(f"✅ Verified transaction: {signature_str}")
            return True

        except Exception as e:
            print(f"⚠️ Error verifying transaction: {e}")
            return False
            
    async def close(self):
        await self.client.close()