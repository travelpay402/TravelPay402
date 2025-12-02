"""
TravelPay SDK - Smart Subscription Manager
Event-driven push notifications with webhook delivery.

Transforms the API from a polling model to a push model where clients
subscribe to specific conditions and get notified when they're met.
"""

import os
import asyncio
import json
import time
import logging
import uuid
from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

import httpx
import aiosqlite

logger = logging.getLogger("travelpay.subscriptions")


class SubscriptionTarget(Enum):
    """Available subscription targets for event monitoring."""
    BORDER_WAIT = "border_wait"
    # Future targets:
    # FLIGHT_PRICE = "flight_price"
    # TRAIN_DELAY = "train_delay"


class SubscriptionStatus(Enum):
    """Subscription lifecycle states."""
    ACTIVE = "active"
    TRIGGERED = "triggered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Subscription:
    """
    A subscription to a data condition with webhook notification.
    
    Attributes:
        id: Unique subscription identifier
        user_wallet: Solana wallet of the subscriber
        target: Data source to monitor (e.g., border_wait)
        params: Target-specific parameters (e.g., crossing name)
        condition: Trigger condition expression (e.g., "wait_time < 20")
        webhook_url: URL to POST notification when triggered
        status: Current subscription state
        created_at: Unix timestamp of creation
        triggered_at: Unix timestamp when condition was met
        expires_at: Unix timestamp for expiration (0 = no expiry)
    """
    id: str
    user_wallet: str
    target: str
    params: Dict[str, Any]
    condition: str
    webhook_url: str
    status: str = SubscriptionStatus.ACTIVE.value
    created_at: int = field(default_factory=lambda: int(time.time()))
    triggered_at: Optional[int] = None
    expires_at: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConditionEvaluator:
    """
    Safe expression evaluator for subscription conditions.
    
    Supports basic comparison operators:
    - wait_time < 20
    - wait_time <= 30
    - status == "Open"
    - wait_time > 60
    
    Does NOT use eval() for security. Parses expressions manually.
    """
    
    OPERATORS = {
        '<': lambda a, b: a < b,
        '<=': lambda a, b: a <= b,
        '>': lambda a, b: a > b,
        '>=': lambda a, b: a >= b,
        '==': lambda a, b: a == b,
        '!=': lambda a, b: a != b,
    }
    
    @classmethod
    def evaluate(cls, condition: str, data: Dict[str, Any]) -> bool:
        """
        Evaluate a condition string against data.
        
        Args:
            condition: Expression like "wait_time < 20"
            data: Data dictionary with field values
            
        Returns:
            True if condition is met, False otherwise
        """
        condition = condition.strip()
        
        # Try each operator (longest first to match <= before <)
        for op in sorted(cls.OPERATORS.keys(), key=len, reverse=True):
            if op in condition:
                parts = condition.split(op, 1)
                if len(parts) == 2:
                    field_name = parts[0].strip()
                    target_str = parts[1].strip()
                    
                    # Get field value from data
                    field_value = data.get(field_name)
                    if field_value is None:
                        # Try nested access (e.g., data.wait_time_minutes)
                        field_value = data.get(field_name.replace('_', '_'))
                    
                    if field_value is None:
                        logger.warning(f"Field '{field_name}' not found in data")
                        return False
                    
                    # Parse target value
                    target_value = cls._parse_value(target_str)
                    
                    try:
                        result = cls.OPERATORS[op](field_value, target_value)
                        logger.debug(f"Condition {field_value} {op} {target_value} = {result}")
                        return result
                    except TypeError as e:
                        logger.warning(f"Type mismatch in condition: {e}")
                        return False
        
        logger.warning(f"Could not parse condition: {condition}")
        return False
    
    @staticmethod
    def _parse_value(value_str: str) -> Any:
        """Parse a string value to appropriate type."""
        value_str = value_str.strip()
        
        # Remove quotes for string comparison
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1]
        
        # Try numeric
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            return value_str


