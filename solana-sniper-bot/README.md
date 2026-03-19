# Solana Sniper Bot

Automated meme coin sniper for Solana. Monitors Pump.fun + Raydium in real-time,
runs safety/momentum analysis, and executes trades via Jupiter V6.

---

## ⚠️ SECURITY WARNINGS

- **NEVER** use your main wallet. Generate a dedicated hot wallet for this bot.
- **NEVER** commit your `.env` file. It is in `.gitignore` for a reason.
- **NEVER** fund the bot wallet with more than you can afford to lose entirely.
- Start with `PAPER_TRADE_MODE=True` and test on devnet before going live.
- Meme coin trading is extremely high risk. Most coins go to zero.

---

## How to Fund Your Wallet Safely

1. Install [Phantom Wallet](https://phantom.app) and create a **brand new wallet**.
2. Export the private key: Settings → Security & Privacy → Export Private Key.
3. Convert it to Base58 format (Phantom already exports in Base58).
4. Paste it into your `.env` as `PRIVATE_KEY_BASE58`.
5. Send only your intended trading capital (e.g. $10–$50 worth of SOL) from your
   main wallet or a CEX (Coinbase, Binance) to this new wallet's public address.
6. **Never send your life savings.** Treat this as a high-risk experiment.

---

## Quick Start

### 1. Prerequisites

- Python 3.12+
- A Helius free API key: https://helius.dev (free tier is sufficient)
- A fresh Solana wallet (see above)

### 2. Install

```bash
cd solana-sniper-bot
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your keys
```

Minimum required fields in `.env`:
```
PRIVATE_KEY_BASE58=<your key>
PUBLIC_KEY=<your pubkey>
HELIUS_RPC_URL=https://devnet.helius-rpc.com/?api-key=<key>
HELIUS_WSS_URL=wss://devnet.helius-rpc.com/?api-key=<key>
PAPER_TRADE_MODE=True
NETWORK=devnet
```

### 4. Run (devnet paper trade first)

```bash
python main.py
```

### 5. Switch to mainnet

In `.env`:
```
NETWORK=mainnet
HELIUS_RPC_URL=https://mainnet.helius-rpc.com/?api-key=<key>
HELIUS_WSS_URL=wss://mainnet.helius-rpc.com/?api-key=<key>
PAPER_TRADE_MODE=True   # keep paper mode until you're confident
```

### 6. Go live (real trades)

```
PAPER_TRADE_MODE=False
```

---

## Run 24/7

### Option A — tmux (local / VPS, free)

```bash
tmux new -s sniper
python main.py
# Detach: Ctrl+B then D
# Reattach: tmux attach -t sniper
```

### Option B — systemd (Linux VPS)

Create `/etc/systemd/system/sniper.service`:
```ini
[Unit]
Description=Solana Sniper Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/solana-sniper-bot
ExecStart=/home/ubuntu/solana-sniper-bot/.venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/solana-sniper-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable sniper
sudo systemctl start sniper
sudo journalctl -u sniper -f   # view logs
```

### Option C — Docker (recommended for VPS)

```bash
cp .env.example .env   # fill in your keys
docker-compose up -d
docker-compose logs -f
```

### Option D — Replit (free, needs uptime ping)

1. Upload project to Replit.
2. The health server runs on port 8080 automatically.
3. Add your Replit URL to [UptimeRobot](https://uptimerobot.com) (free) to ping
   `https://your-repl.repl.co/health` every 5 minutes so it never sleeps.

### Option E — Railway / Render (free tier)

- Railway: connect GitHub repo, set env vars in dashboard, deploy.
- Render: create a "Background Worker", set env vars, deploy.
- Both have free tiers sufficient for this bot.

---

## Cheap VPS Upgrade (~$5/mo)

Once profitable, move to a dedicated VPS for reliability:

- [Hetzner](https://hetzner.com) — CX11, 2GB RAM, €3.79/mo
- [Contabo](https://contabo.com) — VPS S, 8GB RAM, ~$5/mo

```bash
# On VPS:
sudo apt update && sudo apt install -y docker.io docker-compose git
git clone <your-repo>
cd solana-sniper-bot
cp .env.example .env   # fill keys
docker-compose up -d
```

---

## Free API Tiers Used

| Service | Free Tier | Link |
|---------|-----------|------|
| Helius RPC | 100k credits/day | https://helius.dev |
| RugCheck | Unlimited (rate limited) | https://rugcheck.xyz |
| Jupiter | Free | https://jup.ag |
| Dexscreener | Free | https://dexscreener.com |
| Birdeye | Free (limited) | https://birdeye.so |
| Pump.fun WS | Free | pumpportal.fun |

---

## Project Structure

```
solana-sniper-bot/
├── core/
│   ├── config.py          # all constants + env loading
│   └── wallet.py          # keypair load, balance, SOL price
├── modules/
│   ├── monitor.py         # WebSocket listener (Pump.fun + Raydium)
│   ├── analysis.py        # safety + momentum + social checks
│   └── trade_executor.py  # Jupiter buy/sell + position management
├── data/logs/             # log files (gitignored)
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── main.py                # async orchestrator + dashboard
```

---

## Telegram Alerts Setup (optional but recommended)

1. Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
2. Copy the bot token → `TELEGRAM_BOT_TOKEN` in `.env`
3. Message your bot, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   to find your `chat_id` → `TELEGRAM_CHAT_ID` in `.env`

You'll receive alerts on big wins, losses, and daily summaries.
