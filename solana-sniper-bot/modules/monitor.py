"""
monitor.py — Real-time monitor for new Solana token launches and momentum plays.

Sources (priority order):
  1. Pump.fun WebSocket     — new launches, real-time (best for 10x new coins)
  2. Pump.fun graduations   — tokens graduating to Raydium (high conviction)
  3. Raydium WebSocket      — new AMM pools via Helius
  4. Dexscreener new pairs  — tokens listed in last 24h with momentum
  5. Dexscreener trending   — boosted/profiled tokens
  6. Dexscreener search     — high volume $10k-$5M MC movers
  7. Birdeye trending       — cross-validates with Dexscreener

Runs 24/7, reconnects on drop, feeds asyncio.Queue for analysis.
"""
import asyncio
import json
import logging
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosedError, WebSocketException

from core.config import (
    HELIUS_WSS_URL, FALLBACK_WSS_URL,
    PUMP_FUN_PROGRAM, RAYDIUM_AMM_PROGRAM,
    BIRDEYE_API_KEY,
)

logger = logging.getLogger(__name__)

PUMPPORTAL_WSS = "wss://pumpportal.fun/api/data"


class LaunchMonitor:
    """
    Dual-source monitor: Pump.fun + Raydium via Helius.
    Pushes raw token leads to analysis_queue.
    """

    def __init__(self, analysis_queue: asyncio.Queue):
        self.queue = analysis_queue
        self._running = True

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    async def start(self):
        """Launch all listeners concurrently."""
        logger.info("[MONITOR] Starting all sources...")
        logger.info("[MONITOR] Active sources:")
        logger.info("[MONITOR]   1. Pump.fun WebSocket     — new launches + graduations (real-time)")
        logger.info("[MONITOR]   2. Raydium WebSocket      — new AMM pools via Helius")
        logger.info("[MONITOR]   3. Dexscreener new pairs  — tokens <6h old with momentum (every 45s)")
        logger.info("[MONITOR]   4. Dexscreener trending   — boosted/profiled tokens (every 60s)")
        logger.info("[MONITOR]   5. Dexscreener search     — $10k-$5M MC movers >20%/1h (every 60s)")
        logger.info(f"[MONITOR]   6. Birdeye trending      — volume surge tokens ({'ACTIVE' if BIRDEYE_API_KEY else 'SKIPPED — no API key'})")
        await asyncio.gather(
            self._pump_fun_listener(),
            self._raydium_listener(),
            self._established_coin_scanner(),
            self._birdeye_trending_scanner(),
            self._dexscreener_new_pairs_scanner(),
        )

    # ------------------------------------------------------------------
    # 1. Pump.fun listener (pumpportal.fun free WebSocket)
    # ------------------------------------------------------------------
    async def _pump_fun_listener(self):
        while self._running:
            try:
                async with websockets.connect(
                    PUMPPORTAL_WSS,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    logger.info("[MONITOR] Connected to Pump.fun WebSocket")

                    # Subscribe to new token launches
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    # Subscribe to all token trades (for momentum tracking)
                    await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": []}))

                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                            await self._handle_pump_event(data)
                        except json.JSONDecodeError:
                            continue

            except (ConnectionClosedError, WebSocketException, OSError) as e:
                logger.warning(f"[MONITOR] Pump.fun WS dropped ({e}). Reconnecting in 3s...")
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"[MONITOR] Unexpected Pump.fun error: {e}")
                await asyncio.sleep(5)

    async def _handle_pump_event(self, data: dict):
        """Parse pump.fun event and push to queue."""
        # New token launch event
        if data.get("txType") == "create":
            token_lead = {
                "source": "pump_fun",
                "type": "new_launch",
                "mint": data.get("mint", ""),
                "name": data.get("name", ""),
                "symbol": data.get("symbol", ""),
                "creator": data.get("traderPublicKey", ""),
                "bonding_curve": data.get("bondingCurveKey", ""),
                "initial_buy": data.get("initialBuy", 0),
                "market_cap_sol": data.get("marketCapSol", 0),
                "uri": data.get("uri", ""),
                "signature": data.get("signature", ""),
                "timestamp": data.get("timestamp", 0),
            }
            if token_lead["mint"]:
                logger.debug(f"[MONITOR] New Pump.fun launch: {token_lead['symbol']} ({token_lead['mint'][:8]}...)")
                await self.queue.put(token_lead)

        # Trade event — used for momentum signals
        elif data.get("txType") in ("buy", "sell"):
            trade_lead = {
                "source": "pump_fun",
                "type": "trade",
                "mint": data.get("mint", ""),
                "tx_type": data.get("txType"),
                "sol_amount": data.get("solAmount", 0),
                "market_cap_sol": data.get("marketCapSol", 0),
                "signature": data.get("signature", ""),
            }
            if trade_lead["mint"]:
                await self.queue.put(trade_lead)

        # Graduation event — token completed bonding curve, now on Raydium
        # These are high-conviction: survived the bonding curve gauntlet
        elif data.get("txType") == "complete":
            mint = data.get("mint", "")
            if mint:
                grad_lead = {
                    "source": "pump_fun_graduation",
                    "type": "established",   # treat as established — already proven demand
                    "mint": mint,
                    "symbol": data.get("symbol", "?"),
                    "name": data.get("name", "?"),
                    "creator": data.get("traderPublicKey", ""),
                    "graduated": True,
                }
                logger.info(f"[MONITOR] 🎓 Pump.fun graduation: {data.get('symbol', '?')} ({mint[:8]}...)")
                await self.queue.put(grad_lead)

    # ------------------------------------------------------------------
    # 2. Raydium new pool listener (Helius logsSubscribe)
    # ------------------------------------------------------------------
    async def _raydium_listener(self):
        wss_urls = [HELIUS_WSS_URL, FALLBACK_WSS_URL]
        url_index = 0

        while self._running:
            wss = wss_urls[url_index % len(wss_urls)]
            try:
                async with websockets.connect(
                    wss,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    logger.info(f"[MONITOR] Connected to Raydium monitor via {wss[:40]}...")

                    subscribe_msg = {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "logsSubscribe",
                        "params": [
                            {"mentions": [RAYDIUM_AMM_PROGRAM]},
                            {"commitment": "processed"},
                        ],
                    }
                    await ws.send(json.dumps(subscribe_msg))

                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                            await self._handle_raydium_event(data)
                        except json.JSONDecodeError:
                            continue

            except (ConnectionClosedError, WebSocketException, OSError) as e:
                logger.warning(f"[MONITOR] Raydium WS dropped ({e}). Trying next RPC...")
                url_index += 1
                await asyncio.sleep(3)
            except Exception as e:
                logger.error(f"[MONITOR] Unexpected Raydium error: {e}")
                await asyncio.sleep(5)

    async def _handle_raydium_event(self, data: dict):
        """Parse Helius log subscription for Raydium pool init."""
        if "params" not in data:
            return
        try:
            result = data["params"]["result"]["value"]
            logs: list = result.get("logs", [])
            signature: str = result.get("signature", "")

            # Detect pool initialization log
            is_new_pool = any(
                "initialize2" in log or "InitializeInstruction2" in log
                for log in logs
            )
            if is_new_pool:
                token_lead = {
                    "source": "raydium",
                    "type": "new_pool",
                    "signature": signature,
                    "mint": "",   # resolved in analysis via tx lookup
                    "logs": logs[:5],  # keep first 5 for parsing
                }
                logger.debug(f"[MONITOR] New Raydium pool detected: {signature[:12]}...")
                await self.queue.put(token_lead)
        except (KeyError, TypeError):
            pass

    # ------------------------------------------------------------------
    # 3. Established coin scanner (Dexscreener — free, no key)
    #    Scans for coins $10k–$5M MC with strong momentum every 60s
    # ------------------------------------------------------------------
    async def _established_coin_scanner(self):
        """
        Polls Dexscreener for Solana tokens with:
        - Market cap $10k–$5M
        - Strong volume / price momentum
        - Pushes as 'established' leads for 1:3 RR analysis
        Runs every 60 seconds.
        """
        logger.info("[MONITOR] Established coin scanner starting...")
        # Dexscreener trending + boosted endpoints (free)
        SCAN_URLS = [
            "https://api.dexscreener.com/token-boosts/top/v1",
            "https://api.dexscreener.com/token-profiles/latest/v1",
        ]
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10)
        ) as session:
            while self._running:
                for url in SCAN_URLS:
                    try:
                        async with session.get(url) as resp:
                            if resp.status != 200:
                                continue
                            items = await resp.json()
                            if not isinstance(items, list):
                                continue
                            for item in items:
                                # Only Solana tokens
                                if item.get("chainId") != "solana":
                                    continue
                                mint = item.get("tokenAddress", "")
                                if not mint or len(mint) < 32:
                                    continue
                                lead = {
                                    "source": "dexscreener_scan",
                                    "type": "established",
                                    "mint": mint,
                                    "symbol": item.get("symbol", "?"),
                                    "name": item.get("description", "?"),
                                    "creator": "",
                                    "url": item.get("url", ""),
                                }
                                await self.queue.put(lead)
                                await asyncio.sleep(0.5)  # throttle RugCheck
                    except Exception as e:
                        logger.debug(f"[MONITOR] Established scanner error: {e}")

                # Also scan Dexscreener search for high-volume Solana pairs
                try:
                    url = "https://api.dexscreener.com/latest/dex/search?q=solana"
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            pairs = data.get("pairs", [])
                            for pair in pairs:
                                if pair.get("chainId") != "solana":
                                    continue
                                fdv = float(pair.get("fdv", 0) or 0)
                                vol_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
                                price_change_1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)
                                # Filter: $10k–$5M MC, >$50k 24h volume, >20% 1h move
                                if not (10_000 <= fdv <= 5_000_000):
                                    continue
                                if vol_24h < 50_000:
                                    continue
                                if price_change_1h < 20:
                                    continue
                                mint = pair.get("baseToken", {}).get("address", "")
                                if not mint or len(mint) < 32:
                                    continue
                                lead = {
                                    "source": "dexscreener_scan",
                                    "type": "established",
                                    "mint": mint,
                                    "symbol": pair.get("baseToken", {}).get("symbol", "?"),
                                    "name": pair.get("baseToken", {}).get("name", "?"),
                                    "creator": "",
                                    "market_cap_usd": fdv,
                                    "volume_24h": vol_24h,
                                    "price_change_1h": price_change_1h,
                                }
                                await self.queue.put(lead)
                                await asyncio.sleep(0.5)  # throttle RugCheck
                                logger.debug(
                                    f"[MONITOR] Established coin: {lead['symbol']} "
                                    f"MC=${fdv:,.0f} vol=${vol_24h:,.0f} +{price_change_1h:.0f}%/1h"
                                )
                except Exception as e:
                    logger.debug(f"[MONITOR] Dexscreener search error: {e}")

                await asyncio.sleep(60)  # scan every 60 seconds

    # ------------------------------------------------------------------
    # 4. Dexscreener new pairs scanner (tokens listed in last 24h)
    #    Catches coins right as they list — before they trend
    # ------------------------------------------------------------------
    async def _dexscreener_new_pairs_scanner(self):
        """Polls Dexscreener for brand-new Solana pairs with early momentum."""
        logger.info("[MONITOR] Dexscreener new pairs scanner starting...")
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            while self._running:
                try:
                    url = "https://api.dexscreener.com/latest/dex/pairs/solana"
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            await asyncio.sleep(30)
                            continue
                        data = await resp.json()
                        pairs = data.get("pairs", [])
                        for pair in pairs:
                            age_hours = pair.get("pairAge", 9999) / 3600 if pair.get("pairAge") else 9999
                            # Only pairs created in last 6 hours
                            if age_hours > 6:
                                continue
                            fdv = float(pair.get("fdv", 0) or 0)
                            vol_5m = float(pair.get("volume", {}).get("m5", 0) or 0)
                            price_change_5m = float(pair.get("priceChange", {}).get("m5", 0) or 0)
                            # Filter: some MC, active volume, positive momentum
                            if fdv < 5_000 or fdv > 10_000_000:
                                continue
                            if vol_5m < 1_000:
                                continue
                            if price_change_5m < 5:
                                continue
                            mint = pair.get("baseToken", {}).get("address", "")
                            if not mint or len(mint) < 32:
                                continue
                            is_new = fdv < 100_000
                            lead = {
                                "source": "dexscreener_new_pairs",
                                "type": "new_launch" if is_new else "established",
                                "mint": mint,
                                "symbol": pair.get("baseToken", {}).get("symbol", "?"),
                                "name": pair.get("baseToken", {}).get("name", "?"),
                                "creator": "",
                                "market_cap_usd": fdv,
                                "age_hours": age_hours,
                            }
                            await self.queue.put(lead)
                            await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug(f"[MONITOR] Dexscreener new pairs error: {e}")
                await asyncio.sleep(45)

    # ------------------------------------------------------------------
    # 5. Birdeye trending scanner (requires API key, falls back gracefully)
    #    Often catches momentum plays before Dexscreener
    # ------------------------------------------------------------------
    async def _birdeye_trending_scanner(self):
        """Polls Birdeye trending tokens — best early momentum signal."""
        if not BIRDEYE_API_KEY:
            logger.info("[MONITOR] Birdeye API key not set — skipping Birdeye scanner")
            return
        logger.info("[MONITOR] Birdeye trending scanner starting...")
        headers = {"X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            while self._running:
                try:
                    # Birdeye trending tokens (sorted by 1h volume change)
                    url = "https://public-api.birdeye.so/defi/tokenlist?sort_by=v24hChangePercent&sort_type=desc&offset=0&limit=50&min_liquidity=5000"
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            await asyncio.sleep(60)
                            continue
                        data = await resp.json()
                        tokens = data.get("data", {}).get("tokens", [])
                        for token in tokens:
                            mc = float(token.get("mc", 0) or 0)
                            v24h_change = float(token.get("v24hChangePercent", 0) or 0)
                            price_change_1h = float(token.get("priceChange1hPercent", 0) or 0)
                            # Filter: reasonable MC, strong volume surge, positive price
                            if mc < 10_000 or mc > 10_000_000:
                                continue
                            if v24h_change < 50:   # volume up 50%+ in 24h
                                continue
                            if price_change_1h < 5:
                                continue
                            mint = token.get("address", "")
                            if not mint or len(mint) < 32:
                                continue
                            is_new = mc < 100_000
                            lead = {
                                "source": "birdeye_trending",
                                "type": "new_launch" if is_new else "established",
                                "mint": mint,
                                "symbol": token.get("symbol", "?"),
                                "name": token.get("name", "?"),
                                "creator": "",
                                "market_cap_usd": mc,
                                "v24h_change_pct": v24h_change,
                            }
                            await self.queue.put(lead)
                            await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug(f"[MONITOR] Birdeye trending error: {e}")
                await asyncio.sleep(60)

    def stop(self):
        self._running = False
