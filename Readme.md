# TravelPay402

**Pay-Per-Use Travel Intelligence Platform**

TravelPay402 aggregates real-time travel data from multiple sources and delivers it through a simple micropayment protocol. No subscriptions, no API keys - just pay $0.01–$0.05 per query using Solana for instant access to time-sensitive pricing and delay information.

Built for travelers making real decisions, not developers building apps.

## 🎯 What You Get

### Cheapest Flights
Compare prices across airlines, OTAs, and meta-search engines in real-time. Our aggregator checks 20+ sources every hour to find the lowest fares for your route.

**Example Query:**
```
JFK → LAX, Dec 15-22
→ $287 (United via Google Flights)
→ $312 (Delta Direct)
→ $299 (Spirit via Kayak)
```

### Bus & Train Delays
Live delay information for intercity buses and trains across North America and Europe. Know before you go.

**Coverage:**
- Amtrak (US)
- Greyhound, Megabus, FlixBus
- VIA Rail (Canada)
- European rail networks (via third-party feeds)

### Border Wait Times
Official data from Customs and Border Protection (CBP) for all major US-Mexico and US-Canada crossings.

**Example:**
```
San Ysidro Pedestrian Crossing
→ Current Wait: 45 minutes
→ Status: Open
→ Updated: 5 minutes ago
```

### Local Taxi Prices
Real-time taxi and rideshare pricing for major cities. Compare Uber, Lyft, traditional cabs, and local services.

**Example:**
```
LAX Airport → Downtown LA
→ UberX: $32–38 (surge 1.2x)
→ Lyft: $29–35
→ Yellow Cab: ~$45 (meter estimate)
```

## 💰 Pricing

| Data Type | Cost per Query | Update Frequency |
|-----------|---------------|------------------|
| Flight Prices | $0.05 | Hourly |
| Bus/Train Delays | $0.02 | Real-time |
| Border Wait Times | $0.01 | Every 15 min |
| Taxi Prices | $0.03 | Real-time |

**Welcome Bonus:** New users get $2.00 in free credits (40–200 queries depending on data type)

## 🚀 Quick Start

### For Travelers

1. Get a Solana wallet (Phantom, Solflare, or any SPL-compatible wallet)
2. Make your first query - **free credit applied automatically**
3. When credit runs out, top up with SOL or USDC

### Installation (Self-Hosted)

```bash
git clone https://github.com/yourusername/travelpay402.git
cd travelpay402
pip install -r requirements.txt
```

### Configuration

Create `.env` file:

```env
# Your Solana wallet for receiving payments
MERCHANT_WALLET=YourSolanaPublicKeyHere

# Solana RPC endpoint
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Pricing (USD)
PRICE_PER_REQUEST_USD=0.05
WELCOME_BONUS_USD=2.00

# Server
PORT=8000
HOST=0.0.0.0
```

### Run Server

```bash
cd src
python main.py
```

Server starts at `http://localhost:8000`

## 📡 API Usage

### Authentication

All requests require your Solana wallet address in headers:

```bash
X-User-Wallet: YourSolanaPublicKeyHere
```

For top-ups after free credit exhausts:

```bash
X-Payment-Signature: YourSolanaTransactionSignature
```

### Endpoints

#### 1. Find Cheapest Flights

```bash
POST /api/flights
Content-Type: application/json

{
  "origin": "JFK",
  "destination": "LAX",
  "departure_date": "2025-12-15",
  "return_date": "2025-12-22",
  "passengers": 1
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "cheapest": {
      "price": 287,
      "currency": "USD",
      "airline": "United Airlines",
      "source": "Google Flights",
      "direct": false,
      "stops": 1
    },
    "alternatives": [
      {
        "price": 299,
        "airline": "Spirit Airlines",
        "source": "Kayak",
        "direct": true
      },
      {
        "price": 312,
        "airline": "Delta",
        "source": "Delta.com",
        "direct": true
      }
    ],
    "last_updated": "2025-11-28T14:30:00Z",
    "sources_checked": 23
  },
  "cost": 0.05,
  "balance_remaining": 1.95
}
```

#### 2. Check Bus/Train Delays

