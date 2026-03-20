"""
trade_executor.py — Jupiter V6 buy/sell execution with:
  - Dynamic position sizing (% of wallet balance)
  - Partial take-profits at 2x, 5x, 10x
  - Classic trailing stop-loss
  - Hard stop at -20%
  - Time-based stop
  - Emergency exit on post-entry rug signals
  - Paper trade mode (no real transactions)
  - Max open positions guard
  - Trade cooldown to prevent overtrading
"""
import asyncio
import base64
import logging
import os
import time
from typing import Optional

import aiohttp
from solana.rpc.types import TxOpts
from solders.transaction import VersionedTransaction

from core.config import (
    JUPITER_API, PAPER_TRADE, SOL_MINT,
    BASE_POSITION_SIZE_SOL, RISK_PCT_NORMAL, RISK_PCT_MAX,
    MAX_OPEN_POSITIONS, TRADE_COOLDOWN_SECONDS,
    NEW_COIN_TP_MULTIPLIER, GROWN_COIN_TP_MULTIPLIER,
    PARTIAL_TP_LEVELS, PARTIAL_TP_PCT,
    HARD_STOP_LOSS_PCT, TRAILING_STOP_TRIGGER_PCT, TRAILING_STOP_DISTANCE_PCT,
    TIME_STOP_MINUTES, PRIORITY_FEE_LAMPORTS, PRIORITY_FEE_AGGRESSIVE_LAMPORTS,
    MAX_DAILY_LOSS_PCT, EMERGENCY_SELL_ALL,
)
from core.wallet import WalletManager

logger = logging.getLogger(__name__)


class Position:
    """Tracks a single open trade."""

    def __init__(self, mint: str, symbol: str, entry_price: float,
                 size_sol: float, is_new_coin: bool):
        self.mint = mint
        self.symbol = symbol
        self.entry_price = entry_price
        self.current_price = entry_price
        self.size_sol = size_sol
        self.remaining_pct = 1.0          # fraction of position still open
        self.is_new_coin = is_new_coin
        self.high_water_mark = entry_price
        self.trailing_active = False
        self.tp_levels_hit: set = set()
        self.open_time = time.time()
        self.tp_target = NEW_COIN_TP_MULTIPLIER if is_new_coin else GROWN_COIN_TP_MULTIPLIER

    @property
    def profit_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.open_time) / 60


