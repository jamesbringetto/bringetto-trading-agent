# CLAUDE.md - Bringetto Trading Agent

## Project Overview

**Bringetto Trading Agent** is an automated algorithmic day trading system designed to operate autonomously 24/5. It executes 5 rule-based day trading strategies simultaneously with strict risk management, performance monitoring, and automatic strategy disabling when performance degrades.

### Key Characteristics
- **Language**: Python 3.11+
- **Trading Mode**: Day trading with paper money (initial $100,000)
- **Broker**: Alpaca (paper trading API)
- **Deployment**: Railway (backend agent) + Vercel (dashboard)
- **Database**: PostgreSQL

### What's Implemented
- 5 concurrent rule-based trading strategies with technical indicators
- Real-time market data streaming via Alpaca WebSocket
- Strict risk management (circuit breakers, position limits, stop losses)
- Performance monitoring with automatic strategy disabling on poor results
- Full trade logging with decision reasoning
- REST API and live dashboard for observability
- Instrumentation pipeline showing data reception and decision flow

### What's Planned (Not Yet Implemented)
- Machine learning models (market regime detection, pattern recognition, parameter optimization)
- Post-trade analysis (A/B testing, win/loss attribution, strategy optimization)
- Background jobs (model retraining, nightly parameter optimization)
- Adaptive strategy parameters based on trade outcomes

### Project Goals
1. Execute 50-100+ trades in first 2 weeks to gather data
2. Run 5 day trading strategies simultaneously
3. Validate strategies before risking real money
4. Achieve >55% win rate and >1.5 profit factor before going live
5. Build ML pipeline to learn from trade history (future)

---

## Project Structure

```
bringetto-trading-agent/
├── agent/                    # Core trading agent (Railway deployment)
│   ├── config/              # Configuration management
│   │   ├── settings.py      # Environment-based config
│   │   ├── secrets.py       # API keys management
│   │   └── constants.py     # Trading constants
│   ├── data/                # Market data streaming
│   │   ├── streaming.py     # WebSocket handlers (real-time)
│   │   ├── historical.py    # Historical data fetching
│   │   └── preprocessor.py  # Data cleaning/preparation
│   ├── strategies/          # Trading strategies
│   │   ├── base.py          # Base strategy class
│   │   ├── orb.py           # Opening Range Breakout
│   │   ├── vwap_reversion.py # VWAP Mean Reversion
│   │   ├── momentum_scalp.py # Momentum Scalping
│   │   ├── gap_and_go.py    # Pre-Market Gap Trading
│   │   ├── eod_reversal.py  # End-of-Day Reversal
│   │   └── experimental/    # Sandbox for new strategies
│   ├── ml/                  # Machine learning models (PLANNED - not yet implemented)
│   │   └── __init__.py      # Placeholder for future ML modules
│   ├── execution/           # Order execution
│   │   ├── broker.py        # Alpaca integration
│   │   ├── router.py        # Order routing logic
│   │   ├── simulator.py     # Paper trading simulator
│   │   └── sizer.py         # Position sizing calculator
│   ├── risk/                # Risk management engine
│   │   ├── position_sizer.py # Risk-based sizing
│   │   ├── stop_loss.py     # Stop loss manager
│   │   ├── circuit_breaker.py # Daily/weekly loss limits
│   │   ├── validator.py     # Pre-trade risk checks
│   │   └── correlations.py  # Prevent correlated trades
│   ├── monitoring/          # Performance tracking
│   │   ├── metrics.py       # Real-time performance calculations
│   │   ├── logger.py        # Trade decision logging
│   │   ├── reporter.py      # Daily/weekly reports
│   │   └── alerter.py       # Slack/email alerts
│   ├── database/            # PostgreSQL models
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── repositories.py  # Data access layer
│   │   └── migrations/      # Alembic migrations
│   ├── analysis/            # Post-trade analysis (PLANNED - not yet implemented)
│   │   └── __init__.py      # Placeholder for future analysis modules
│   ├── api/                 # REST API for dashboard
│   │   ├── main.py          # FastAPI app
│   │   ├── routes/          # API endpoints
│   │   └── websocket.py     # Real-time updates to dashboard
│   ├── jobs/                # Background tasks (PLANNED - not yet implemented)
│   │   └── __init__.py      # Placeholder for future background jobs
│   └── main.py              # Agent entry point
├── dashboard/               # Web UI (Vercel deployment)
│   ├── app/                 # Next.js App Router
│   ├── components/          # React components
│   ├── lib/                 # Utilities
│   └── public/              # Static assets
├── tests/                   # Tests
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── fixtures/            # Test data
├── notebooks/               # Jupyter notebooks for backtesting
├── docker/                  # Docker configurations
├── scripts/                 # Utility scripts
├── .github/workflows/       # GitHub Actions CI/CD
├── .env.example             # Environment template
├── Procfile                 # Railway startup command
├── railway.json             # Railway configuration
├── vercel.json              # Vercel configuration
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Python project config
└── alembic.ini              # Database migrations config
```

