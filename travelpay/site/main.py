"""
TravelPay402 API Server
HTTP 402 Micropayment Protocol with Verifiable Oracle & Event Subscriptions

Update 5 Features:
- GET /oracle-key - Public key for data verification
- POST /subscribe - Create event subscriptions  
- GET /subscriptions - List user subscriptions
- DELETE /subscriptions/{id} - Cancel subscription
- All responses cryptographically signed
- Redis caching for high performance
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv

# Import from TravelPay SDK
from travelpay import (
    PaymentVerifier, 
    Layer402Middleware, 
    Ledger, 
    BorderWaitAgent,
    DataSigner,
    SubscriptionManager,
    SubscriptionStore
)

# Load environment from root directory
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
PRICE_PER_REQUEST = float(os.getenv("PRICE_PER_REQUEST_USD", "0.05"))
STATIC_DIR = Path(__file__).parent / "static"
DB_PATH = ROOT_DIR / "travelpay.db"
SUBS_DB_PATH = ROOT_DIR / "subscriptions.db"


# === LOGGING ===
def setup_logging():
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    root_logger.handlers = []
    
    file_handler = RotatingFileHandler(
        log_dir / "travelpay.log",
        maxBytes=10_000_000,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    return logging.getLogger("travelpay.site")

logger = setup_logging()


# === SDK COMPONENTS ===
ledger = Ledger(str(DB_PATH))
payment_verifier = PaymentVerifier()
border_agent = BorderWaitAgent()

# Update 5: Oracle signing
data_signer = DataSigner()

# Update 5: Subscription manager
subscription_store = SubscriptionStore(str(SUBS_DB_PATH))
subscription_manager: Optional[SubscriptionManager] = None


# === LIFESPAN ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    global subscription_manager
    
    # Startup
    await ledger.init_db()
    await subscription_store.init_db()
    
    # Initialize Redis cache for border agent
    cache_connected = await border_agent.init_cache()
    if cache_connected:
        logger.info("Redis cache: ENABLED")
    else:
        logger.warning("Redis cache: DISABLED (using direct API)")
    
    # Initialize subscription manager
    subscription_manager = SubscriptionManager(
        store=subscription_store,
        ledger=ledger,
        signer=data_signer
    )
    subscription_manager.register_fetcher("border_wait", border_agent.get_wait_time)
    await subscription_manager.start()
    
    merchant = os.getenv("MERCHANT_WALLET", "")
    if not merchant or "YourActual" in merchant:
        logger.warning("=" * 50)
        logger.warning("MERCHANT_WALLET not configured!")
        logger.warning("=" * 50)
    
    logger.info(f"TravelPay402 starting on {HOST}:{PORT}")
    logger.info(f"Price: ${PRICE_PER_REQUEST}/request")
    logger.info(f"Oracle Public Key: {data_signer.public_key_hex[:16]}...")
    
    yield
    
    # Shutdown
    if subscription_manager:
        await subscription_manager.stop()
    await payment_verifier.close()
    await border_agent.close()
    logger.info("Server shutdown complete")


# === APP ===
app = FastAPI(
    title="TravelPay402 API",
    description="HTTP 402 Micropayments Protocol with Verifiable Oracle",
    version="0.5.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Payment Middleware (from SDK)
app.add_middleware(
    Layer402Middleware,
    ledger=ledger,
    payment_verifier=payment_verifier,
    price_per_request=PRICE_PER_REQUEST,
    exclude_paths={
        "/", "/docs", "/openapi.json", "/health", "/balance", 
        "/static", "/favicon.ico", "/oracle-key", "/subscribe",
        "/subscriptions"
    }
)

# Static Files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# === PYDANTIC MODELS ===

class SubscribeRequest(BaseModel):
    """Request body for creating a subscription."""
    target: str = "border_wait"
    params: dict = {"crossing": "San Ysidro"}
    condition: str = "wait_time_minutes < 20"
    webhook_url: str
    expires_in_hours: int = 24
    
    class Config:
        json_schema_extra = {
            "example": {
                "target": "border_wait",
                "params": {"crossing": "San Ysidro"},
                "condition": "wait_time_minutes < 20",
                "webhook_url": "https://your-app.com/webhook",
                "expires_in_hours": 24
            }
        }


class BorderWaitRequest(BaseModel):
    """Request body for border wait endpoint."""
    crossing: str = "San Ysidro"


# === PUBLIC ROUTES ===

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve landing page."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding='utf-8'))
    
    return HTMLResponse(content=f"""
        <html>
        <head><title>TravelPay402</title></head>
        <body style="font-family: system-ui; background: #E8A035; padding: 40px;">
            <h1>🔐 TravelPay402 API v0.5.0</h1>
            <p>Verifiable Oracle Protocol Active</p>
            <p><strong>Oracle Public Key:</strong> <code>{data_signer.public_key_hex[:32]}...</code></p>
            <p><a href="/docs">API Docs</a> | <a href="/oracle-key">Full Public Key</a></p>
        </body>
        </html>
    """)


@app.get("/health")
async def health():
    """Health check endpoint."""
    cache_stats = await border_agent.get_cache_stats()
    
    return {
        "status": "healthy",
        "version": "0.5.0",
        "merchant_configured": bool(os.getenv("MERCHANT_WALLET", "").strip()),
        "oracle_enabled": True,
        "subscriptions_enabled": subscription_manager is not None,
        "cache": cache_stats
    }


@app.get("/oracle-key")
async def get_oracle_key():
    """
    PUBLIC - Get the Oracle's public key for data verification.
    
    Clients use this key to verify that signed responses came from this API.
    The key can be stored on-chain for trustless verification.
    """
    return {
        "provider": "TravelPay402",
        "protocol": "Ed25519",
        "public_key": data_signer.public_key_hex,
        "usage": {
            "description": "Use this key to verify 'signature' field in API responses",
            "verification_steps": [
                "1. Extract 'data' from response",
                "2. Compute SHA-256 hash of JSON-serialized data (sorted keys)",
                "3. Concatenate: '{data_hash}:{timestamp}'",
                "4. Verify Ed25519 signature against message using this public key"
            ]
        }
    }


@app.get("/balance/{wallet}")
async def get_balance(wallet: str):
    """Check user balance."""
    balance = await ledger.get_balance(wallet)
    return {
        "wallet": wallet,
        "balance_usd": balance,
        "price_per_request": PRICE_PER_REQUEST,
        "requests_remaining": int(balance / PRICE_PER_REQUEST) if PRICE_PER_REQUEST > 0 else 0
    }


# === SUBSCRIPTION ROUTES ===

@app.post("/subscribe")
async def create_subscription(request: Request, body: SubscribeRequest):
    """
    Create a new event subscription.
    
    When the condition is met, a signed notification is POSTed to your webhook.
    One-time trigger: subscription is removed after notification.
    Cost: $0.20 charged when notification is sent.
    """
    user_wallet = request.headers.get("X-User-Wallet")
    if not user_wallet:
        raise HTTPException(
            status_code=400,
            detail={"error": "X-User-Wallet header required"}
        )
    
    if not subscription_manager:
        raise HTTPException(
            status_code=503,
            detail={"error": "Subscription service unavailable"}
        )
    
    # Validate webhook URL
    if not body.webhook_url.startswith(('http://', 'https://')):
        raise HTTPException(
            status_code=400,
            detail={"error": "Invalid webhook URL - must start with http:// or https://"}
        )
    
    sub = await subscription_manager.create_subscription(
        user_wallet=user_wallet,
        target=body.target,
        params=body.params,
        condition=body.condition,
        webhook_url=body.webhook_url,
        expires_in_hours=body.expires_in_hours
    )
    
    if not sub:
        raise HTTPException(
            status_code=400,
            detail={"error": "Could not create subscription - may be duplicate or invalid target"}
        )
    
    return data_signer.sign_response({
        "message": "Subscription created",
        "subscription": sub.to_dict(),
        "notification_price_usd": subscription_manager.notification_price,
        "check_interval_seconds": subscription_manager.check_interval
    })


@app.get("/subscriptions")
async def list_subscriptions(request: Request):
    """List all subscriptions for the authenticated user."""
    user_wallet = request.headers.get("X-User-Wallet")
    if not user_wallet:
        raise HTTPException(
            status_code=400,
            detail={"error": "X-User-Wallet header required"}
        )
    
    if not subscription_manager:
        raise HTTPException(
            status_code=503,
            detail={"error": "Subscription service unavailable"}
        )
    
    subs = await subscription_manager.get_user_subscriptions(user_wallet)
    
    return data_signer.sign_response({
        "wallet": user_wallet,
        "subscriptions": subs,
        "count": len(subs)
    })


@app.delete("/subscriptions/{sub_id}")
async def cancel_subscription(sub_id: str, request: Request):
    """Cancel a subscription."""
    user_wallet = request.headers.get("X-User-Wallet")
    if not user_wallet:
        raise HTTPException(
            status_code=400,
            detail={"error": "X-User-Wallet header required"}
        )
    
    if not subscription_manager:
        raise HTTPException(
            status_code=503,
            detail={"error": "Subscription service unavailable"}
        )
    
    deleted = await subscription_manager.cancel_subscription(sub_id, user_wallet)
    
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"error": "Subscription not found or not owned by wallet"}
        )
    
    return data_signer.sign_response({
        "message": "Subscription cancelled",
        "subscription_id": sub_id
    })


# === PAID ROUTES ===

@app.post("/border-wait")
async def get_border_wait(request: Request, body: BorderWaitRequest):
    """
    PAID ENDPOINT - Get border wait times (signed response).
    
    Returns cryptographically signed data that can be verified using the oracle public key.
    """
    try:
        user = request.headers.get("X-User-Wallet", "unknown")
        logger.info(f"Border request | User: {user[:12]}... | Crossing: {body.crossing}")
        
        data = await border_agent.get_wait_time(body.crossing)
        
        if "error" in data:
            return JSONResponse(
                status_code=404, 
                content=data_signer.sign_response(data)
            )
        
        logger.info(f"Served: {data.get('crossing')} | Wait: {data.get('wait_time_minutes')} min | Cached: {data.get('cached', False)}")
        
        # Return signed response
        return data_signer.sign_response(data)
        
    except Exception as e:
        logger.error(f"Border request error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@app.get("/crossings")
async def list_crossings():
    """PAID ENDPOINT - List all available crossings (signed response)."""
    crossings = await border_agent.list_crossings()
    return data_signer.sign_response({"crossings": crossings})


@app.get("/cache-stats")
async def cache_statistics():
    """Get Redis cache statistics."""
    stats = await border_agent.get_cache_stats()
    return data_signer.sign_response(stats)


@app.post("/cache-invalidate")
async def invalidate_cache(crossing: Optional[str] = None):
    """Invalidate cache for a crossing or all crossings (admin use)."""
    await border_agent.invalidate_cache(crossing)
    return data_signer.sign_response({
        "message": f"Cache invalidated for: {crossing or 'all crossings'}"
    })


# === ENTRY POINT ===
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=True
    )
