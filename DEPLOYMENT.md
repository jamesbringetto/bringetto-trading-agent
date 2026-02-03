# Deployment Guide

This guide walks you through deploying the Bringetto Trading Agent to Railway (backend) and Vercel (dashboard).

## Prerequisites

1. **Alpaca Account** - Sign up at https://app.alpaca.markets/signup
   - Navigate to Paper Trading > API Keys
   - Save your API Key ID and Secret Key

2. **GitHub Account** - Your code should be pushed to a GitHub repository

3. **Railway Account** - Sign up at https://railway.app (free tier available)

4. **Vercel Account** - Sign up at https://vercel.com (free tier available)

---

## Step 1: Deploy Backend to Railway

### 1.1 Create New Project

1. Go to https://railway.app/new
2. Click "Deploy from GitHub repo"
3. Select your `bringetto-trading-agent` repository
4. Railway will auto-detect the Python project

### 1.2 Add PostgreSQL Database

1. In your Railway project, click "+ New"
2. Select "Database" > "Add PostgreSQL"
3. Railway automatically sets `DATABASE_URL` for you

### 1.3 Configure Environment Variables

In Railway dashboard, go to your service > Variables tab and add:

```
# Required
ALPACA_API_KEY=your_paper_api_key
ALPACA_SECRET_KEY=your_paper_secret_key
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Trading Config
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

# API
API_SECRET_KEY=generate_a_random_string_here

# Optional: Alerts
SLACK_WEBHOOK_URL=
EMAIL_ALERTS_TO=
```

### 1.4 Configure Settings

1. Go to Settings tab
2. Set Root Directory to: `/` (leave blank for root)
3. Set Start Command to: `python -m agent.main & uvicorn agent.api.main:app --host 0.0.0.0 --port $PORT`
4. Enable "Always On" (in production settings) - costs extra but keeps agent running

### 1.5 Deploy

1. Click "Deploy" or push to your main branch
2. Wait for build to complete
3. Note your Railway URL (e.g., `your-app.up.railway.app`)

### 1.6 Verify Deployment

Visit `https://your-app.up.railway.app/health` - should return:
```json
{"status": "healthy", "trading_enabled": true}
```

---

## Step 2: Deploy Dashboard to Vercel

### 2.1 Import Project

1. Go to https://vercel.com/new
2. Click "Import Git Repository"
3. Select your `bringetto-trading-agent` repository

### 2.2 Configure Project

1. Set **Root Directory** to: `dashboard`
2. Framework Preset: Next.js (auto-detected)
3. Build Command: `npm run build` (default)
4. Output Directory: `.next` (default)

### 2.3 Add Environment Variables

```
NEXT_PUBLIC_API_URL=https://your-app.up.railway.app
```

Replace `your-app.up.railway.app` with your actual Railway URL from Step 1.5.

### 2.4 Deploy

1. Click "Deploy"
2. Wait for build to complete
3. Your dashboard is live at the Vercel URL

---

## Step 3: Connect the Pieces

### Update CORS (if needed)

If you see CORS errors, add your Vercel URL to the allowed origins in `agent/api/main.py`.

### Verify Full Stack

1. Visit your Vercel dashboard URL
2. You should see the trading dashboard
3. Check that data loads (strategies, status)

---

## Quick Reference

| Service | Platform | URL Pattern |
|---------|----------|-------------|
| Trading Agent | Railway | `your-app.up.railway.app` |
| API | Railway | `your-app.up.railway.app/api/*` |
| Dashboard | Vercel | `your-dashboard.vercel.app` |
| Database | Railway | Auto-configured |

---

## Troubleshooting

### Agent Not Starting

1. Check Railway logs for errors
2. Verify all environment variables are set
3. Ensure `DATABASE_URL` is auto-injected from PostgreSQL addon

### Dashboard Can't Connect to API

1. Check `NEXT_PUBLIC_API_URL` is set correctly
2. Verify Railway service is running
3. Check browser console for CORS errors

### No Trades Happening

1. Check if within market hours (9:30 AM - 4:00 PM ET)
2. Verify Alpaca API keys are for Paper Trading
3. Check Railway logs for strategy decisions

### Database Connection Errors

1. Ensure PostgreSQL addon is provisioned
2. Run migrations: In Railway, use the CLI or add a release command

---

## Costs (Estimated)

| Service | Free Tier | Paid |
|---------|-----------|------|
| Railway | $5/month credit | ~$10-20/month |
| Vercel | 100GB bandwidth | Free for personal |
| Alpaca | Free | Free (paper trading) |

**Total: ~$10-20/month** for a fully running trading agent.

---

## Security Reminders

- Never commit `.env` files
- Use Railway/Vercel environment variables for secrets
- Alpaca paper trading keys are separate from live keys
- The kill switch works even if the dashboard is down (via API)
