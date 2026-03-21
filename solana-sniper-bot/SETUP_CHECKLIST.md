# Complete Setup Checklist — v2.0

## Prerequisites

- [ ] Python 3.12+ installed
- [ ] Git installed
- [ ] Fresh Solana wallet created (NOT your main wallet)
- [ ] Funded with test SOL (devnet) or real SOL (mainnet)

## API Keys Required

### 1. Helius RPC (Required)
- [ ] Sign up at https://helius.dev
- [ ] Get free API key
- [ ] Copy mainnet RPC URL

### 2. Jupiter API (Required for optimal performance)
- [ ] Sign up at https://portal.jup.ag
- [ ] Get free API key
- [ ] Copy API key

### 3. Birdeye (Optional, recommended)
- [ ] Sign up at https://birdeye.so
- [ ] Get free API key
- [ ] Copy API key

### 4. Telegram Bot (Optional, recommended)
- [ ] Message @BotFather on Telegram
- [ ] Create new bot with `/newbot`
- [ ] Copy bot token
- [ ] Message your bot
- [ ] Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
- [ ] Copy your chat_id

## Installation

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd solana-sniper-bot
```

### 2. Create Virtual Environment
```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate

# Linux/Mac:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

## Configuration

### 1. Create `.env` File
```bash
cp .env.example .env
```

### 2. Edit `.env` — Required Fields

```bash
# Wallet (REQUIRED)
PRIVATE_KEY_BASE58=your_base58_private_key
PUBLIC_KEY=your_public_key

# Network (REQUIRED)
NETWORK=mainnet  # or devnet for testing

# Helius RPC (REQUIRED)
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR_KEY
HELIUS_WSS_URL=wss://mainnet.helius-rpc.com/?api-key=YOUR_KEY

# Jupiter API (REQUIRED for optimal performance)
JUPITER_API_KEY=your_jupiter_api_key

# Bot Mode (REQUIRED)
PAPER_TRADE_MODE=True  # Start with paper trading
```

### 3. Edit `.env` — Optional Fields

```bash
# Birdeye (Optional, improves price accuracy)
BIRDEYE_API_KEY=your_birdeye_key

# Telegram Alerts (Optional, recommended)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Advanced Performance (Optional)
ENABLE_WEBSOCKET_PRICES=False  # Set True if you have premium RPC
```

## Testing

### 1. Test on Devnet First
```bash
# In .env
NETWORK=devnet
PAPER_TRADE_MODE=True
HELIUS_RPC_URL=https://devnet.helius-rpc.com/?api-key=YOUR_KEY
HELIUS_WSS_URL=wss://devnet.helius-rpc.com/?api-key=YOUR_KEY
```

### 2. Run Bot
```bash
python main.py
```

### 3. Verify Startup
Look for these in logs:
- [ ] `[WALLET] Balance: X.XXXX SOL`
- [ ] `[MONITOR] Connected to Pump.fun WebSocket`
- [ ] `[EXECUTOR] Position manager started`
- [ ] No error messages

### 4. Test Paper Trading on Mainnet
```bash
# In .env
NETWORK=mainnet
PAPER_TRADE_MODE=True
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=YOUR_KEY
```

Run for 24 hours and monitor:
- [ ] Tokens detected and analyzed
- [ ] Positions opened and closed
- [ ] Stop-loss triggers working
- [ ] Price updates every 0.5s
- [ ] Batch price fetching working (`[BATCH]` in logs)

## Going Live

### 1. Final Checks
- [ ] Tested in paper mode for 24+ hours
- [ ] No critical errors in logs
- [ ] Comfortable with bot behavior
- [ ] Wallet funded with amount you can afford to lose

### 2. Enable Real Trading
```bash
# In .env
PAPER_TRADE_MODE=False
```

### 3. Start Bot
```bash
python main.py
```

### 4. Monitor Closely
First 24 hours:
- [ ] Watch logs in real-time
- [ ] Verify real trades execute correctly
- [ ] Check stop-loss triggers are accurate
- [ ] Monitor P&L

## Performance Validation

### Check These in Logs