```bash
POST /api/transit-delays
Content-Type: application/json

{
  "route": "Amtrak Northeast Regional",
  "train_number": "171",
  "date": "2025-11-28"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "service": "Amtrak",
    "route": "Northeast Regional #171",
    "status": "Delayed",
    "delay_minutes": 23,
    "reason": "Track maintenance",
    "next_update": "2025-11-28T15:00:00Z",
    "current_location": "Philadelphia 30th Street Station"
  },
  "cost": 0.02,
  "balance_remaining": 1.93
}
```

#### 3. Border Wait Times

```bash
POST /api/border-wait
Content-Type: application/json

{
  "crossing": "San Ysidro",
  "lane_type": "pedestrian"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "crossing": "San Ysidro - US/Mexico Border",
    "lane_type": "Pedestrian",
    "wait_time_minutes": 45,
    "status": "Open",
    "last_updated": "2025-11-28T14:25:00Z",
    "source": "Official CBP Feed",
    "verified": true
  },
  "cost": 0.01,
  "balance_remaining": 1.92
}
```

#### 4. Local Taxi Prices

```bash
POST /api/taxi-prices
Content-Type: application/json

{
  "pickup": "LAX Airport",
  "dropoff": "Downtown Los Angeles",
  "pickup_coords": [33.9416, -118.4085],
  "dropoff_coords": [34.0522, -118.2437],
  "time": "2025-11-28T18:00:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "route": "LAX → Downtown LA",
    "distance_miles": 16.2,
    "estimates": [
      {
        "provider": "UberX",
        "price_min": 32,
        "price_max": 38,
        "surge_multiplier": 1.2,
        "eta_minutes": 8
      },
      {
        "provider": "Lyft",
        "price_min": 29,
        "price_max": 35,
        "surge_multiplier": 1.0,
        "eta_minutes": 10
      },
      {
        "provider": "Yellow Cab",
        "price_estimate": 45,
        "metered": true,
        "eta_minutes": 12
      }
    ],
    "last_updated": "2025-11-28T14:30:00Z"
  },
  "cost": 0.03,
  "balance_remaining": 1.89
}
```

#### 5. Check Balance

```bash
GET /balance/{your_wallet_public_key}
```

**Response:**
```json
{
  "public_key": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
  "balance_usd": 1.89,
  "queries_remaining": {
    "flights": 37,
    "delays": 94,
    "borders": 189,
    "taxis": 63
  }
}
```

## 🔄 Payment Flow

### First-Time Users

1. Make your first request with `X-User-Wallet` header
2. System automatically credits $2.00 welcome bonus
3. Query cost is deducted from your balance
4. Continue querying until balance depletes

### When Balance Runs Out

If your balance is insufficient, you'll receive **HTTP 402 Payment Required**:

```json
{
  "error": "Payment Required",
  "message": "Insufficient balance. Please top up your account.",
  "amount_needed_usd": 0.05,
  "merchant_wallet": "G5SaT8YvV2fT7w...x9P",
  "accepted_tokens": ["SOL", "USDC"],
  "instructions": {
    "step_1": "Send payment to merchant wallet",
    "step_2": "Include transaction signature in X-Payment-Signature header",
    "step_3": "Retry your request"
  }
}
```

### Top-Up Process

1. Send SOL or USDC to the merchant wallet shown in the 402 response
2. Copy your transaction signature from your wallet
3. Retry your request with the signature:

```bash
curl -X POST http://localhost:8000/api/flights \
  -H "X-User-Wallet: YourWallet" \
  -H "X-Payment-Signature: 5j7k8...TransactionHash" \
  -H "Content-Type: application/json" \
  -d '{"origin":"JFK","destination":"LAX",...}'
```

4. System verifies payment on-chain and credits your account
5. Your query proceeds automatically

## 🗂️ Data Sources

### Flights
- Google Flights API
- Kayak Meta-Search
- Skyscanner Aggregator
- Direct airline APIs (United, Delta, American, Southwest)
- Momondo, Cheapflights
- **Updated:** Hourly

### Transit Delays
- Amtrak Real-Time API
- Greyhound Status Feeds
- FlixBus Live Tracker
- European Rail (DB, SNCF, Trenitalia via third-party)
- **Updated:** Real-time (streaming)

### Border Crossings
- Official CBP (Customs and Border Protection) JSON Feed
- CBSA (Canada Border Services) for Canadian crossings
- **Updated:** Every 15 minutes

### Taxi/Rideshare
- Uber Price Estimates API
- Lyft Cost Estimator
- Local taxi commission rate tables
- Real-time surge/demand pricing
- **Updated:** Real-time