---

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment template and configure
cp .env.example .env
# Edit .env with your Alpaca API keys
```

### Running the Agent
```bash
# Run the trading agent (main process)
python agent/main.py

# Run the FastAPI server (for dashboard communication)
uvicorn agent.api.main:app --reload --port 8000

# Run both (production)
python agent/main.py &
uvicorn agent.api.main:app --host 0.0.0.0 --port $PORT
```

### Database
```bash
# Initialize database
python scripts/setup_db.py

# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "description"
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=agent --cov-report=html

# Run specific test file
pytest tests/unit/test_strategies.py

# Run integration tests only
pytest tests/integration/
```

### Linting & Formatting
```bash
# Format code
ruff format .

# Check linting
ruff check .

# Fix auto-fixable issues
ruff check --fix .

# Type checking
mypy agent/
```

### Dashboard (Next.js)
```bash
cd dashboard

# Install dependencies
npm install

# Development server
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check
```

---

## Core Technologies

### Backend (Python)
| Package | Purpose | Status |
|---------|---------|--------|
| `alpaca-py` | Alpaca trading API SDK | Active |
| `fastapi` | REST API framework | Active |
| `uvicorn` | ASGI server | Active |
| `websockets` | Real-time data streaming | Active |
| `sqlalchemy` | ORM for PostgreSQL | Active |
| `alembic` | Database migrations | Active |
| `pandas` | Data analysis | Active |
| `numpy` | Numerical computing | Active |
| `ta` / `ta-lib` | Technical indicators | Active |
| `pydantic` | Data validation | Active |
| `loguru` | Structured logging | Active |
| `scikit-learn` | Machine learning | Installed, not yet used |
| `apscheduler` | Background job scheduling | Installed, not yet used |
| `redis` | Caching & pub/sub | Installed, not yet used |

### Frontend (TypeScript)
| Package | Purpose |
|---------|---------|
| `next` | React framework |
| `typescript` | Type safety |
| `tailwindcss` | Styling |
| `shadcn/ui` | UI components |
| `recharts` | Charts and graphs |
| `@tanstack/react-query` | Data fetching |
| `zustand` | State management |
| `socket.io-client` | WebSocket client |

---

## Trading Strategies

The agent runs 5 rule-based day trading strategies simultaneously. Each strategy uses fixed technical indicator parameters set at initialization. Strategies are automatically disabled after 5 consecutive losses or when win rate drops below 40% (after 20+ trades).

### 1. Opening Range Breakout (ORB)
- **Assets**: SPY, QQQ, IWM
- **Concept**: Trade breakouts from first 15-30 min range
- **Position Size**: $10,000 (10% of capital)
- **Max Positions**: 3 concurrent

### 2. VWAP Mean Reversion
- **Assets**: AAPL, MSFT, GOOGL, NVDA, TSLA
- **Concept**: Fade extreme deviations from VWAP
- **Position Size**: $8,000 (8% of capital)
- **Max Positions**: 4 concurrent

### 3. Momentum Scalping
- **Assets**: High-volume stocks (>5M daily volume)
- **Concept**: Ride strong intraday trends with quick scalps
- **Position Size**: $5,000 (5% of capital)
- **Max Positions**: 5 concurrent

### 4. Pre-Market Gap & Go
- **Assets**: Stocks with pre-market gap >3%
- **Concept**: Trade stocks that gap significantly overnight
- **Position Size**: $15,000 (15% of capital)
- **Max Positions**: 2 concurrent

### 5. End-of-Day Reversal
- **Assets**: SPY, QQQ
- **Concept**: Catch reversals in final hour of trading
- **Position Size**: $10,000 (10% of capital)
- **Max Positions**: 2 concurrent

---

## Risk Management Rules (NON-NEGOTIABLE)

### Position-Level
- Max risk per trade: **1% of portfolio** ($1,000 max loss)
- Stop loss: **ALWAYS required** (0.5-2% depending on strategy)
- Max position size: **15% of portfolio** ($15,000)

### Portfolio-Level
- Max concurrent positions: **10**
- Max capital deployed: **60%** ($60,000)
- Min cash reserve: **40%** ($40,000)
- Max daily loss: **2%** ($2,000) → CIRCUIT BREAKER
- Max weekly loss: **5%** ($5,000) → PAUSE TRADING
- Max monthly drawdown: **10%** ($10,000) → HUMAN REVIEW

### Strategy-Level
- Max trades per strategy per day: **10**
- Total max trades per day: **30**
- Max consecutive losses: **5** → disable strategy
- Strategy timeout: 3 losing days → disable

### System-Level
- Trading hours: **9:30 AM - 4:00 PM ET** only
- No trading first/last **5 minutes**
- No trading during major news events (FOMC, CPI, etc.)

---

## Environment Variables

Required environment variables (see `.env.example`):

```bash
# Alpaca API (PAPER TRADING)
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Trading Configuration
PAPER_TRADING_CAPITAL=100000.00
ENVIRONMENT=paper
TRADING_MODE=day_trading

