"""
monitor.py — Real-time WebSocket monitor for:
  1. Pump.fun new token launches (pumpportal.fun API)
  2. Raydium new AMM pool creation (Helius logsSubscribe)

Runs 24/7, reconnects on drop, feeds asyncio.Queue for analysis.
Handles 100+ launches/min without blocking.
"""
import asyncio
import json
import logging
import aiohttp
import websockets
from websockets.exceptions import ConnectionClosedError, WebSocketException

from core.config import (
    HELIUS_WSS_URL, FALLBACK_WSS_URL,
    PUMP_FUN_PROGRAM, RAYDIUM_AMM_PROGRAM
)

logger = logging.getLogger(__name__)

# Pump.fun public WebSocket (free, no key needed)
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
        logger.info("[MONITOR] Starting dual-source monitor...")
        await asyncio.gather(
            self._pump_fun_listener(),
            self._raydium_listener(),
            self._established_coin_scanner(),
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
                                logger.debug(
                                    f"[MONITOR] Established coin: {lead['symbol']} "
                                    f"MC=${fdv:,.0f} vol=${vol_24h:,.0f} +{price_change_1h:.0f}%/1h"
                                )
                except Exception as e:
                    logger.debug(f"[MONITOR] Dexscreener search error: {e}")

                await asyncio.sleep(60)  # scan every 60 seconds

    def stop(self):
        self._running = False
