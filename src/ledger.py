import aiosqlite
import asyncio
import os

class Ledger:
    def __init__(self, db_path="travelpay.db"):
        self.db_path = db_path

    async def init_db(self):
        """Initializes the users table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    public_key TEXT PRIMARY KEY,
                    balance REAL DEFAULT 0.0
                )
            """)
            await db.commit()
        print(f"✅ Database initialized at {self.db_path}")

    async def get_balance(self, public_key: str) -> float:
        """Retrieves the current balance for a public key."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT balance FROM users WHERE public_key = ?", (public_key,))
            row = await cursor.fetchone()
            return row[0] if row else 0.0

    async def credit_user(self, public_key: str, amount_usd: float):
        """Credits funds to a user (UPSERT logic)."""
        async with aiosqlite.connect(self.db_path) as db:
            # Update if exists, Insert if new
            await db.execute("""
                INSERT INTO users (public_key, balance) VALUES (?, ?)
                ON CONFLICT(public_key) DO UPDATE SET balance = balance + ?
            """, (public_key, amount_usd, amount_usd))
            await db.commit()
        print(f"💰 Credited ${amount_usd} to {public_key}")

    async def charge_user(self, public_key: str, amount_usd: float) -> bool:
        """Deducts funds if balance is sufficient. Returns True if successful."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT balance FROM users WHERE public_key = ?", (public_key,))
            row = await cursor.fetchone()
            current_balance = row[0] if row else 0.0

            if current_balance >= amount_usd:
                new_balance = current_balance - amount_usd
                await db.execute("UPDATE users SET balance = ? WHERE public_key = ?", (new_balance, public_key))
                await db.commit()
                return True
            return False