## 🏗️ Architecture

```
Request → 402 Middleware → Balance Check → Data Aggregator → Response
            ↓                    ↓              ↓
       Payment Gate         SQLite Ledger   Multi-Source APIs
            ↓                                   ↓
    Solana Verification              [Flights, Buses, Borders, Taxis]
```

### Components

- **FastAPI Server**: Async Python web framework for high-throughput API
- **Layer402Middleware**: Enforces micropayment requirements before data access
- **Ledger System**: SQLite-based balance tracking with atomic transactions
- **Payment Verifier**: On-chain Solana transaction verification
- **Data Aggregators**: Specialized scrapers/API clients for each data source
- **Cache Layer**: Redis-backed caching for frequently requested routes

## 🔒 Security & Privacy

- **No Personal Data Storage**: Only wallet addresses and balance info
- **On-Chain Verification**: All payments verified against Solana blockchain
- **No API Keys Required**: Zero registration friction
- **Rate Limiting**: Per-wallet rate limits prevent abuse
- **HTTPS Only**: All production endpoints enforce TLS
- **Open Source**: Full code transparency

## 📊 Why TravelPay402?

### For Travelers

**Traditional travel sites:**
- Show outdated prices (cached for hours)
- Include sponsored/boosted results
- Require email signup for alerts
- Bombard you with ads and upsells

**TravelPay402:**
- Pay only for fresh data you actually use
- No ads, no tracking, no email required
- All sources aggregated and ranked by price
- Data freshness guaranteed (hourly updates minimum)

### For the Industry

TravelPay402 proves micropayments work for consumer use cases. HTTP 402 has existed since 1997 but was never adopted because traditional payment rails couldn't support sub-dollar transactions. Solana changes that.

**This is useful for travelers, not developers.** We're not building an API for apps - we're building a service for humans who need real-time travel intelligence right now.

## 🌍 Coverage

### Flights
- **Supported:** All major airports worldwide (5,000+ routes)
- **Airlines:** 100+ carriers including budget airlines
- **Search Engines:** 20+ aggregators

### Transit
- **Supported:** US (Amtrak, Greyhound, Megabus), Canada (VIA Rail), Europe (major routes)
- **Coverage:** 500+ intercity routes

### Borders
- **Supported:** All US-Mexico crossings (25+), all US-Canada crossings (100+)
- **Data Source:** Official government feeds only

### Taxis
- **Supported:** 50+ major cities in US, Canada, Europe
- **Services:** Uber, Lyft, local taxis, regional services

## 💻 Development

### Project Structure

```
travelpay402/
├── src/
│   ├── main.py                 # FastAPI app & routes
│   ├── middleware.py           # HTTP 402 payment enforcement
│   ├── ledger.py              # Balance management
│   ├── payment.py             # Solana transaction verification
│   └── aggregators/
│       ├── flights.py         # Flight price aggregation
│       ├── transit.py         # Bus/train delay tracking
│       ├── border_agent.py    # Border wait times
│       └── taxis.py           # Taxi/rideshare pricing
├── tests/
│   ├── test_api.py
│   ├── test_ledger.py
│   └── test_aggregators.py
└── .env
```

### Tech Stack

- **Backend:** Python 3.10+, FastAPI, uvicorn
- **Database:** SQLite (aiosqlite for async)
- **Blockchain:** Solana Web3.py, solders
- **HTTP Client:** httpx (async)
- **Testing:** pytest

### Running Tests

```bash
pytest tests/ -v
```

## 🚧 Roadmap

- [ ] Mobile app (iOS/Android) with built-in wallet
- [ ] Hotel price comparison endpoint
- [ ] Car rental aggregation
- [ ] Multi-city flight routing
- [ ] Price drop alerts via Solana NFT subscriptions
- [ ] Lightning Network support for Bitcoin payments
- [ ] Historical price charts and trend analysis

## 📄 License

MIT License - See LICENSE file

## 🤝 Contributing

Pull requests welcome. For major changes, open an issue first.

## 📞 Support

- **Issues:** GitHub Issues
- **Contact:** [Your Email]
- **Status:** Check `/` endpoint for system status

---

**TravelPay402** - Real data. Real prices. Real-time. No bullshit.

*Pay for what you use. Use what you pay for.*