class TradeExecutor:
    """Executes trades via Jupiter V6 and manages open positions."""

    def __init__(self, wallet: WalletManager):
        self.wallet = wallet
        self.open_positions: dict[str, Position] = {}
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_trade_time: float = 0
        self._daily_start_balance: float = 0
        self._daily_pnl_sol: float = 0
        self._paper_pnl_sol: float = 0.0   # accumulated paper trade realized P&L
        # Per-source cooldown: new launches and established coins don't block each other
        self._last_trade_time_by_source: dict = {}
        # Optional async callback: notify(msg: str) — set by main.py
        self.notify = None  # type: Optional[callable]

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------
    async def execute_buy(self, signal: dict):
        """Main entry point. Called from trade queue processor."""
        mint = signal["mint"]
        symbol = signal.get("symbol", "?")
        is_new = signal.get("is_new_coin", True)
        confidence = signal.get("confidence", 75)

        # --- Guards ---
        if os.getenv("EMERGENCY_SELL_ALL", "False").lower() == "true":
            logger.warning("[EXECUTOR] Emergency sell-all active. No new buys.")
            return

        if len(self.open_positions) >= MAX_OPEN_POSITIONS:
            logger.info(f"[EXECUTOR] Max positions ({MAX_OPEN_POSITIONS}) reached. Skipping {symbol}.")
            return

        if mint in self.open_positions:
            logger.info(f"[EXECUTOR] Already in position for {symbol}. Skipping.")
            return

        cooldown_remaining = TRADE_COOLDOWN_SECONDS - (
            time.time() - self._last_trade_time_by_source.get(
                signal.get("source", "unknown"), 0
            )
        )
        if cooldown_remaining > 0:
            logger.info(f"[EXECUTOR] Cooldown active ({cooldown_remaining:.0f}s) for source={signal.get('source')}. Skipping {symbol}.")
            return

        # --- Daily loss limit ---
        if await self._daily_loss_exceeded():
            logger.warning("[EXECUTOR] Daily loss limit hit. No new trades today.")
            return

        # --- Position sizing ---
        size_sol = await self._calculate_position_size(confidence)
        source = signal.get("source", "unknown")
        logger.info(f"[EXECUTOR] BUY signal: {symbol} ({mint[:12]}...) | size={size_sol:.4f} SOL | conf={confidence}")

        if PAPER_TRADE:
            await self._paper_buy(mint, symbol, size_sol, is_new, source)
            return

        await self._real_buy(mint, symbol, size_sol, is_new, confidence, source)

    async def _calculate_position_size(self, confidence: int) -> float:
        """Scale position size with wallet balance and confidence."""
        balance = await self.wallet.get_sol_balance()
        # If balance is 0 (devnet/unfunded), use base size for paper trading
        if balance < BASE_POSITION_SIZE_SOL:
            return BASE_POSITION_SIZE_SOL
        # Scale risk % with confidence (75→2%, 100→5%)
        risk_pct = RISK_PCT_NORMAL + (confidence - 75) / 25 * (RISK_PCT_MAX - RISK_PCT_NORMAL)
        risk_pct = min(risk_pct, RISK_PCT_MAX)
        size = max(balance * risk_pct, BASE_POSITION_SIZE_SOL)
        size = min(size, balance * RISK_PCT_MAX)
        return round(size, 6)

    async def _paper_buy(self, mint: str, symbol: str, size_sol: float, is_new: bool, source: str = "unknown"):
        # Fetch real current price for accurate paper trade simulation
        real_price = await self._get_current_price(mint)
        entry_price = real_price if real_price and real_price > 0 else 0.000001
        pos = Position(mint, symbol, entry_price, size_sol, is_new)
        self.open_positions[mint] = pos
        self._last_trade_time = time.time()
        self._last_trade_time_by_source[source] = time.time()
        logger.info(
            f"[PAPER] BUY {size_sol:.4f} SOL of {symbol} @ ${entry_price:.8f} | "
            f"target={'10x' if is_new else '3x'}"
        )

    async def _real_buy(self, mint: str, symbol: str, size_sol: float,
                        is_new: bool, confidence: int, source: str = "unknown"):
        """Execute real buy via Jupiter V6 swap API."""
        session = await self._get_session()
        lamports = self.wallet.sol_to_lamports(size_sol)
        fee = PRIORITY_FEE_AGGRESSIVE_LAMPORTS if is_new else PRIORITY_FEE_LAMPORTS

        try:
            # Step 1: Get quote
            quote_url = (
                f"{JUPITER_API}/quote"
                f"?inputMint={SOL_MINT}"
                f"&outputMint={mint}"
                f"&amount={lamports}"
                f"&slippageBps=1500"  # 15% slippage for speed on new launches
            )
            async with session.get(quote_url) as resp:
                if resp.status != 200:
                    logger.error(f"[EXECUTOR] Quote failed HTTP {resp.status} for {symbol}")
                    return
                quote = await resp.json()

            if "error" in quote:
                logger.error(f"[EXECUTOR] Quote error for {symbol}: {quote['error']}")
                return

            # Step 2: Get swap transaction
            swap_payload = {
                "quoteResponse": quote,
                "userPublicKey": str(self.wallet.pubkey),
                "wrapAndUnwrapSol": True,
                "prioritizationFeeLamports": fee,
                "dynamicComputeUnitLimit": True,
            }
            async with session.post(f"{JUPITER_API}/swap", json=swap_payload) as resp:
                if resp.status != 200:
                    logger.error(f"[EXECUTOR] Swap tx failed HTTP {resp.status} for {symbol}")
                    return
                swap_data = await resp.json()

            if "swapTransaction" not in swap_data:
                logger.error(f"[EXECUTOR] No swapTransaction in response for {symbol}")
                return

            # Step 3: Sign and send
            # solders VersionedTransaction: reconstruct with signed message
            raw_bytes = base64.b64decode(swap_data["swapTransaction"])
            unsigned_tx = VersionedTransaction.from_bytes(raw_bytes)
            signed_tx = VersionedTransaction(unsigned_tx.message, [self.wallet.keypair])
            tx_bytes = bytes(signed_tx)

            send_resp = await self.wallet.client.send_raw_transaction(
                tx_bytes,
                opts=TxOpts(skip_preflight=True, max_retries=3),
            )
            sig = send_resp.value
            logger.info(f"[EXECUTOR] ✅ BUY sent: {symbol} | tx={sig} | {size_sol:.4f} SOL")

            # Record position (entry price fetched from quote output)
            out_amount = int(quote.get("outAmount", 1))
            entry_price = lamports / out_amount if out_amount > 0 else 0.000001
            pos = Position(mint, symbol, entry_price, size_sol, is_new)
            self.open_positions[mint] = pos
            self._last_trade_time = time.time()
            self._last_trade_time_by_source[source] = time.time()

        except Exception as e:
            logger.error(f"[EXECUTOR] Buy failed for {symbol}: {e}")

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------
    async def execute_sell(self, mint: str, reason: str, fraction: float = 1.0):
        """Sell a fraction (0.0–1.0) of a position."""
        pos = self.open_positions.get(mint)
        if not pos:
            return

        sell_pct = min(fraction, pos.remaining_pct)
        symbol = pos.symbol

        if PAPER_TRADE:
            pnl_pct = (pos.current_price - pos.entry_price) / pos.entry_price * 100 if pos.entry_price else 0
            # Realized P&L in SOL for this partial/full sell
            realized_sol = pos.size_sol * sell_pct * (pnl_pct / 100)
            self._paper_pnl_sol += realized_sol
            logger.info(
                f"[PAPER] SELL {sell_pct*100:.0f}% of {symbol} | "
                f"reason={reason} | P&L={pnl_pct:+.1f}% | realized={realized_sol:+.4f} SOL"
            )
            pos.remaining_pct -= sell_pct
            if pos.remaining_pct <= 0.01:
                del self.open_positions[mint]
            # Fire Telegram alert on notable exits
            if self.notify and abs(pnl_pct) >= 50:
                emoji = "🚀" if pnl_pct > 0 else "🔴"
                asyncio.create_task(self.notify(
                    f"{emoji} {symbol} SELL ({reason}) | P&L: {pnl_pct:+.1f}% | {realized_sol:+.4f} SOL"
                ))
            return

        # Real sell via Jupiter
        session = await self._get_session()
        balance_sol = pos.size_sol * sell_pct
        lamports = self.wallet.sol_to_lamports(balance_sol)

        try:
            quote_url = (
                f"{JUPITER_API}/quote"
                f"?inputMint={mint}"
                f"&outputMint={SOL_MINT}"
                f"&amount={lamports}"
                f"&slippageBps=2000"  # wider slippage on exit for speed
            )
            async with session.get(quote_url) as resp:
                if resp.status != 200:
                    logger.error(f"[EXECUTOR] Sell quote failed for {symbol}")
                    return
                quote = await resp.json()

            swap_payload = {
                "quoteResponse": quote,
                "userPublicKey": str(self.wallet.pubkey),
                "wrapAndUnwrapSol": True,
                "prioritizationFeeLamports": PRIORITY_FEE_AGGRESSIVE_LAMPORTS,
                "dynamicComputeUnitLimit": True,
            }
            async with session.post(f"{JUPITER_API}/swap", json=swap_payload) as resp:
                swap_data = await resp.json()

            raw_bytes = base64.b64decode(swap_data["swapTransaction"])
            unsigned_tx = VersionedTransaction.from_bytes(raw_bytes)
            signed_tx = VersionedTransaction(unsigned_tx.message, [self.wallet.keypair])
            send_resp = await self.wallet.client.send_raw_transaction(
                bytes(signed_tx),
                opts=TxOpts(skip_preflight=True, max_retries=3),
            )
            logger.info(f"[EXECUTOR] ✅ SELL {symbol} | reason={reason} | tx={send_resp.value}")

            pos.remaining_pct -= sell_pct
            if pos.remaining_pct <= 0.01:
                del self.open_positions[mint]

        except Exception as e:
            logger.error(f"[EXECUTOR] Sell failed for {symbol}: {e}")

    # ------------------------------------------------------------------
    # Position management loop
    # ------------------------------------------------------------------
    async def manage_positions(self):
        """
        Runs every 5 seconds. Updates prices, checks TP/SL/trailing/time stops.
        Re-reads EMERGENCY_SELL_ALL from env at runtime so it can be toggled
        without restarting the bot (set EMERGENCY_SELL_ALL=True in .env and
        send SIGHUP, or just restart — the flag is checked every 5s).
        """
        while True:
            try:
                # Re-read at runtime so env changes take effect without restart
                emergency = os.getenv("EMERGENCY_SELL_ALL", "False").lower() == "true"

                if emergency and self.open_positions:
                    logger.warning("[EXECUTOR] EMERGENCY SELL ALL triggered!")
                    for mint in list(self.open_positions.keys()):
                        await self.execute_sell(mint, "emergency_sell_all")

                for mint in list(self.open_positions.keys()):
                    pos = self.open_positions.get(mint)
                    if not pos:
                        continue

                    # Fetch current price
                    price = await self._get_current_price(mint)
                    if price and price > 0:
                        pos.current_price = price

                    # Update high water mark
                    if pos.current_price > pos.high_water_mark:
                        pos.high_water_mark = pos.current_price

                    pnl = pos.profit_pct

                    # --- Hard stop-loss ---
                    if pnl <= HARD_STOP_LOSS_PCT:
                        logger.warning(f"[STOP] Hard stop hit for {pos.symbol} | P&L={pnl*100:.1f}%")
                        await self.execute_sell(mint, "hard_stop_loss")
                        continue

                    # --- Time-based stop ---
                    if pos.age_minutes >= TIME_STOP_MINUTES and pnl < 0.10:
                        logger.info(f"[STOP] Time stop for {pos.symbol} | age={pos.age_minutes:.0f}m | P&L={pnl*100:.1f}%")
                        await self.execute_sell(mint, "time_stop")
                        continue

                    # --- Partial take-profits ---
                    for level in PARTIAL_TP_LEVELS:
                        if level not in pos.tp_levels_hit and pnl >= (level - 1):
                            logger.info(f"[TP] Partial TP {level}x for {pos.symbol}")
                            await self.execute_sell(mint, f"partial_tp_{level}x", PARTIAL_TP_PCT)
                            pos.tp_levels_hit.add(level)

                    # --- Full take-profit ---
                    if pnl >= (pos.tp_target - 1):
                        logger.info(f"[TP] Full TP {pos.tp_target}x for {pos.symbol}!")
                        await self.execute_sell(mint, f"full_tp_{pos.tp_target}x")
                        continue

                    # --- Trailing stop ---
                    if pnl >= TRAILING_STOP_TRIGGER_PCT:
                        pos.trailing_active = True

                    if pos.trailing_active and pos.high_water_mark > pos.entry_price:
                        drop_from_high = (pos.high_water_mark - pos.current_price) / pos.high_water_mark
                        if drop_from_high >= TRAILING_STOP_DISTANCE_PCT:
                            logger.info(
                                f"[STOP] Trailing stop for {pos.symbol} | "
                                f"high={pos.high_water_mark:.8f} | "
                                f"current={pos.current_price:.8f} | "
                                f"drop={drop_from_high*100:.1f}%"
                            )
                            await self.execute_sell(mint, "trailing_stop")

            except Exception as e:
                logger.error(f"[EXECUTOR] manage_positions error: {e}")

            await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # Price fetching (Birdeye → Dexscreener fallback)
    # ------------------------------------------------------------------
    async def _get_current_price(self, mint: str) -> Optional[float]:
        session = await self._get_session()
        # Try Jupiter price API (free, no key)
        try:
            url = f"https://price.jup.ag/v4/price?ids={mint}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = data.get("data", {}).get(mint, {}).get("price")
                    if price:
                        return float(price)
        except Exception:
            pass

        # Fallback: Dexscreener
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get("pairs", [])
                    if pairs:
                        return float(pairs[0].get("priceUsd", 0) or 0)
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Daily loss guard
    # ------------------------------------------------------------------
    async def _daily_loss_exceeded(self) -> bool:
        if self._daily_start_balance == 0:
            self._daily_start_balance = await self.wallet.get_sol_balance()
            return False
        current = await self.wallet.get_sol_balance()
        loss_pct = (self._daily_start_balance - current) / self._daily_start_balance
        return loss_pct >= MAX_DAILY_LOSS_PCT

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
