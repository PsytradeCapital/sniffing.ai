"""
main.py — Async orchestrator for the Solana Sniper Bot.

Pipeline: Monitor → Analysis Queue → Analyzer → Trade Queue → Executor
         + Position Manager (trailing stops / TP)
         + Dashboard (console)
         + Auto-restart on crash
         + Daily loss limit + emergency sell
         + Telegram alerts (optional)
         + Gradual lot-size scaling as balance grows
"""
import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, date

import aiohttp
from colorama import Fore, Style, init

from core.config import (
    PAPER_TRADE, AGGRESSIVE_MODE, MIN_DEPOSIT_MODE,
    MAX_DAILY_LOSS_PCT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    LOG_FILE, LOG_LEVEL,
)
from core.wallet import WalletManager
from modules.monitor import LaunchMonitor
from modules.analysis import TokenAnalyzer
from modules.trade_executor import TradeExecutor

init(autoreset=True)

# ---------------------------------------------------------------------------
# Logging — file + console
# ---------------------------------------------------------------------------
def setup_logging():
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
    logging.basicConfig(level=level, format=fmt, handlers=handlers)


# ---------------------------------------------------------------------------
# Telegram alerts (optional)
# ---------------------------------------------------------------------------
async def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=aiohttp.ClientTimeout(total=5))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Queue processors
# ---------------------------------------------------------------------------
async def analysis_worker(analyzer: TokenAnalyzer, analysis_queue: asyncio.Queue):
    """Drains analysis queue — runs analysis on each lead."""
    logger = logging.getLogger("analysis_worker")
    while True:
        try:
            lead = await analysis_queue.get()
            asyncio.create_task(analyzer.analyze(lead))  # non-blocking per-token
            analysis_queue.task_done()
        except Exception as e:
            logger.error(f"Analysis worker error: {e}")


async def trade_worker(executor: TradeExecutor, trade_queue: asyncio.Queue):
    """Drains trade queue — executes buys."""
    logger = logging.getLogger("trade_worker")
    while True:
        try:
            signal = await trade_queue.get()
            await executor.execute_buy(signal)
            trade_queue.task_done()
        except Exception as e:
            logger.error(f"Trade worker error: {e}")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
async def dashboard(wallet: WalletManager, executor: TradeExecutor,
                    analysis_queue: asyncio.Queue, trade_queue: asyncio.Queue,
                    start_time: float):
    logger = logging.getLogger("dashboard")
    daily_start_bal: float = 0
    last_summary_date = date.today()

    while True:
        try:
            bal = await wallet.get_sol_balance()
            price = await wallet.get_sol_price_usd()
            bal_usd = bal * price

            if daily_start_bal == 0:
                daily_start_bal = bal

            pn