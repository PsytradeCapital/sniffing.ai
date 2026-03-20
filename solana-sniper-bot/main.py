"""
main.py — Async orchestrator for the Solana Sniper Bot.

Pipeline: Monitor → Analysis Queue → Analyzer → Trade Queue → Executor
         + Position Manager (trailing stops / TP)
         + Dashboard (console)
         + Auto-restart on crash
         + Daily loss limit + emergency sell
         + Telegram alerts (optional)
"""
import asyncio
import logging
import sys
import time
from datetime import date, datetime

import aiohttp
from colorama import Fore, init

from core.config import (
    PAPER_TRADE, AGGRESSIVE_MODE, MIN_DEPOSIT_MODE,
    MAX_DAILY_LOSS_PCT, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    LOG_FILE, LOG_LEVEL, EMERGENCY_SELL_ALL, MAX_OPEN_POSITIONS,
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
    # Silence noisy third-party loggers
    logging.getLogger("solanaweb3.rpc.httprpc.HTTPClient").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Telegram alerts (optional)
# ---------------------------------------------------------------------------
async def send_telegram(msg: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                url,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=aiohttp.ClientTimeout(total=5),
            )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Queue processors
# ---------------------------------------------------------------------------
async def analysis_worker(analyzer: TokenAnalyzer, analysis_queue: asyncio.Queue):
    """Drains analysis queue — spawns a non-blocking task per lead.
    Small stagger between tasks to avoid RugCheck rate limit bursts."""
    log = logging.getLogger("analysis_worker")
    while True:
        try:
            lead = await analysis_queue.get()
            asyncio.create_task(analyzer.analyze(lead))
            analysis_queue.task_done()
            await asyncio.sleep(0.8)  # stagger to avoid RugCheck rate limit bursts
        except Exception as e:
            log.error(f"Analysis worker error: {e}")


async def trade_worker(executor: TradeExecutor, trade_queue: asyncio.Queue):
    """Drains trade queue — executes buys sequentially."""
    log = logging.getLogger("trade_worker")
    while True:
        try:
            signal_data = await trade_queue.get()
            await executor.execute_buy(signal_data)
            trade_queue.task_done()
        except Exception as e:
            log.error(f"Trade worker error: {e}")


# ---------------------------------------------------------------------------
# Console dashboard
# ---------------------------------------------------------------------------
async def dashboard(
    wallet: WalletManager,
    executor: TradeExecutor,
    analysis_queue: asyncio.Queue,
    trade_queue: asyncio.Queue,
    start_time: float,
):
    log = logging.getLogger("dashboard")
    daily_start_bal: float = 0.0
    last_summary_date = date.today()

    while True:
        try:
            bal = await wallet.get_sol_balance()
            price = await wallet.get_sol_price_usd()
            bal_usd = bal * price

            if daily_start_bal == 0:
                daily_start_bal = bal

            # In paper mode, P&L comes from realized paper trades (balance doesn't change)
            if PAPER_TRADE:
                daily_pnl_sol = executor._paper_pnl_sol
                daily_pnl_pct = (daily_pnl_sol / daily_start_bal * 100) if daily_start_bal else 0
                simulated_bal = daily_start_bal + daily_pnl_sol
            else:
                daily_pnl_sol = bal - daily_start_bal
                daily_pnl_pct = (daily_pnl_sol / daily_start_bal * 100) if daily_start_bal else 0
                simulated_bal = bal
            uptime_h = (time.time() - start_time) / 3600

            pnl_color = Fore.GREEN if daily_pnl_sol >= 0 else Fore.RED
            mode_tag = "[PAPER]" if PAPER_TRADE else "[LIVE]"
            mode_color = Fore.YELLOW if PAPER_TRADE else Fore.RED

            print("\n" + "=" * 52)
            print(Fore.CYAN + f"  🦅  SOLANA SNIPER BOT  {mode_color}{mode_tag}")
            print("=" * 52)
            if PAPER_TRADE:
                print(Fore.WHITE + f"  Real Balance  : {bal:.4f} SOL  (${bal_usd:.2f})")
                print(Fore.YELLOW + f"  Paper Balance : {simulated_bal:.4f} SOL  (${simulated_bal * price:.2f})")
            else:
                print(Fore.WHITE + f"  Balance   : {bal:.4f} SOL  (${bal_usd:.2f})")
            print(pnl_color  + f"  Daily P&L : {daily_pnl_sol:+.4f} SOL  ({daily_pnl_pct:+.1f}%)")
            print(Fore.WHITE + f"  Positions : {len(executor.open_positions)} / {MAX_OPEN_POSITIONS}")
            print(Fore.WHITE + f"  Queues    : analysis={analysis_queue.qsize()}  trade={trade_queue.qsize()}")
            print(Fore.WHITE + f"  Uptime    : {uptime_h:.1f}h")
            print(Fore.WHITE + f"  Network   : {'AGGRESSIVE' if AGGRESSIVE_MODE else 'NORMAL'} | MIN_DEPOSIT={MIN_DEPOSIT_MODE}")

            # Print open positions
            if executor.open_positions:
                print(Fore.CYAN + "\n  Open Positions:")
                for mint, pos in executor.open_positions.items():
                    pnl = pos.profit_pct * 100
                    c = Fore.GREEN if pnl >= 0 else Fore.RED
                    phase = "P2" if pos.phase2_active else "P1"
                    stop_pct = (pos.stop_price - pos.entry_price) / pos.entry_price * 100
                    grace = " [grace]" if pos.age_minutes < pos.grace_period_minutes else ""
                    sol_price_now = price  # reuse fetched SOL price
                    invested_usd = pos.size_sol * sol_price_now
                    print(c + f"    {pos.symbol:10s} | {pos.size_sol:.4f} SOL (${invested_usd:.2f}) | P&L: {pnl:+.1f}% | stop: {stop_pct:+.1f}% | {phase}{grace} | age: {pos.age_minutes:.0f}m")

            # Print last 5 closed trades
            if executor.trade_history:
                closed = [t for t in executor.trade_history if t.get("pnl_sol") is not None]
                if closed:
                    print(Fore.CYAN + "\n  Last Closed Trades:")
                    for t in closed[-5:]:
                        c = Fore.GREEN if t["pnl_sol"] > 0 else Fore.RED
                        ts = datetime.fromtimestamp(t["timestamp"]).strftime("%H:%M")
                        print(c + f"    {t['symbol']:10s} | invested: {t['size_sol']:.4f} SOL | {t['pnl_pct']:+.1f}% | {t['pnl_sol']:+.4f} SOL | {t['reason']} @ {ts}")

            print("=" * 52 + "\n")

            # Daily summary (once per day)
            today = date.today()
            if today != last_summary_date:
                summary = (
                    f"📊 Daily Summary\n"
                    f"P&L: {daily_pnl_sol:+.4f} SOL ({daily_pnl_pct:+.1f}%)\n"
                    f"Balance: {bal:.4f} SOL"
                )
                await send_telegram(summary)
                log.info(summary)
                if PAPER_TRADE:
                    executor._paper_pnl_sol = 0.0
                else:
                    daily_start_bal = bal
                last_summary_date = today

            # Telegram alert on big daily loss
            if daily_pnl_pct <= -(MAX_DAILY_LOSS_PCT * 100 * 0.8):
                await send_telegram(f"⚠️ WARNING: Daily loss at {daily_pnl_pct:.1f}% — approaching limit!")

            # Telegram alert on big daily win (>50% up on the day)
            if daily_pnl_pct >= 50:
                await send_telegram(f"🚀 BIG WIN: Daily P&L at +{daily_pnl_pct:.1f}% ({daily_pnl_sol:+.4f} SOL)!")

        except Exception as e:
            log.error(f"Dashboard error: {e}")

        await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# Health check HTTP endpoint (for Replit / Render uptime pings)
# ---------------------------------------------------------------------------
async def health_server():
    """Tiny HTTP server on port 8080 so uptime monitors can ping it."""
    from aiohttp import web

    async def handle(_request):
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/health", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logging.getLogger("health").info("Health server running on :8080")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main():
    setup_logging()
    log = logging.getLogger("main")
    start_time = time.time()

    log.info("=" * 52)
    log.info("  Solana Sniper Bot — Starting up")
    log.info(f"  Mode: {'PAPER TRADE' if PAPER_TRADE else '🔴 LIVE TRADING'}")
    log.info(f"  Min deposit mode: {MIN_DEPOSIT_MODE}")
    log.info("=" * 52)

    await send_telegram("🚀 Solana Sniper Bot started!")

    # Init wallet
    wallet = WalletManager()
    bal = await wallet.get_sol_balance()
    price = await wallet.get_sol_price_usd()
    log.info(f"Wallet: {wallet.pubkey} | Balance: {bal:.4f} SOL (${bal * price:.2f})")

    if bal < 0.001 and not PAPER_TRADE:
        log.error("Wallet balance too low for live trading. Fund wallet or enable PAPER_TRADE_MODE=True")
        await wallet.close()
        return

    # Queues
    analysis_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    trade_queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    # Modules
    monitor = LaunchMonitor(analysis_queue)
    analyzer = TokenAnalyzer(trade_queue)
    executor = TradeExecutor(wallet)
    executor.notify = send_telegram  # wire Telegram alerts for big wins/losses

    # Spawn all tasks
    tasks = [
        asyncio.create_task(monitor.start(), name="monitor"),
        asyncio.create_task(analysis_worker(analyzer, analysis_queue), name="analysis_worker"),
        asyncio.create_task(trade_worker(executor, trade_queue), name="trade_worker"),
        asyncio.create_task(executor.manage_positions(), name="position_manager"),
        asyncio.create_task(dashboard(wallet, executor, analysis_queue, trade_queue, start_time), name="dashboard"),
        asyncio.create_task(health_server(), name="health"),
    ]

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log.info("Tasks cancelled — shutting down.")
    finally:
        monitor.stop()
        await analyzer.close()
        await executor.close()
        await wallet.close()
        log.info("Bot shut down cleanly.")
        await send_telegram("🛑 Solana Sniper Bot stopped.")


# ---------------------------------------------------------------------------
# Entry point with auto-restart on crash
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    log = logging.getLogger("main")
    RESTART_DELAY = 10  # seconds between crash restarts

    while True:
        try:
            asyncio.run(main())
            break  # clean exit (KeyboardInterrupt propagates below)
        except KeyboardInterrupt:
            print("\nBot stopped by user.")
            break
        except Exception as e:
            print(f"[CRASH] Bot crashed: {e}. Restarting in {RESTART_DELAY}s...")
            time.sleep(RESTART_DELAY)
