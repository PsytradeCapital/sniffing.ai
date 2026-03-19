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
        """Launch both listeners concurrently."""
        logger.info("[MONITOR] Starting dual-source monitor...")
        await asyncio.gather(
            self._pump_fun_listener(),
            self._raydium_listener(),
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

    def stop(self):
        self._running = False
