"""
config.py — All constants, risk rules, and environment loading.
Edit risk parameters here. Never hardcode secrets.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Network & Wallet
# ---------------------------------------------------------------------------
PRIVATE_KEY_BASE58: str = os.getenv("PRIVATE_KEY_BASE58", "")
PUBLIC_KEY: str = os.getenv("PUBLIC_KEY", "")
NETWORK: str = os.getenv("NETWORK", "devnet")  # "devnet" | "mainnet"

# Primary RPC (Helius free tier)
HELIUS_RPC_URL: str = os.getenv("HELIUS_RPC_URL", "https://api.devnet.solana.com")
HELIUS_WSS_URL: str = os.getenv("HELIUS_WSS_URL", "wss://api.devnet.solana.com")

# Fallback public RPC (used automatically if Helius fails)
FALLBACK_RPC_URL: str = os.getenv("FALLBACK_RPC_URL", "https://api.devnet.solana.com")
FALLBACK_WSS_URL: str = os.getenv("FALLBACK_WSS_URL", "wss://api.devnet.solana.com")

# Mainnet public fallback (auto-selected when NETWORK=mainnet and no Helius key)
_MAINNET_FALLBACK_RPC = "https://api.mainnet-beta.solana.com"
_MAINNET_FALLBACK_WSS = "wss://api.mainnet-beta.solana.com"
if NETWORK == "mainnet" and "devnet" in FALLBACK_RPC_URL:
    FALLBACK_RPC_URL = _MAINNET_FALLBACK_RPC
    FALLBACK_WSS_URL = _MAINNET_FALLBACK_WSS

# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
# Jupiter Swap API (v6 for swaps, v3 for prices)
# NOTE: Jupiter updated their API structure in 2024:
# - Swap/Quote API: https://api.jup.ag/swap/v2 (requires API key for production)
# - Price API: https://api.jup.ag/price/v3 (requires API key)
# - Legacy endpoints (quote-api.jup.ag, price.jup.ag/v4) are deprecated
# For now using lite-api.jup.ag which is free but will be deprecated Jan 2026
JUPITER_API: str = os.getenv("JUPITER_API_URL", "https://lite-api.jup.ag/swap/v1")
JUPITER_PRICE_API: str = os.getenv("JUPITER_PRICE_API_URL", "https://api.jup.ag/price/v3")
JUPITER_API_KEY: str = os.getenv("JUPITER_API_KEY", "")  # Get free key at portal.jup.ag

RUGCHECK_API: str = os.getenv("RUGCHECK_API_URL", "https://api.rugcheck.xyz/v1")
BIRDEYE_API: str = os.getenv("BIRDEYE_API_URL", "https://public-api.birdeye.so")
BIRDEYE_API_KEY: str = os.getenv("BIRDEYE_API_KEY", "")
TWITTER_API_KEY: str = os.getenv("TWITTER_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Bot Modes
# ---------------------------------------------------------------------------
PAPER_TRADE: bool = os.getenv("PAPER_TRADE_MODE", "True").lower() == "true"
AGGRESSIVE_MODE: bool = os.getenv("AGGRESSIVE_MODE", "False").lower() == "true"
MIN_DEPOSIT_MODE: bool = os.getenv("MIN_DEPOSIT_MODE", "True").lower() == "true"

# ---------------------------------------------------------------------------
# On-chain Program IDs
# ---------------------------------------------------------------------------
PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkz8z789tL66p59p336ziZnk7nyoX"
RAYDIUM_AMM_PROGRAM = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# ---------------------------------------------------------------------------
# Position Sizing
# ---------------------------------------------------------------------------
# Minimum trade size in SOL
BASE_POSITION_SIZE_SOL: float = 0.075 if MIN_DEPOSIT_MODE else 0.2

# Dynamic sizing: % of paper/real balance per trade
# With 0.5 SOL (~$44):  18% = 0.090 SOL (~$8.0)
# With 0.6 SOL (~$53):  18% = 0.108 SOL (~$9.6)
# With 1.0 SOL (~$89):  22% = 0.220 SOL (~$19.6)
# With 2.0 SOL (~$178): 28% = 0.560 SOL (~$49.8)
# With 5.0 SOL (~$445): 30% = 1.500 SOL (~$133)
RISK_PCT_MIN: float = 0.18   # 18% of balance at confidence=60
RISK_PCT_MAX: float = 0.30   # 30% of balance at confidence=100 (high conviction)
RISK_PCT_NORMAL: float = 0.22  # 22% default

# Max concurrent open positions
MAX_OPEN_POSITIONS: int = 3 if not AGGRESSIVE_MODE else 5

# Cooldown between trades (seconds) to prevent overtrading
TRADE_COOLDOWN_SECONDS: int = 30

# ---------------------------------------------------------------------------
# Risk / Reward Rules
# ---------------------------------------------------------------------------
# New coin (<$100k MC): target 10x+
NEW_COIN_MC_THRESHOLD: int = 100_000   # USD
NEW_COIN_TP_MULTIPLIER: float = 10.0
NEW_COIN_RR_MIN: float = 10.0

# Grown coin (>$100k MC): strict 1:3
GROWN_COIN_TP_MULTIPLIER: float = 3.0
GROWN_COIN_RR_MIN: float = 3.0

# Partial take-profit levels (multipliers)
PARTIAL_TP_LEVELS: list = [2.0, 5.0, 10.0]   # sell 33% at each
PARTIAL_TP_PCT: float = 0.33                   # portion to sell at each level

# Stop-loss — now handled per-position in Position.update_stop()
# These are kept for reference only; actual values set in Position.__init__
HARD_STOP_LOSS_PCT: float = -0.30             # new coin max loss (30%)
TRAILING_STOP_TRIGGER_PCT: float = 0.0        # unused — trailing active from entry
TRAILING_STOP_DISTANCE_PCT: float = 0.0       # unused — see Position class

# Phase 3 Moonshot Mode (NEW in v2.0)
# When a coin hits +200% (3x), the trailing stop WIDENS to give room for 1000-10000% runs
# This prevents premature exits on potential moonshots
# New coins: 35% trail (from 25% in P2)
# Old coins: 30% trail (from 20% in P2)
PHASE3_MOONSHOT_TRIGGER_PCT: float = 2.00     # triggers at +200% (3x)
PHASE3_TRAIL_NEW: float = 0.35                # 35% below high for new coins
PHASE3_TRAIL_OLD: float = 0.30                # 30% below high for established coins

# Time-based stop: exit if no movement after N minutes
TIME_STOP_MINUTES: int = 30

# ---------------------------------------------------------------------------
# Safety Limits
# ---------------------------------------------------------------------------
MAX_DAILY_LOSS_PCT: float = 0.30   # halt trading if down 30% on the day
# Set EMERGENCY_SELL_ALL=True in .env OR flip at runtime to liquidate all positions instantly
EMERGENCY_SELL_ALL: bool = os.getenv("EMERGENCY_SELL_ALL", "False").lower() == "true"

# ---------------------------------------------------------------------------
# Priority Fees (SOL) for fast transaction landing
# ---------------------------------------------------------------------------
PRIORITY_FEE_LAMPORTS: int = 500_000   # 0.0005 SOL default tip
PRIORITY_FEE_AGGRESSIVE_LAMPORTS: int = 1_000_000  # 0.001 SOL for hot launches

# ---------------------------------------------------------------------------
# Analysis Thresholds
# ---------------------------------------------------------------------------
MIN_CONFIDENCE_SCORE: int = 75
MIN_LIQUIDITY_USD: int = 5_000
MIN_VOLUME_5M_USD: int = 10_000
MIN_BUY_SELL_RATIO: float = 1.5   # more buys than sells

# ---------------------------------------------------------------------------
# Social Hype — Top 20 Meme Guru Handles (user-editable)
# ---------------------------------------------------------------------------
GURU_HANDLES: list = [
    "Ansem", "GiganticRebirth", "CryptoGodJohn", "blknoiz06",
    "notthreadguy", "inversebrah", "CryptoKaleo", "AltcoinSherpa",
    "CryptoWendyO", "Pentosh1", "SmallCapScientist", "CryptoTony101",
    "CryptoMichNL", "Trader_XO", "CryptoCapo_", "RookieXBT",
    "CryptoHayes", "CryptoJack", "CryptoSqueeze", "MoonOverlord",
]
GURU_MENTION_THRESHOLD: int = 3   # how many gurus must mention for hype signal

# ---------------------------------------------------------------------------
# Position Management & Price Fetching
# ---------------------------------------------------------------------------
# Polling interval for position management loop (seconds)
# 0.5s = 2 checks per second — fast enough to catch rugs before -97%
# 5.0s = legacy slow mode (not recommended for memecoins)
POSITION_CHECK_INTERVAL: float = 0.5

# Price feed staleness timeout (seconds)
# Exit position if no valid price update received within this window
PRICE_FEED_TIMEOUT: float = 10.0

# Batch price fetching: fetch all open positions in one API call
# Reduces API calls from N per loop to 1 per loop (N = open positions)
BATCH_PRICE_FETCH: bool = True

# WebSocket real-time price streaming (requires premium RPC like Helius)
# When enabled, uses WebSocket subscriptions for instant price updates
# Falls back to polling if WebSocket connection fails
ENABLE_WEBSOCKET_PRICES: bool = os.getenv("ENABLE_WEBSOCKET_PRICES", "False").lower() == "true"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE: str = "data/logs/bot.log"
LOG_LEVEL: str = "INFO"