# Risk Management
MAX_DAILY_LOSS_PCT=2.0
MAX_WEEKLY_LOSS_PCT=5.0
MAX_MONTHLY_DRAWDOWN_PCT=10.0
MAX_POSITION_SIZE_PCT=15.0
MAX_RISK_PER_TRADE_PCT=1.0
MAX_CONCURRENT_POSITIONS=10
MAX_TRADES_PER_DAY=30

# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# API
API_SECRET_KEY=your_secret_key

# Alerts (optional)
SLACK_WEBHOOK_URL=your_slack_webhook
EMAIL_ALERTS_TO=your_email@example.com
```

---

## Database Schema

Key tables in PostgreSQL:

### Actively Used
| Table | Purpose |
|-------|---------|
| `trades` | Every executed trade with entry/exit details |
| `trade_decisions` | Complete reasoning for EVERY trade decision |
| `strategies` | Strategy configurations and parameters |
| `strategy_performance` | Real-time performance metrics per strategy |
| `daily_summaries` | Daily performance rollups |
| `alerts` | System alerts and notifications |
| `system_health` | Agent health metrics |

### Schema Exists, Not Yet Populated
| Table | Purpose |
|-------|---------|
| `ab_tests` | A/B testing experiments (planned) |
| `market_regimes` | Detected market conditions (planned) |

---

## Code Conventions

### Python Style
- Follow PEP 8 with Ruff for formatting
- Use type hints for all function signatures
- Use Pydantic models for data validation
- Use async/await for I/O operations
- Use loguru for all logging

### Naming Conventions
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Strategy files: named after strategy (e.g., `orb.py`, `vwap_reversion.py`)

### Error Handling
- Always catch specific exceptions, never bare `except:`
- Log all errors with context using loguru
- Use custom exception classes in `agent/exceptions.py`
- Never swallow errors silently

### Trade Decision Logging
Every trade MUST be logged with:
1. **BEFORE entry**: Why entering, what signals triggered
2. **DURING**: Price action vs. expectations
3. **AFTER exit**: Profit/loss, what worked/didn't work
4. Complete market context (VIX, trend, volume, etc.)

---

## Deployment

### Railway (Backend)
- Auto-deploys from `main` branch
- PostgreSQL addon for database
- Health checks at `/health` endpoint
- Environment variables in Railway dashboard

### Vercel (Dashboard)
- Auto-deploys from `main` branch
- Next.js optimized deployment
- Environment variables for API URL

### CI/CD
- GitHub Actions for testing on PR
- Auto-deploy to Railway/Vercel on merge to main

---

## Important Guidelines for AI Assistants

### DO:
- Always implement stop losses - they are NON-NEGOTIABLE
- Log complete trade reasoning to the database
- Follow risk management limits strictly
- Use type hints and Pydantic models
- Write tests for new strategies
- Handle WebSocket disconnections gracefully
- Use async patterns for I/O operations

### DON'T:
- Never remove or bypass circuit breakers
- Never exceed position size limits (even for "perfect" setups)
- Never trade outside market hours
- Never deploy without testing
- Never store API keys in code
- Never use penny stocks (<$5) or low-volume stocks

### When Adding New Strategies:
1. Create new file in `agent/strategies/`
2. Inherit from `BaseStrategy` class
3. Implement required methods: `should_enter()`, `should_exit()`, `calculate_position_size()`
4. Add comprehensive logging
5. Write unit tests in `tests/unit/test_strategies.py`
6. Test in `experimental/` folder first

### When Modifying Risk Parameters:
1. Document the change and reasoning
2. Never increase max risk per trade above 1%
3. Never disable circuit breakers
4. Test thoroughly with backtesting before deploying

---

## Current Status

### Working
- [x] 5 rule-based strategies executing trades autonomously
- [x] Real-time market data streaming (WebSocket)
- [x] Risk management with circuit breakers and position limits
- [x] Performance monitoring with automatic strategy disabling
- [x] Trade decision logging with reasoning
- [x] REST API and live dashboard
- [x] Instrumentation pipeline for observability

### Not Yet Implemented
- [ ] ML models (market regime detection, pattern recognition, price prediction)
- [ ] Post-trade analysis (A/B testing, win/loss attribution)
- [ ] Background jobs (model retraining, nightly optimization)
- [ ] Adaptive strategy parameters
- [ ] Strategy parameter optimization from historical data

### Success Criteria (Before Real Money)

- [ ] Minimum 3 months profitable paper trading
- [ ] 50+ trades per strategy (statistical significance)
- [ ] Overall win rate >55%
- [ ] Profit factor >1.5
- [ ] Sharpe ratio >1.0
- [ ] Max drawdown <10%
- [ ] No critical bugs or system failures
- [ ] All trade decisions logged with reasoning
- [ ] Beats buy-and-hold SPY
- [ ] At least 2 strategies consistently profitable
- [ ] Daily loss circuit breaker tested and working

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `python agent/main.py` | Start trading agent |
| `pytest` | Run tests |
| `ruff check .` | Lint code |
| `ruff format .` | Format code |
| `alembic upgrade head` | Run migrations |
| `uvicorn agent.api.main:app --reload` | Start API server |
| `cd dashboard && npm run dev` | Start dashboard |