#### Batch Price Fetching
```
[BATCH] Fetched 3/3 prices from Jupiter v3
```
✅ Working if you see this every 0.5s

#### Fast Position Checks
```
[POS] BTC | P&L=+15.2% | stop=0.00001234 | high=0.00001456 | P1
```
✅ Working if timestamps show 0.5s intervals

#### Stop-Loss Triggers
```
[STOP] P1 trailing stop for SCAM | P&L=-45.2% | stop=-50.0%
```
✅ Working if exits happen within 1s of price drop

#### Price Feed Timeout
```
[STOP] Price feed dead for SCAM (10s) — exiting
```
✅ Working if timeout is 10s (not 15s)

## Troubleshooting

### Bot won't start
- [ ] Check Python version: `python --version` (need 3.12+)
- [ ] Check dependencies: `pip install -r requirements.txt`
- [ ] Check `.env` file exists and has required fields

### HTTP 401 Unauthorized
- [ ] Verify `JUPITER_API_KEY` in `.env`
- [ ] Get new key from https://portal.jup.ag

### No price updates
- [ ] Check `JUPITER_API_KEY` is set
- [ ] Verify Helius RPC URL is correct
- [ ] Check internet connection

### Batch fetching not working
- [ ] Verify `JUPITER_API_KEY` in `.env`
- [ ] Check logs for `[BATCH]` messages
- [ ] Ensure `BATCH_PRICE_FETCH = True` in `core/config.py`

### Still seeing -90%+ losses
- [ ] Verify `POSITION_CHECK_INTERVAL = 0.5` in `core/config.py`
- [ ] Check batch fetching is working
- [ ] Consider enabling WebSocket streaming
- [ ] Remember: 95%+ of memecoins are rugs, filters help but can't eliminate all risk

## Configuration Tuning

### If hitting API rate limits
```python
# In core/config.py
POSITION_CHECK_INTERVAL = 1.0  # slow down from 0.5s
```

### If getting false "price feed dead" exits
```python
# In core/config.py
PRICE_FEED_TIMEOUT = 15.0  # increase from 10s
```

### If you have premium RPC
```bash
# In .env
ENABLE_WEBSOCKET_PRICES=True
```

## 24/7 Deployment

### Option A: tmux (Simple)
```bash
tmux new -s sniper
python main.py
# Detach: Ctrl+B then D
# Reattach: tmux attach -t sniper
```

### Option B: Docker (Recommended)
```bash
docker-compose up -d
docker-compose logs -f
```

### Option C: systemd (Linux VPS)
See README.md for systemd service setup

## Monitoring

### Daily Checks
- [ ] Check logs for errors: `tail -f data/logs/bot.log`
- [ ] Verify wallet balance
- [ ] Review trade history: `python report.py`
- [ ] Check Telegram alerts (if configured)

### Weekly Checks
- [ ] Review P&L performance
- [ ] Adjust risk parameters if needed
- [ ] Update dependencies: `pip install -r requirements.txt --upgrade`
- [ ] Check for bot updates: `git pull origin main`

## Safety Reminders

- ⚠️ **Never use your main wallet**
- ⚠️ **Only fund with what you can afford to lose**
- ⚠️ **Start with paper trading**
- ⚠️ **Test on devnet first**
- ⚠️ **Monitor closely when going live**
- ⚠️ **95%+ of memecoins are rugs**
- ⚠️ **No bot can eliminate all risk**

## Support

- **Documentation**: See README.md, UPGRADE_GUIDE.md
- **Jupiter API**: See JUPITER_API_UPDATE.md
- **Testing**: See TESTING_CHECKLIST.md
- **Architecture**: See ARCHITECTURE_v2.md

## Quick Reference

### Start Bot
```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python main.py
```

### View Logs
```bash
tail -f data/logs/bot.log
```

### Generate Report
```bash
python report.py
```

### Emergency Stop
```bash
# In .env
EMERGENCY_SELL_ALL=True
```

Or press Ctrl+C to stop bot

---

**Version**: 2.0.0  
**Status**: Production Ready  
**Last Updated**: March 2024