class SubscriptionStore:
    """
    SQLite-backed subscription persistence.
    """
    
    def __init__(self, db_path: str = "subscriptions.db"):
        self.db_path = db_path
        self._initialized = False
    
    async def init_db(self):
        """Initialize database schema."""
        if self._initialized:
            return
            
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    user_wallet TEXT NOT NULL,
                    target TEXT NOT NULL,
                    params TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    webhook_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at INTEGER NOT NULL,
                    triggered_at INTEGER,
                    expires_at INTEGER DEFAULT 0,
                    UNIQUE(user_wallet, target, condition, webhook_url)
                )
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_subs_status 
                ON subscriptions(status)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_subs_wallet 
                ON subscriptions(user_wallet)
            """)
            await db.commit()
        
        self._initialized = True
        logger.info(f"Subscription store initialized: {self.db_path}")
    
    async def add(self, sub: Subscription) -> bool:
        """Add a new subscription. Returns False if duplicate."""
        await self.init_db()
        
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO subscriptions 
                    (id, user_wallet, target, params, condition, webhook_url, 
                     status, created_at, triggered_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sub.id, sub.user_wallet, sub.target,
                    json.dumps(sub.params), sub.condition, sub.webhook_url,
                    sub.status, sub.created_at, sub.triggered_at, sub.expires_at
                ))
                await db.commit()
            return True
        except aiosqlite.IntegrityError:
            logger.warning(f"Duplicate subscription attempt: {sub.id}")
            return False
    
    async def get_active(self, target: Optional[str] = None) -> List[Subscription]:
        """Get all active subscriptions, optionally filtered by target."""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            if target:
                cursor = await db.execute(
                    "SELECT * FROM subscriptions WHERE status = 'active' AND target = ?",
                    (target,)
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM subscriptions WHERE status = 'active'"
                )
            
            rows = await cursor.fetchall()
            
            return [
                Subscription(
                    id=row['id'],
                    user_wallet=row['user_wallet'],
                    target=row['target'],
                    params=json.loads(row['params']),
                    condition=row['condition'],
                    webhook_url=row['webhook_url'],
                    status=row['status'],
                    created_at=row['created_at'],
                    triggered_at=row['triggered_at'],
                    expires_at=row['expires_at']
                )
                for row in rows
            ]
    
    async def get_by_wallet(self, wallet: str) -> List[Subscription]:
        """Get all subscriptions for a wallet."""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM subscriptions WHERE user_wallet = ? ORDER BY created_at DESC",
                (wallet,)
            )
            rows = await cursor.fetchall()
            
            return [
                Subscription(
                    id=row['id'],
                    user_wallet=row['user_wallet'],
                    target=row['target'],
                    params=json.loads(row['params']),
                    condition=row['condition'],
                    webhook_url=row['webhook_url'],
                    status=row['status'],
                    created_at=row['created_at'],
                    triggered_at=row['triggered_at'],
                    expires_at=row['expires_at']
                )
                for row in rows
            ]
    
    async def update_status(
        self, 
        sub_id: str, 
        status: SubscriptionStatus,
        triggered_at: Optional[int] = None
    ):
        """Update subscription status."""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            if triggered_at:
                await db.execute(
                    "UPDATE subscriptions SET status = ?, triggered_at = ? WHERE id = ?",
                    (status.value, triggered_at, sub_id)
                )
            else:
                await db.execute(
                    "UPDATE subscriptions SET status = ? WHERE id = ?",
                    (status.value, sub_id)
                )
            await db.commit()
    
    async def delete(self, sub_id: str, user_wallet: str) -> bool:
        """Delete a subscription. Returns True if deleted."""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM subscriptions WHERE id = ? AND user_wallet = ?",
                (sub_id, user_wallet)
            )
            await db.commit()
            return cursor.rowcount > 0


class SubscriptionManager:
    """
    Manages event subscriptions and processes triggers asynchronously.
    
    The manager runs a background loop that:
    1. Fetches current data for each target
    2. Evaluates conditions against active subscriptions
    3. Triggers webhooks when conditions are met
    4. Charges users for successful notifications
    
    Example:
        manager = SubscriptionManager(
            store=SubscriptionStore("subs.db"),
            ledger=ledger,
            signer=data_signer
        )
        
        # Register data fetcher for border_wait target
        manager.register_fetcher("border_wait", border_agent.get_wait_time)
        
        # Start background processing
        await manager.start()
        
        # Create subscription
        sub = await manager.create_subscription(
            user_wallet="ABC123...",
            target="border_wait",
            params={"crossing": "San Ysidro"},
            condition="wait_time_minutes < 20",
            webhook_url="https://myapp.com/webhook"
        )
    """
    
    def __init__(
        self,
        store: SubscriptionStore,
        ledger: Any,  # Ledger instance for charging
        signer: Any,  # DataSigner for signing notifications
        notification_price: float = None,
        check_interval: int = None
    ):
        self.store = store
        self.ledger = ledger
        self.signer = signer
        
        self.notification_price = notification_price or float(
            os.getenv("SUBSCRIPTION_PRICE_USD", "0.20")
        )
        self.check_interval = check_interval or int(
            os.getenv("SUBSCRIPTION_CHECK_INTERVAL", "60")
        )
        
        # Data fetchers for each target type
        self._fetchers: Dict[str, Callable[..., Awaitable[Dict]]] = {}
        
        # Background task handle
        self._task: Optional[asyncio.Task] = None
        self._running = False
        
        # HTTP client for webhooks
        self._http_client: Optional[httpx.AsyncClient] = None
        
        logger.info(f"Subscription Manager initialized:")
        logger.info(f"  - Notification price: ${self.notification_price}")
        logger.info(f"  - Check interval: {self.check_interval}s")
    
    def register_fetcher(
        self, 
        target: str, 
        fetcher: Callable[..., Awaitable[Dict]]
    ):
        """
        Register a data fetcher for a subscription target.
        
        Args:
            target: Target name (e.g., "border_wait")
            fetcher: Async function that takes params and returns data dict
        """
        self._fetchers[target] = fetcher
        logger.info(f"Registered fetcher for target: {target}")
    
    async def start(self):
        """Start the background subscription processing loop."""
        if self._running:
            logger.warning("Subscription manager already running")
            return
        
        await self.store.init_db()
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Subscription manager started")
    
    async def stop(self):
        """Stop the background processing loop."""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        
        logger.info("Subscription manager stopped")
    
    async def create_subscription(
        self,
        user_wallet: str,
        target: str,
        params: Dict[str, Any],
        condition: str,
        webhook_url: str,
        expires_in_hours: int = 24
    ) -> Optional[Subscription]:
        """
        Create a new subscription.
        
        Args:
            user_wallet: Subscriber's Solana wallet
            target: Data source to monitor
            params: Target-specific parameters
            condition: Trigger condition expression
            webhook_url: Notification endpoint
            expires_in_hours: Hours until expiration (0 = never)
            
        Returns:
            Subscription object if created, None if duplicate or invalid
        """
        # Validate target
        if target not in self._fetchers:
            logger.warning(f"Unknown subscription target: {target}")
            return None
        
        # Validate webhook URL
        if not webhook_url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid webhook URL: {webhook_url}")
            return None
        
        # Calculate expiration
        expires_at = 0
        if expires_in_hours > 0:
            expires_at = int(time.time()) + (expires_in_hours * 3600)
        
        sub = Subscription(
            id=str(uuid.uuid4()),
            user_wallet=user_wallet,
            target=target,
            params=params,
            condition=condition,
            webhook_url=webhook_url,
            expires_at=expires_at
        )
        
        success = await self.store.add(sub)
        if success:
            logger.info(f"Created subscription {sub.id[:8]}... for {user_wallet[:8]}...")
            return sub
        
        return None
    
    async def cancel_subscription(self, sub_id: str, user_wallet: str) -> bool:
        """Cancel a subscription."""
        deleted = await self.store.delete(sub_id, user_wallet)
        if deleted:
            logger.info(f"Cancelled subscription: {sub_id[:8]}...")
        return deleted
    
    async def get_user_subscriptions(self, wallet: str) -> List[Dict]:
        """Get all subscriptions for a user."""
        subs = await self.store.get_by_wallet(wallet)
        return [s.to_dict() for s in subs]
    
    async def _process_loop(self):
        """Main background processing loop."""
        logger.info("Starting subscription processing loop")
        
        while self._running:
            try:
                await self._process_subscriptions()
            except Exception as e:
                logger.error(f"Error in subscription loop: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)
    
    async def _process_subscriptions(self):
        """Process all active subscriptions."""
        now = int(time.time())
        
        for target, fetcher in self._fetchers.items():
            subscriptions = await self.store.get_active(target)
            
            if not subscriptions:
                continue
            
            logger.debug(f"Processing {len(subscriptions)} subscriptions for {target}")
            
            # Group by params to minimize API calls
            params_groups: Dict[str, List[Subscription]] = {}
            for sub in subscriptions:
                # Check expiration
                if sub.expires_at > 0 and sub.expires_at < now:
                    await self.store.update_status(sub.id, SubscriptionStatus.EXPIRED)
                    logger.info(f"Subscription expired: {sub.id[:8]}...")
                    continue
                
                params_key = json.dumps(sub.params, sort_keys=True)
                if params_key not in params_groups:
                    params_groups[params_key] = []
                params_groups[params_key].append(sub)
            
            # Fetch data and evaluate conditions
            for params_key, subs in params_groups.items():
                params = json.loads(params_key)
                
                try:
                    # Get single param value for simple fetchers
                    if len(params) == 1:
                        param_value = list(params.values())[0]
                        data = await fetcher(param_value)
                    else:
                        data = await fetcher(**params)
                    
                    if "error" in data:
                        logger.warning(f"Fetcher error for {target}: {data['error']}")
                        continue
                    
                    # Evaluate each subscription's condition
                    for sub in subs:
                        if ConditionEvaluator.evaluate(sub.condition, data):
                            await self._trigger_subscription(sub, data)
                            
                except Exception as e:
                    logger.error(f"Error fetching {target} data: {e}")
    
    async def _trigger_subscription(self, sub: Subscription, data: Dict):
        """
        Handle a triggered subscription:
        1. Charge the user
        2. Send webhook notification
        3. Update subscription status
        """
        logger.info(f"Subscription triggered: {sub.id[:8]}... condition: {sub.condition}")
        
        # Try to charge user
        charged = await self.ledger.charge_user(sub.user_wallet, self.notification_price)
        
        if not charged:
            # Insufficient balance - mark as failed
            await self.store.update_status(sub.id, SubscriptionStatus.FAILED)
            logger.warning(f"Insufficient balance for subscription: {sub.id[:8]}...")
            return
        
        # Sign the notification data
        signed_data = self.signer.sign_response({
            "subscription_id": sub.id,
            "target": sub.target,
            "params": sub.params,
            "condition": sub.condition,
            "data": data,
            "triggered_at": int(time.time())
        })
        
        # Send webhook
        try:
            response = await self._http_client.post(
                sub.webhook_url,
                json=signed_data,
                headers={
                    "Content-Type": "application/json",
                    "X-TravelPay-Signature": signed_data["signature"],
                    "X-TravelPay-Timestamp": str(signed_data["timestamp"]),
                    "X-TravelPay-Pubkey": signed_data["provider_pubkey"]
                }
            )
            
            if response.status_code < 300:
                logger.info(f"Webhook delivered: {sub.webhook_url}")
            else:
                logger.warning(f"Webhook returned {response.status_code}: {sub.webhook_url}")
                
        except Exception as e:
            logger.error(f"Webhook delivery failed: {e}")
        
        # Mark as triggered (one-time trigger)
        await self.store.update_status(
            sub.id, 
            SubscriptionStatus.TRIGGERED,
            triggered_at=int(time.time())
        )
        
        logger.info(f"Charged ${self.notification_price} for subscription notification")
