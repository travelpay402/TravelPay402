# TravelPay402 Protocol

**Machine-to-Machine Micropayments for Real-Time Travel Data via Solana**

TravelPay402 is a production-ready HTTP 402 payment protocol that enables autonomous machines and AI agents to access real-time travel intelligence through Solana-powered micropayments. Built on the principle that data should be paid for at the point of consumption, TravelPay402 implements the often-overlooked HTTP 402 status code to create a seamless pay-per-request infrastructure for border wait times, traffic conditions, and other time-sensitive transportation data.

## 🎯 Core Features

- **HTTP 402 Payment Required**: Native implementation of the HTTP 402 status code for API monetization
- **Solana Blockchain Integration**: Lightning-fast payment verification with sub-second finality
- **Freemium Credit System**: New users receive $2.00 welcome credit for immediate access
- **Real-Time Border Intelligence**: Live wait times from official CBP (Customs and Border Protection) data sources
- **Machine-First Architecture**: Designed for autonomous agents, IoT devices, and M2M communication
- **Zero-Setup Payments**: No registration required - just provide your Solana wallet address
- **Async-First Design**: Built on FastAPI with aiosqlite for maximum throughput

## 💡 Why TravelPay402?

Traditional API monetization requires accounts, subscriptions, and complex billing. TravelPay402 eliminates this friction by implementing true pay-per-use pricing at the protocol level. Each request costs exactly what it's worth - no more, no less.

**Perfect for:**
- Autonomous vehicles planning optimal routes
- AI agents requiring real-time transportation data
- Logistics companies optimizing delivery schedules
- Travel applications with on-demand data needs
- IoT devices in transportation networks
- Any system requiring sub-dollar API monetization

## 🏗️ Architecture

```
Client Request → 402 Middleware → Balance Check → Solana Verification → Data Response
                      ↓                              ↓
                 Ledger System                Payment Gateway
                      ↓                              ↓
                  SQLite DB                   Solana Mainnet
```

### Components

- **Layer402Middleware**: Intercepts all API requests and enforces payment requirements
- **Ledger System**: Manages user balances with atomic transaction support
- **Payment Verifier**: Validates Solana transactions against merchant wallet
- **Border Agent**: Aggregates real-time data from official government sources
- **Credit System**: Automatic welcome bonuses for first-time users

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Solana wallet address (for receiving payments)
- RPC endpoint access (default: Solana mainnet)

### Installation

```bash
git clone https://github.com/yourusername/travelpay402.git
cd travelpay402
pip install -r requirements.txt
```

### Configuration

Create a `.env` file:

```env
# Merchant Configuration
MERCHANT_WALLET=YourSolanaWalletAddressHere
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# Pricing Strategy
PRICE_PER_REQUEST_USD=0.05
WELCOME_BONUS_USD=2.00

# Server
PORT=8000
HOST=0.0.0.0
```

### Launch

```bash
cd src
python main.py
```

Server starts at `http://localhost:8000`

## 📡 API Usage

### Endpoints

#### `GET /` - Protocol Information
Returns protocol metadata and operational status.

#### `GET /api/borders/{crossing_id}` - Get Border Wait Times

**Headers Required:**
- `X-User-Wallet`: Your Solana wallet public key
- `X-Payment-Signature`: (Optional) Solana transaction signature for top-up

**Example:**
```bash
curl -H "X-User-Wallet: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU" \
     http://localhost:8000/api/borders/US-MEX-TIJUANA-PED
```

**Response:**
```json
{
  "success": true,
  "data": {
    "crossing": "US-Mexico Border - Tijuana",
    "specific_lane": "Pedestrian Lane",
    "wait_time_minutes": 45,
    "status": "Open",
    "last_updated": "2025-11-28 14:30:00",
    "source": "Official CBP API",
    "verified": true
  },
  "cost": 0.05,
  "balance_remaining": 1.95
}
```

### Payment Flow

