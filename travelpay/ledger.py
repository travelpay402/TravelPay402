"""
TravelPay SDK - Credit Ledger
SQLite-based user balance tracking for micropayments.
"""

import os
import logging
from typing import Optional
from datetime import datetime

import aiosqlite

logger = logging.getLogger("travelpay.ledger")


class Ledger:
    """
    Manages user credit balances for API access.
    
    Implements a freemium model where:
    - New users get a welcome bonus
    - Each API request deducts from balance
    - When balance is exhausted, payment is required
    
    Thread-safe with SQLite's built-in locking.
    
    Example:
        ledger = Ledger("payments.db")
        await ledger.init_db()
        
        # Check balance
        balance = await ledger.get_balance("wallet123...")
        
        # Credit user (after payment verification)
        await ledger.credit_user("wallet123...", 5.00)
        
        # Charge for API request
        success = await ledger.charge_user("wallet123...", 0.05)
    """
    
    def __init__(self, db_path: str = "travelpay.db"):
        """
        Initialize the Ledger.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._initialized = False
    
    async def init_db(self):
        """Initialize database schema."""
        if self._initialized:
            return
            
        async with aiosqlite.connect(self.db_path) as db:
            # User balances table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS balances (
                    wallet TEXT PRIMARY KEY,
                    balance_usd REAL NOT NULL DEFAULT 0.0,
                    total_credited REAL NOT NULL DEFAULT 0.0,
                    total_spent REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            # Transaction history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet TEXT NOT NULL,
                    amount_usd REAL NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (wallet) REFERENCES balances(wallet)
                )
            """)
            
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_transactions_wallet 
                ON transactions(wallet)
            """)
            
            await db.commit()
        
        self._initialized = True
        logger.info(f"Ledger initialized: {self.db_path}")
    
    async def get_balance(self, wallet: str) -> float:
        """
        Get current balance for a wallet.
        
        Args:
            wallet: Solana wallet address
            
        Returns:
            Current balance in USD (0.0 if wallet not found)
        """
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT balance_usd FROM balances WHERE wallet = ?",
                (wallet,)
            )
            row = await cursor.fetchone()
            
            return row[0] if row else 0.0
    
    async def credit_user(
        self, 
        wallet: str, 
        amount: float,
        description: str = "Credit"
    ) -> float:
        """
        Add credits to a user's balance.
        
        Args:
            wallet: Solana wallet address
            amount: Amount in USD to credit
            description: Transaction description
            
        Returns:
            New balance after credit
        """
        await self.init_db()
        
        now = datetime.utcnow().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Upsert balance
            await db.execute("""
                INSERT INTO balances (wallet, balance_usd, total_credited, total_spent, created_at, updated_at)
                VALUES (?, ?, ?, 0.0, ?, ?)
                ON CONFLICT(wallet) DO UPDATE SET
                    balance_usd = balance_usd + ?,
                    total_credited = total_credited + ?,
                    updated_at = ?
            """, (wallet, amount, amount, now, now, amount, amount, now))
            
            # Record transaction
            await db.execute("""
                INSERT INTO transactions (wallet, amount_usd, type, description, timestamp)
                VALUES (?, ?, 'credit', ?, ?)
            """, (wallet, amount, description, now))
            
            await db.commit()
            
            # Get new balance
            cursor = await db.execute(
                "SELECT balance_usd FROM balances WHERE wallet = ?",
                (wallet,)
            )
            row = await cursor.fetchone()
            new_balance = row[0] if row else amount
            
            logger.info(f"Credited ${amount:.2f} to {wallet[:8]}... (new balance: ${new_balance:.2f})")
            return new_balance
    
    async def charge_user(
        self, 
        wallet: str, 
        amount: float,
        description: str = "API request"
    ) -> bool:
        """
        Deduct credits from a user's balance.
        
        Args:
            wallet: Solana wallet address
            amount: Amount in USD to charge
            description: Transaction description
            
        Returns:
            True if charge succeeded, False if insufficient balance
        """
        await self.init_db()
        
        now = datetime.utcnow().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Check current balance
            cursor = await db.execute(
                "SELECT balance_usd FROM balances WHERE wallet = ?",
                (wallet,)
            )
            row = await cursor.fetchone()
            
            if not row or row[0] < amount:
                return False
            
            # Deduct balance
            await db.execute("""
                UPDATE balances SET
                    balance_usd = balance_usd - ?,
                    total_spent = total_spent + ?,
                    updated_at = ?
                WHERE wallet = ?
            """, (amount, amount, now, wallet))
            
            # Record transaction
            await db.execute("""
                INSERT INTO transactions (wallet, amount_usd, type, description, timestamp)
                VALUES (?, ?, 'charge', ?, ?)
            """, (wallet, -amount, description, now))
            
            await db.commit()
            
            return True
    
    async def get_user_stats(self, wallet: str) -> Optional[dict]:
        """
        Get detailed stats for a wallet.
        
        Returns:
            Dict with balance, totals, and transaction count
        """
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute(
                "SELECT * FROM balances WHERE wallet = ?",
                (wallet,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            # Count transactions
            cursor = await db.execute(
                "SELECT COUNT(*) FROM transactions WHERE wallet = ?",
                (wallet,)
            )
            tx_count = (await cursor.fetchone())[0]
            
            return {
                "wallet": row["wallet"],
                "balance_usd": row["balance_usd"],
                "total_credited": row["total_credited"],
                "total_spent": row["total_spent"],
                "transaction_count": tx_count,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
    
    async def get_recent_transactions(
        self, 
        wallet: str, 
        limit: int = 20
    ) -> list:
        """
        Get recent transactions for a wallet.
        
        Args:
            wallet: Solana wallet address
            limit: Maximum transactions to return
            
        Returns:
            List of transaction dicts
        """
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            cursor = await db.execute("""
                SELECT * FROM transactions 
                WHERE wallet = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (wallet, limit))
            
            rows = await cursor.fetchall()
            
            return [
                {
                    "id": row["id"],
                    "amount_usd": row["amount_usd"],
                    "type": row["type"],
                    "description": row["description"],
                    "timestamp": row["timestamp"]
                }
                for row in rows
            ]
