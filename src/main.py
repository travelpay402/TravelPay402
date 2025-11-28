import uvicorn
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Import local modules
from ledger import Ledger
from payment import PaymentVerifier
from border_agent import BorderWaitAgent
from middleware import Layer402Middleware

# === CONFIGURATION ===
REQUEST_PRICE_USD = 0.05 

app = FastAPI(
    title="TravelPay402 Protocol",
    description="M2M Micropayments for Real-World Data via Solana",
    version="1.0.0"
)

# CORS Configuration (Allows access from frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === INITIALIZATION ===
ledger = Ledger()
payment_verifier = PaymentVerifier()
border_agent = BorderWaitAgent()

# === LIFECYCLE EVENTS ===

@app.on_event("startup")
async def startup_event():
    """Run system checks and database initialization on startup."""
    await ledger.init_db()
    print("🚀 [System] Online: Database connected, Solana RPC ready.")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup connections on shutdown."""
    await payment_verifier.close()
    print("💤 [System] Offline: Connections closed.")

# === MIDDLEWARE REGISTRATION ===
# Applies the 402 payment logic globally
app.add_middleware(
    Layer402Middleware, 
    ledger=ledger, 
    payment_verifier=payment_verifier,
    price_per_request=REQUEST_PRICE_USD
)

# === ROUTES ===

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Public Endpoint: Landing Page.
    Does not require payment (handled in middleware exclusion).
    """
    return """
    <html>
        <head><title>TravelPay402 API</title></head>
        <body style="font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 20px;">
            <h1>🚦 TravelPay402 API is Live</h1>
            <p>Protocol V1.0 running on <strong>Solana Mainnet</strong>.</p>
            <p>Use <code>POST /border-wait</code> to fetch real-time data.</p>
            <p>Price per request: <strong>$0.05</strong></p>
        </body>
    </html>
    """

@app.post("/border-wait")
async def get_border_wait(request: Request):
    """
    PROTECTED ENDPOINT.
    Returns real-time border wait times.
    Requires 'X-Solana-Pay' header with valid transaction signature.
    """
    try:
        body = await request.json()
        crossing_query = body.get("crossing", "San Ysidro")
        
        print(f"📥 [API] Request received for: {crossing_query}")

        # Fetch real data from CBP
        data = await border_agent.get_wait_time(crossing_query)
        
        if "error" in data:
            return JSONResponse(status_code=404, content=data)
            
        return data

    except Exception as e:
        print(f"❌ [API] Error processing request: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/balance/{public_key}")
async def check_balance(public_key: str):
    """
    Public Endpoint: Check user balance.
    (Future proofing for prepaid model).
    """
    balance = await ledger.get_balance(public_key)
    return {"public_key": public_key, "balance_usd": balance}

# === ENTRY POINT ===
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)