1. **First Request**: Receive $2.00 welcome bonus automatically
2. **Subsequent Requests**: $0.05 deducted per API call
3. **Low Balance**: Receive 402 Payment Required with recharge instructions
4. **Top-Up**: Send SOL to merchant wallet, include signature in header

## 💳 Payment Integration

### For End Users

Simply provide your Solana wallet address in the `X-User-Wallet` header. Your first 40 requests are free ($2.00 welcome credit).

### For Merchants

Set your `MERCHANT_WALLET` in `.env` to receive payments. The system automatically:
- Tracks all user balances
- Verifies incoming Solana transactions
- Credits user accounts upon payment confirmation
- Maintains transaction audit trail

## 🔧 Development

### Project Structure

```
travelpay402/
├── src/
│   ├── main.py              # FastAPI application & routes
│   ├── middleware.py        # HTTP 402 enforcement layer
│   ├── ledger.py           # Balance & credit management
│   ├── payment.py          # Solana transaction verification
│   └── border_agent.py     # Data aggregation from CBP
├── tests/
│   ├── test_api.py         # API endpoint tests
│   └── test_ledger.py      # Ledger logic tests
└── .env                    # Configuration
```

### Running Tests

```bash
pytest tests/ -v
```

### Key Technologies

- **FastAPI**: High-performance async web framework
- **aiosqlite**: Async SQLite for ledger persistence
- **httpx**: Async HTTP client for payment verification
- **Solana Web3.py**: Blockchain interaction layer

## 🌐 Supported Border Crossings

Currently integrated with official CBP data sources:

- **US-Mexico Border**: All major pedestrian and vehicle crossings
- **US-Canada Border**: Primary international checkpoints
- **Data Sources**: Real-time feeds from US Customs and Border Protection

Additional crossing support available upon request.

## 📊 Pricing Model

| Tier | Cost per Request | Ideal For |
|------|-----------------|-----------|
| Welcome Credit | Free (first 40 requests) | Trying the service |
| Standard | $0.05 | Individual users, small apps |
| Volume* | $0.03 | High-frequency access (1000+ req/day) |
| Enterprise* | Custom | White-label solutions |

*Contact for volume and enterprise pricing

## 🔒 Security

- All balances stored in local SQLite with transaction atomicity
- Solana signatures verified against on-chain data
- No private keys stored or transmitted
- CORS configured for production environments
- Async architecture prevents request blocking

## 📈 Scalability

The protocol is designed for high-throughput scenarios:
- Async request handling (10,000+ concurrent connections)
- Database connection pooling
- Horizontal scaling via load balancer
- Stateless middleware design
- CDN-compatible response caching

## 🛣️ Roadmap

- **Payment Channels**: Support for Solana Lightning-style channels
- **Multi-Token Support**: USDC, USDT, and custom SPL tokens
- **Additional Data Sources**: Traffic, weather, flight delays
- **GraphQL Interface**: For complex data queries
- **Webhook System**: Real-time balance notifications
- **API Key Management**: Optional authentication layer

## 🤝 Contributing

TravelPay402 is production software, but we welcome contributions:

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License - See LICENSE file for details

## 🔗 Links

- **Documentation**: [Coming Soon]
- **API Status**: `GET /` endpoint
- **Support**: [Your Email/Discord]
- **Solana Explorer**: [View Merchant Wallet](https://explorer.solana.com/)

## 💬 Use Cases

**Logistics & Fleet Management**
Real-time border wait times enable dynamic routing for commercial vehicles, reducing idle time and fuel costs.

**Autonomous Vehicles**
Self-driving cars can query current conditions and adjust routes autonomously without human intervention.

**Travel Applications**
Mobile apps can offer live border crossing recommendations to travelers on a pay-per-query basis.

**Supply Chain Optimization**
International shipping companies can monitor crossing delays and adjust inventory schedules proactively.

---

**Built with Solana. Powered by Data. Enabled by HTTP 402.**

*TravelPay402 - Because every byte of real-time data has value.*