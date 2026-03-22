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
    JUPITER_API, JUPITER_PRICE_API, JUPITER_API_KEY, PAPER_TRADE, SOL_MINT,
    BASE_POSITION_SIZE_SOL, RISK_PCT_MIN, RISK_PCT_MAX,
    MAX_OPEN_POSITIONS, TRADE_COOLDOWN_SECONDS,
    NEW_COIN_TP_MULTIPLIER, GROWN_COIN_TP_MULTIPLIER,
    PARTIAL_TP_LEVELS, PARTIAL_TP_PCT,
    HARD_STOP_LOSS_PCT, TRAILING_STOP_TRIGGER_PCT, TRAILING_STOP_DISTANCE_PCT,
    TIME_STOP_MINUTES, PRIORITY_FEE_LAMPORTS, PRIORITY_FEE_AGGRESSIVE_LAMPORTS,
    MAX_DAILY_LOSS_PCT, EMERGENCY_SELL_ALL,
    POSITION_CHECK_INTERVAL, PRICE_FEED_TIMEOUT, BATCH_PRICE_FETCH,
    ENABLE_WEBSOCKET_PRICES, HELIUS_WSS_URL,
)
from core.wallet import WalletManager

logger = logging.getLogger(__name__)


class Position:
    """
    Tracks a single open trade with THREE-phase trailing stop system.

    Phase 1 (active immediately):
      - Stop loss starts at entry - hard_stop_distance
      - Every time price makes a new high, stop moves up by the SAME amount
        (1:1 ratchet — stop always stays hard_stop_distance below the high water mark)
      - New coin: stop distance = 50% of entry price
      - Old coin: stop distance = 40% of entry price

    Phase 2 (activates at first big win):
      - Stop tightens to trail_distance_p2 below current high water mark
      - New coin: triggers at +100% (2x), tightens to 25% below high
      - Old coin: triggers at +40%, tightens to 20% below high

    Phase 3 (MOONSHOT MODE - activates at 200%+ for potential 1000-10000% runners):
      - Stop WIDENS to give room for massive runs
      - Triggers at +200% (3x)
      - New coin: widens to 35% below high (from 25%)
      - Old coin: widens to 30% below high (from 20%)
      - Allows coins to breathe and run to 10x, 50x, 100x without premature exit
    """

    def __init__(self, mint: str, symbol: str, entry_price: float,
                 size_sol: float, is_new_coin: bool):
        self.mint = mint
        self.symbol = symbol
        self.entry_price = entry_price
        self.current_price = entry_price
        self.size_sol = size_sol
        self.remaining_pct = 1.0
        self.is_new_coin = is_new_coin
        self.high_water_mark = entry_price
        self.tp_levels_hit: set = set()
        self.open_time = time.time()
        self.tp_target = NEW_COIN_TP_MULTIPLIER if is_new_coin else GROWN_COIN_TP_MULTIPLIER
        self.token_amount: int = 0
        self.last_price_update: float = time.time()
        self.consecutive_price_failures: int = 0

        # --- Three-phase trailing parameters ---
        if is_new_coin:
            # New launches: wide stop — memecoins need room to breathe
            # P1: stop starts 50% below entry, trails 50% below high water mark
            # P2: triggers at +100% (2x), tightens to 25% below high
            # P3: triggers at +200% (3x), WIDENS to 35% below high (moonshot mode)
            self.hard_stop_distance = 0.50   # P1: 50% below entry / high
            self.phase2_trigger_pct = 1.00   # P2 kicks in at +100% (2x)
            self.phase2_trail_distance = 0.25  # P2: 25% below high
            self.phase3_trigger_pct = 2.00   # P3 kicks in at +200% (3x) — MOONSHOT
            self.phase3_trail_distance = 0.35  # P3: 35% below high (WIDER for big runs)
        else:
            # Established coins: slightly tighter but still room for moonshots
            # P1: stop starts 40% below entry, trails 40% below high water mark
            # P2: triggers at +40%, tightens to 20% below high
            # P3: triggers at +200% (3x), WIDENS to 30% below high (moonshot mode)
            self.hard_stop_distance = 0.40   # P1: 40% below entry / high
            self.phase2_trigger_pct = 0.40   # P2 kicks in at +40%
            self.phase2_trail_distance = 0.20  # P2: 20% below high
            self.phase3_trigger_pct = 2.00   # P3 kicks in at +200% (3x) — MOONSHOT
            self.phase3_trail_distance = 0.30  # P3: 30% below high (WIDER for big runs)

        # Stop level starts at entry - hard_stop_distance
        self.stop_price = entry_price * (1 - self.hard_stop_distance)
        self.phase2_active = False
        self.phase3_active = False  # NEW: Phase 3 moonshot mode
        self.trailing_active = True
        # Grace period: 5 minutes
        self.grace_period_minutes = 5

    @property
    def profit_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.open_time) / 60

    def update_stop(self):
        """
        Proportional ratchet: stop always trails by a fixed % below the high water mark.
        As price rises, stop rises with it maintaining the same distance ratio.
        Stop NEVER moves down.

        THREE-PHASE SYSTEM:
        Phase 1: Wide protection (50% new / 40% old)
        Phase 2: Tighter lock-in (25% new / 20% old) at 2x/1.4x
        Phase 3: MOONSHOT MODE (35% new / 30% old) at 3x — WIDENS to let winners run

        Example (new coin):
          Entry $1.00 → P1 stop $0.50 (50% below)
          Price rises to $2.00 (+100%) → P2 activates, stop $1.50 (25% below $2.00)
          Price rises to $3.00 (+200%) → P3 activates, stop $1.95 (35% below $3.00)
          Price rises to $10.00 (+900%) → P3 stop $6.50 (35% below $10.00)
          Price rises to $100.00 (+9900%) → P3 stop $65.00 (still 35% below)
          Price drops to $65.00 → SELL, locked +6400% profit

        Phase 3 gives room for 10x, 50x, 100x runs without premature exit.
        """
        # Update high water mark
        if self.current_price > self.high_water_mark:
            self.high_water_mark = self.current_price

        # Check phase 3 trigger (moonshot mode at +200%)
        if not self.phase3_active and self.profit_pct >= self.phase3_trigger_pct:
            self.phase3_active = True
            logger.info(
                f"[PHASE3] 🚀 MOONSHOT MODE activated for {self.symbol} at +{self.profit_pct*100:.0f}% | "
                f"Widening trail to {self.phase3_trail_distance*100:.0f}% for big runs"
            )

        # Check phase 2 trigger (first lock-in)
        elif not self.phase2_active and self.profit_pct >= self.phase2_trigger_pct:
            self.phase2_active = True

        # Select trailing distance based on active phase
        if self.phase3_active:
            distance = self.phase3_trail_distance  # WIDEST for moonshots
        elif self.phase2_active:
            distance = self.phase2_trail_distance  # Tighter lock-in
        else:
            distance = self.hard_stop_distance     # Initial wide protection

        # New stop = high water mark minus trailing distance
        new_stop = self.high_water_mark * (1 - distance)

        # Only ratchet UP, never down
        if new_stop > self.stop_price:
            self.stop_price = new_stop


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
        # Trade history for reporting
        self.trade_history: list = []
        # Blacklist: mints that exited at a loss — never re-enter these
        self._loss_blacklist: set = set()
        # Optional async callback: notify(msg: str) — set by main.py
        self.notify = None  # type: Optional[callable]
        # WebSocket connections for real-time price streaming
        self._ws_connections: dict = {}  # mint -> websocket connection
        self._ws_prices: dict = {}  # mint -> latest price from WebSocket
        self._ws_enabled = ENABLE_WEBSOCKET_PRICES

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

        if mint in self._loss_blacklist:
            logger.info(f"[EXECUTOR] {symbol} blacklisted (previous loss). Skipping.")
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
        size_sol = await self._calculate_position_size(confidence, is_new)
        source = signal.get("source", "unknown")
        logger.info(f"[EXECUTOR] BUY signal: {symbol} ({mint[:12]}...) | size={size_sol:.4f} SOL | conf={confidence}")

        if PAPER_TRADE:
            await self._paper_buy(mint, symbol, size_sol, is_new, source)
            return

        await self._real_buy(mint, symbol, size_sol, is_new, confidence, source)

    async def _calculate_position_size(self, confidence: int, is_new_coin: bool = True) -> float:
        """
        Scale position size with balance and confidence.
        In paper mode, scales off simulated paper balance so sizing grows with profits.
        
        IMPORTANT: Both new and established coins use THE SAME position size.
        Established coins are proven and deserve equal or more capital allocation.
        """
        if PAPER_TRADE:
            # Use paper balance (real balance + accumulated paper P&L) for realistic scaling
            real_balance = await self.wallet.get_sol_balance()
            balance = max(real_balance + self._paper_pnl_sol, BASE_POSITION_SIZE_SOL)
        else:
            balance = await self.wallet.get_sol_balance()

        if balance < BASE_POSITION_SIZE_SOL:
            return BASE_POSITION_SIZE_SOL

        # Scale risk linearly: confidence 60 → RISK_PCT_MIN, confidence 100 → RISK_PCT_MAX
        conf_clamped = max(60, min(confidence, 100))
        t = (conf_clamped - 60) / 40  # 0.0 at conf=60, 1.0 at conf=100
        risk_pct = RISK_PCT_MIN + t * (RISK_PCT_MAX - RISK_PCT_MIN)

        size = balance * risk_pct
        
        # SAME SIZE for both new and established coins
        # No multiplier - they get equal treatment
        
        size = max(size, BASE_POSITION_SIZE_SOL)
        size = min(size, balance * RISK_PCT_MAX)  # never exceed max risk
        return round(size, 4)

    async def _paper_buy(self, mint: str, symbol: str, size_sol: float, is_new: bool, source: str = "unknown"):
        # Fetch real current price for accurate paper trade simulation
        real_price = await self._get_current_price(mint)
        entry_price = real_price if real_price and real_price > 0 else 0.000001

        # Resolve symbol if still unknown — try Dexscreener one more time at buy
        if not symbol or symbol == "?":
            symbol = await self._resolve_symbol(mint)

        pos = Position(mint, symbol, entry_price, size_sol, is_new)
        self.open_positions[mint] = pos
        self._last_trade_time = time.time()
        self._last_trade_time_by_source[source] = time.time()
        # Record buy in trade history
        self.trade_history.append({
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": None,
            "size_sol": size_sol,
            "pnl_sol": None,
            "pnl_pct": None,
            "reason": "buy",
            "timestamp": time.time(),
            "mint": mint,
        })
        logger.info(
            f"[PAPER] BUY {size_sol:.4f} SOL of {symbol} @ ${entry_price:.8f} | "
            f"target={'10x' if is_new else '3x'}"
        )
        
        # Telegram alert for paper trades too
        if self.notify:
            asyncio.create_task(self.notify(
                f"🟢 [PAPER] BUY {symbol}\n"
                f"Size: {size_sol:.4f} SOL\n"
                f"Entry: ${entry_price:.8f}\n"
                f"Target: {'10x' if is_new else '3x'}\n"
                f"Mode: Paper Trading"
            ))

    async def _real_buy(self, mint: str, symbol: str, size_sol: float,
                        is_new: bool, confidence: int, source: str = "unknown"):
        """Execute real buy via Jupiter V6 swap API."""
        # Resolve symbol if still unknown
        if not symbol or symbol == "?":
            symbol = await self._resolve_symbol(mint)

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
            pos.token_amount = out_amount  # store actual tokens received for sell
            self.open_positions[mint] = pos
            self._last_trade_time = time.time()
            self._last_trade_time_by_source[source] = time.time()

            # Telegram alert
            if self.notify:
                asyncio.create_task(self.notify(
                    f"🟢 BUY {symbol}\n"
                    f"Size: {size_sol:.4f} SOL\n"
                    f"Entry: ${entry_price:.8f}\n"
                    f"Target: {'10x' if is_new else '3x'}\n"
                    f"tx: {sig}"
                ))

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
            
            # Record trade history (update the matching buy entry, or append new)
            buy_entry = next(
                (t for t in reversed(self.trade_history)
                 if t.get("mint") == mint and t["reason"] == "buy" and t["exit_price"] is None),
                None
            )
            sell_record = {
                "symbol": symbol,
                "entry_price": pos.entry_price,
                "exit_price": pos.current_price,
                "size_sol": pos.size_sol * sell_pct,
                "pnl_sol": realized_sol,
                "pnl_pct": pnl_pct,
                "reason": reason,
                "timestamp": time.time(),
                "mint": mint,
            }
            if buy_entry:
                buy_entry.update(sell_record)
            else:
                self.trade_history.append(sell_record)
            
            logger.info(
                f"[PAPER] SELL {sell_pct*100:.0f}% of {symbol} | "
                f"reason={reason} | P&L={pnl_pct:+.1f}% | realized={realized_sol:+.4f} SOL"
            )
            pos.remaining_pct -= sell_pct
            if pos.remaining_pct <= 0.01:
                del self.open_positions[mint]
                # Blacklist coins that closed at a loss — don't re-enter rugs
                if pnl_pct < 0:
                    self._loss_blacklist.add(mint)
            
            # Telegram alert for ALL paper exits (not just >50%)
            if self.notify:
                emoji = "🚀" if pnl_pct > 0 else "🔴"
                asyncio.create_task(self.notify(
                    f"{emoji} [PAPER] SELL {symbol}\n"
                    f"Reason: {reason}\n"
                    f"P&L: {pnl_pct:+.1f}%\n"
                    f"Realized: {realized_sol:+.4f} SOL\n"
                    f"Mode: Paper Trading"
                ))
            return

        # Real sell via Jupiter
        session = await self._get_session()
        # Use actual token amount received at buy time, scaled by sell fraction
        token_amount = getattr(pos, "token_amount", 0)
        if token_amount > 0:
            sell_token_amount = int(token_amount * sell_pct * pos.remaining_pct / pos.remaining_pct)
            # Clamp to what we still hold
            sell_token_amount = int(token_amount * sell_pct)
        else:
            # Fallback: estimate from SOL spent (less accurate but won't crash)
            sell_token_amount = self.wallet.sol_to_lamports(pos.size_sol * sell_pct)

        try:
            quote_url = (
                f"{JUPITER_API}/quote"
                f"?inputMint={mint}"
                f"&outputMint={SOL_MINT}"
                f"&amount={sell_token_amount}"
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

            # Calculate and log real P&L
            pnl_pct = (pos.current_price - pos.entry_price) / pos.entry_price * 100 if pos.entry_price else 0
            sol_out = int(quote.get("outAmount", 0)) / 1_000_000_000
            logger.info(f"[EXECUTOR] P&L {symbol}: {pnl_pct:+.1f}% | received {sol_out:.4f} SOL")

            if self.notify:
                emoji = "🚀" if pnl_pct > 0 else "🔴"
                asyncio.create_task(self.notify(
                    f"{emoji} SELL {symbol} ({reason})\n"
                    f"P&L: {pnl_pct:+.1f}%\n"
                    f"Received: {sol_out:.4f} SOL\n"
                    f"tx: {send_resp.value}"
                ))

            pos.remaining_pct -= sell_pct
            if pos.remaining_pct <= 0.01:
                del self.open_positions[mint]
                # Blacklist coins that closed at a loss — don't re-enter rugs
                if pnl_pct < 0:
                    self._loss_blacklist.add(mint)

        except Exception as e:
            logger.error(f"[EXECUTOR] Sell failed for {symbol}: {e}")

    # ------------------------------------------------------------------
    # Position management loop
    # ------------------------------------------------------------------
    async def manage_positions(self):
        """
        Runs every 0.5 seconds safely using batched API requests.
        Updates prices, ratchets stop prices, and checks exits instantly.
        """
        while True:
            try:
                emergency = os.getenv("EMERGENCY_SELL_ALL", "False").lower() == "true"
                if emergency and self.open_positions:
                    logger.warning("[EXECUTOR] EMERGENCY SELL ALL triggered!")
                    for mint in list(self.open_positions.keys()):
                        await self.execute_sell(mint, "emergency_sell_all")

                # Step 1: Batch fetch all prices in one fast network call
                open_mints = list(self.open_positions.keys())
                if not open_mints:
                    await asyncio.sleep(POSITION_CHECK_INTERVAL)
                    continue

                batch_prices = await self._get_batch_prices(open_mints)

                # Step 2: Iterate through positions with the fresh data
                for mint in open_mints:
                    pos = self.open_positions.get(mint)
                    if not pos:
                        continue

                    # --- Price update (WebSocket → Batch → Individual fallback) ---
                    price = None
                    
                    # Try WebSocket first (if enabled)
                    if self._ws_enabled:
                        price = await self._get_ws_price(mint)
                        if price and price > 0:
                            logger.debug(f"[WS] Using WebSocket price for {pos.symbol}: ${price:.8f}")
                    
                    # Fallback to batch price
                    if not price or price <= 0:
                        price = batch_prices.get(mint)
                    
                    # Final fallback to individual fetch
                    if not price or price <= 0:
                        price = await self._get_current_price(mint)
                    
                    if price and price > 0:
                        pos.current_price = price
                        pos.last_price_update = time.time()
                        pos.consecutive_price_failures = 0
                    else:
                        pos.consecutive_price_failures += 1
                        stale_seconds = time.time() - pos.last_price_update
                        # Exit after PRICE_FEED_TIMEOUT of no price data (tightened from 15s)
                        if stale_seconds > PRICE_FEED_TIMEOUT:
                            logger.warning(
                                f"[STOP] Price feed dead for {pos.symbol} ({stale_seconds:.0f}s) — exiting"
                            )
                            await self.execute_sell(mint, "price_feed_dead")
                            continue

                    # --- Ratchet stop upward FIRST, then check all exits ---
                    pos.update_stop()
                    pnl = pos.profit_pct
                    # Show current phase (P1, P2, or P3)
                    if pos.phase3_active:
                        phase = "P3-MOONSHOT"
                    elif pos.phase2_active:
                        phase = "P2"
                    else:
                        phase = "P1"

                    # --- Stop loss check ---
                    in_grace = pos.age_minutes < pos.grace_period_minutes
                    if pos.current_price <= pos.stop_price:
                        stop_pct = (pos.stop_price / pos.entry_price - 1) * 100
                        if in_grace:
                            reason = "hard_floor_stop"
                            logger.warning(
                                f"[STOP] Hard floor (grace) for {pos.symbol} | "
                                f"P&L={pnl*100:+.1f}% | floor={stop_pct:+.1f}%"
                            )
                        else:
                            reason = f"trailing_stop_{phase.lower()}"
                            logger.info(
                                f"[STOP] {phase} trailing stop for {pos.symbol} | "
                                f"P&L={pnl*100:+.1f}% | stop={stop_pct:+.1f}%"
                            )
                        # Fire sell order asynchronously so it doesn't block the loop for other coins
                        asyncio.create_task(self.execute_sell(mint, reason))
                        continue

                    # --- Time-based stop ---
                    if pos.age_minutes >= TIME_STOP_MINUTES and pnl < 0.05:
                        logger.info(
                            f"[STOP] Time stop for {pos.symbol} | "
                            f"age={pos.age_minutes:.0f}m | P&L={pnl*100:+.1f}%"
                        )
                        asyncio.create_task(self.execute_sell(mint, "time_stop"))
                        continue

                    # --- Partial take-profits ---
                    for level in PARTIAL_TP_LEVELS:
                        if level not in pos.tp_levels_hit and pnl >= (level - 1):
                            logger.info(
                                f"[TP] Partial TP {level}x for {pos.symbol} | P&L={pnl*100:+.1f}%"
                            )
                            asyncio.create_task(
                                self.execute_sell(mint, f"partial_tp_{level}x", PARTIAL_TP_PCT)
                            )
                            pos.tp_levels_hit.add(level)

                    # --- Full take-profit ---
                    if pnl >= (pos.tp_target - 1):
                        logger.info(f"[TP] Full TP {pos.tp_target}x for {pos.symbol}!")
                        asyncio.create_task(self.execute_sell(mint, f"full_tp_{pos.tp_target}x"))
                        continue

            except Exception as e:
                logger.error(f"[EXECUTOR] manage_positions error: {e}")

            # Sleep interval reduced from 5.0 to POSITION_CHECK_INTERVAL (default 0.5s)
            await asyncio.sleep(POSITION_CHECK_INTERVAL)

    # ------------------------------------------------------------------
    # Price fetching (Birdeye → Dexscreener fallback)
    # ------------------------------------------------------------------
    async def _resolve_symbol(self, mint: str) -> str:
        """Last-chance symbol resolution from Dexscreener at buy time."""
        try:
            session = await self._get_session()
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get("pairs", [])
                    if pairs:
                        sym = pairs[0].get("baseToken", {}).get("symbol", "")
                        if sym:
                            return sym
        except Exception:
            pass
        return mint[:8]  # fallback to mint prefix

    async def _get_current_price(self, mint: str) -> Optional[float]:
        """
        Price fetch with 3 sources: Jupiter → Birdeye → Dexscreener.
        Returns None only if ALL three fail — reduces false price_feed_dead exits.
        
        NOTE: Jupiter Price API v3 requires API key. If no key, falls back to Birdeye/Dexscreener.
        """
        session = await self._get_session()

        # 1. Jupiter Price API v3 (requires API key, most accurate)
        if JUPITER_API_KEY:
            try:
                url = f"{JUPITER_PRICE_API}?ids={mint}"
                headers = {"x-api-key": JUPITER_API_KEY}
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price_data = data.get(mint, {})
                        price = price_data.get("usdPrice")
                        if price:
                            return float(price)
            except Exception:
                pass

        # 2. Birdeye (free tier, good coverage for new tokens)
        try:
            from core.config import BIRDEYE_API_KEY, BIRDEYE_API
            headers = {"X-API-KEY": BIRDEYE_API_KEY} if BIRDEYE_API_KEY else {}
            url = f"{BIRDEYE_API}/defi/price?address={mint}"
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = data.get("data", {}).get("value", 0)
                    if price and float(price) > 0:
                        return float(price)
        except Exception:
            pass

        # 3. Dexscreener (last resort — slower but very broad coverage)
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get("pairs", [])
                    if pairs:
                        price = float(pairs[0].get("priceUsd", 0) or 0)
                        if price > 0:
                            return price
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Daily loss guard
    # ------------------------------------------------------------------
    async def _daily_loss_exceeded(self) -> bool:
        current = await self.wallet.get_sol_balance()
        if self._daily_start_balance == 0:
            self._daily_start_balance = current
            return False
        if self._daily_start_balance == 0:
            return False
        loss_pct = (self._daily_start_balance - current) / self._daily_start_balance
        return loss_pct >= MAX_DAILY_LOSS_PCT

    # ------------------------------------------------------------------
    # Batch price fetching (reduces API calls from N to 1 per loop)
    # ------------------------------------------------------------------
    async def _get_batch_prices(self, mints: list[str]) -> dict[str, float]:
        """
        Fetch prices for multiple tokens in one API call.
        Returns dict: {mint: price}
        Falls back to individual fetching if batch fails.
        
        NOTE: Jupiter Price API v3 requires API key and supports up to 50 tokens per request.
        """
        if not BATCH_PRICE_FETCH or not mints:
            return {}

        session = await self._get_session()
        prices = {}

        # Jupiter Price API v3 (requires API key, up to 50 tokens per request)
        if JUPITER_API_KEY:
            try:
                mint_ids = ",".join(mints[:50])  # Max 50 tokens
                url = f"{JUPITER_PRICE_API}?ids={mint_ids}"
                headers = {"x-api-key": JUPITER_API_KEY}
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for mint in mints:
                            price_data = data.get(mint, {})
                            price = price_data.get("usdPrice")
                            if price:
                                prices[mint] = float(price)
                        if prices:
                            logger.debug(f"[BATCH] Fetched {len(prices)}/{len(mints)} prices from Jupiter v3")
                            return prices
            except Exception as e:
                logger.debug(f"[BATCH] Jupiter v3 batch failed: {e}")

        # Fallback: Birdeye batch (if available)
        try:
            from core.config import BIRDEYE_API_KEY, BIRDEYE_API
            if BIRDEYE_API_KEY:
                headers = {"X-API-KEY": BIRDEYE_API_KEY}
                # Birdeye multi-price endpoint (check their docs for exact format)
                # This is a placeholder — adjust based on actual Birdeye API
                for mint in mints:
                    url = f"{BIRDEYE_API}/defi/price?address={mint}"
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            price = data.get("data", {}).get("value", 0)
                            if price and float(price) > 0:
                                prices[mint] = float(price)
        except Exception as e:
            logger.debug(f"[BATCH] Birdeye batch failed: {e}")

        return prices

    # ------------------------------------------------------------------
    # WebSocket real-time price streaming (premium RPC required)
    # ------------------------------------------------------------------
    async def _subscribe_price_ws(self, mint: str):
        """
        Subscribe to real-time price updates via WebSocket.
        Monitors the token's liquidity pool account for instant price changes.
        """
        if not self._ws_enabled:
            return

        try:
            import websockets
            import json

            logger.info(f"[WS] Connecting to WebSocket for {mint[:12]}...")
            
            # Connect to Helius WebSocket
            async with websockets.connect(HELIUS_WSS_URL) as ws:
                self._ws_connections[mint] = ws
                
                # For Solana tokens, we need to subscribe to the token account or pool
                # This is a working implementation using accountSubscribe
                subscribe_msg = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "accountSubscribe",
                    "params": [
                        mint,  # Subscribe to the token mint account
                        {
                            "encoding": "jsonParsed",
                            "commitment": "confirmed"
                        }
                    ]
                }
                await ws.send(json.dumps(subscribe_msg))
                logger.info(f"[WS] Subscribed to {mint[:12]}")
                
                # Listen for updates
                while mint in self.open_positions:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=30)
                        data = json.loads(msg)
                        
                        # Handle subscription confirmation
                        if "result" in data and isinstance(data["result"], int):
                            logger.debug(f"[WS] Subscription confirmed for {mint[:12]}, ID: {data['result']}")
                            continue
                        
                        # Handle account updates
                        if "params" in data and "result" in data["params"]:
                            # For real-time price, we'd need to:
                            # 1. Get the pool account (Raydium/Orca)
                            # 2. Parse reserve amounts
                            # 3. Calculate price from reserves
                            
                            # For now, trigger a price fetch when we get an update
                            # This is still faster than polling because we only fetch when something changes
                            price = await self._get_current_price(mint)
                            if price and price > 0:
                                self._ws_prices[mint] = price
                                pos = self.open_positions.get(mint)
                                if pos:
                                    pos.current_price = price
                                    pos.last_price_update = time.time()
                                logger.debug(f"[WS] Price update for {mint[:12]}: ${price:.8f}")
                            
                    except asyncio.TimeoutError:
                        # Send ping to keep connection alive
                        ping_msg = {"jsonrpc": "2.0", "method": "ping"}
                        await ws.send(json.dumps(ping_msg))
                    except Exception as e:
                        logger.warning(f"[WS] Error processing message for {mint[:12]}: {e}")
                        break
                        
        except Exception as e:
            logger.warning(f"[WS] WebSocket connection failed for {mint[:12]}: {e}")
            logger.info(f"[WS] Falling back to polling for {mint[:12]}")
        finally:
            # Clean up
            self._ws_connections.pop(mint, None)
            self._ws_prices.pop(mint, None)

    async def _get_ws_price(self, mint: str) -> Optional[float]:
        """
        Get latest price from WebSocket feed if available.
        Returns None if WebSocket not connected or no recent update.
        """
        if not self._ws_enabled:
            return None
        
        # Start WebSocket subscription if not already running
        if mint not in self._ws_connections and mint in self.open_positions:
            # Start WebSocket in background
            asyncio.create_task(self._subscribe_price_ws(mint))
            # Give it a moment to connect
            await asyncio.sleep(0.1)
        
        return self._ws_prices.get(mint)

    async def close(self):
        # Close all WebSocket connections
        for mint, ws in self._ws_connections.items():
            try:
                await ws.close()
            except Exception:
                pass
        self._ws_connections.clear()
        
        # Close HTTP session
        if self._session and not self._session.closed:
            await self._session.close()
