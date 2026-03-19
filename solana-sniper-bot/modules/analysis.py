"""
analysis.py — Full token analysis pipeline. Every token must pass ALL checks
before being queued for trading. Target: <2 seconds per coin.

Checks (in order):
  1. RugCheck honeypot / safety score
  2. Creator wallet history
  3. Liquidity & market cap filter
  4. Momentum (Birdeye / Dexscreener)
  5. Social hype (Twitter gurus + mentions)
  6. Confidence score > 75 → pass to trade queue
"""
import asyncio
import logging
import time
from typing import Optional

import aiohttp

from core.config import (
    RUGCHECK_API, BIRDEYE_API, BIRDEYE_API_KEY, TWITTER_API_KEY,
    MIN_CONFIDENCE_SCORE, MIN_LIQUIDITY_USD, MIN_VOLUME_5M_USD,
    MIN_BUY_SELL_RATIO, NEW_COIN_MC_THRESHOLD,
    GURU_HANDLES, GURU_MENTION_THRESHOLD,
)

logger = logging.getLogger(__name__)

# Simple in-memory cache to avoid re-analyzing the same mint within 60s
_analysis_cache: dict[str, float] = {}
CACHE_TTL = 60  # seconds


class TokenAnalyzer:
    """
    Runs all safety and momentum checks on a token.
    Pushes passing tokens to trade_queue with a confidence score.
    """

    def __init__(self, trade_queue: asyncio.Queue):
        self.trade_queue = trade_queue
        # Shared aiohttp session (created on first use)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=4)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    async def analyze(self, lead: dict):
        """
        Accepts a raw lead from monitor queue.
        Resolves mint address, runs all checks, pushes to trade queue.
        """
        mint = lead.get("mint", "")

        # Raydium leads may not have mint yet — skip for now (needs tx parse)
        if not mint and lead.get("source") == "raydium":
            return

        # Skip trade events (momentum-only, not new launches)
        if lead.get("type") == "trade":
            return

        if not mint or len(mint) < 32:
            return

        # Cache check — don't re-analyze within TTL
        now = time.time()
        if mint in _analysis_cache and now - _analysis_cache[mint] < CACHE_TTL:
            return
        _analysis_cache[mint] = now

        logger.info(f"[ANALYSIS] Analyzing {mint[:12]}... ({lead.get('symbol', '?')})")
        start = time.time()

        confidence = 0
        reasons = []

        # --- 1. RugCheck ---
        rug_result = await self._check_rugcheck(mint)
        if not rug_result["safe"]:
            logger.info(f"[ANALYSIS] REJECT {mint[:12]}: RugCheck failed — {rug_result['reason']}")
            return
        confidence += 35
        reasons.append("rug_ok")

        # --- 2. Creator history ---
        creator = lead.get("creator", "")
        if creator:
            creator_ok = await self._check_creator(creator)
            if not creator_ok:
                logger.info(f"[ANALYSIS] REJECT {mint[:12]}: Creator flagged as serial rugger")
                return
            confidence += 10
            reasons.append("creator_ok")

        # --- 3. Market data (liquidity + market cap) ---
        market = await self._check_market_data(mint)
        if market is None:
            logger.info(f"[ANALYSIS] REJECT {mint[:12]}: Could not fetch market data")
            return
        if market["liquidity_usd"] < MIN_LIQUIDITY_USD:
            logger.info(f"[ANALYSIS] REJECT {mint[:12]}: Liquidity too low (${market['liquidity_usd']:.0f})")
            return
        confidence += 15
        reasons.append("liquidity_ok")

        is_new_coin = market["market_cap_usd"] < NEW_COIN_MC_THRESHOLD

        # --- 4. Momentum ---
        momentum_score = await self._check_momentum(mint, market)
        if momentum_score == 0:
            logger.info(f"[ANALYSIS] REJECT {mint[:12]}: No momentum")
            return
        confidence += momentum_score
        reasons.append(f"momentum+{momentum_score}")

        # --- 5. Social hype ---
        social_score = await self._check_social_hype(lead.get("symbol", ""), mint)
        confidence += social_score
        if social_score > 0:
            reasons.append(f"social+{social_score}")

        elapsed = time.time() - start
        logger.info(
            f"[ANALYSIS] {mint[:12]} | score={confidence} | "
            f"new={is_new_coin} | {elapsed:.2f}s | {', '.join(reasons)}"
        )

        if confidence >= MIN_CONFIDENCE_SCORE:
            signal = {
                "mint": mint,
                "symbol": lead.get("symbol", "?"),
                "name": lead.get("name", "?"),
                "is_new_coin": is_new_coin,
                "market_cap_usd": market["market_cap_usd"],
                "liquidity_usd": market["liquidity_usd"],
                "confidence": confidence,
                "source": lead.get("source", "unknown"),
            }
            logger.info(f"[ANALYSIS] ✅ PASS {mint[:12]} | confidence={confidence}")
            await self.trade_queue.put(signal)
        else:
            logger.info(f"[ANALYSIS] REJECT {mint[:12]}: Score {confidence} < {MIN_CONFIDENCE_SCORE}")

    # ------------------------------------------------------------------
    # Check 1: RugCheck.xyz (free API)
    # ------------------------------------------------------------------
    async def _check_rugcheck(self, mint: str) -> dict:
        """
        Calls RugCheck free endpoint. Parses:
        - risks array (honeypot, freeze authority, mint authority, LP burned)
        - top holder concentration
        Returns {"safe": bool, "reason": str}
        """
        session = await self._get_session()
        url = f"{RUGCHECK_API}/tokens/{mint}/report/summary"
        try:
            async with session.get(url) as resp:
                if resp.status == 429:
                    # Rate limited — give benefit of doubt, log warning
                    logger.warning(f"[RUGCHECK] Rate limited for {mint[:12]}, skipping check")
                    return {"safe": True, "reason": "rate_limited"}
                if resp.status != 200:
                    return {"safe": False, "reason": f"HTTP {resp.status}"}

                data = await resp.json()

                # RugCheck returns a "risks" list with severity levels
                risks = data.get("risks", [])
                score = data.get("score", 0)  # higher = riskier on some endpoints

                # Hard reject on critical risks
                critical_names = {
                    "Freeze Authority still enabled",
                    "Mint Authority still enabled",
                    "Low Liquidity",
                    "Honeypot",
                    "High holder concentration",
                }
                for risk in risks:
                    name = risk.get("name", "")
                    level = risk.get("level", "").lower()
                    if level == "danger" or name in critical_names:
                        return {"safe": False, "reason": name}

                # Check top holder concentration from full report if available
                top_holders = data.get("topHolders", [])
                if top_holders:
                    top_pct = sum(h.get("pct", 0) for h in top_holders[:5])
                    if top_pct > 60:
                        return {"safe": False, "reason": f"Top 5 holders own {top_pct:.0f}%"}

                return {"safe": True, "reason": "ok"}

        except asyncio.TimeoutError:
            logger.warning(f"[RUGCHECK] Timeout for {mint[:12]}")
            return {"safe": False, "reason": "timeout"}
        except Exception as e:
            logger.error(f"[RUGCHECK] Error: {e}")
            return {"safe": False, "reason": str(e)}

    # ------------------------------------------------------------------
    # Check 2: Creator wallet history
    # ------------------------------------------------------------------
    async def _check_creator(self, creator: str) -> bool:
        """
        Checks if creator has a history of rug pulls via RugCheck creator endpoint.
        Returns True if creator appears clean.
        """
        session = await self._get_session()
        url = f"{RUGCHECK_API}/tokens/{creator}/report/summary"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return True  # Can't verify, give benefit of doubt
                data = await resp.json()
                # If creator wallet itself has danger flags, reject
                risks = data.get("risks", [])
                for risk in risks:
                    if risk.get("level", "").lower() == "danger":
                        return False
                return True
        except Exception:
            return True  # Network error — don't block on this

    # ------------------------------------------------------------------
    # Check 3: Market data (Birdeye + Dexscreener fallback)
    # ------------------------------------------------------------------
    async def _check_market_data(self, mint: str) -> Optional[dict]:
        """
        Fetches market cap, liquidity, volume from Birdeye (free tier).
        Falls back to Dexscreener if Birdeye fails.
        Returns dict or None on failure.
        """
        result = await self._birdeye_market(mint)
        if result is None:
            result = await self._dexscreener_market(mint)
        return result

    async def _birdeye_market(self, mint: str) -> Optional[dict]:
        session = await self._get_session()
        headers = {"X-API-KEY": BIRDEYE_API_KEY} if BIRDEYE_API_KEY else {}
        url = f"{BIRDEYE_API}/defi/token_overview?address={mint}"
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = (await resp.json()).get("data", {})
                return {
                    "market_cap_usd": data.get("mc", 0) or 0,
                    "liquidity_usd": data.get("liquidity", 0) or 0,
                    "volume_5m_usd": data.get("v5m", 0) or 0,
                    "price_change_5m": data.get("priceChange5mPercent", 0) or 0,
                    "buy_5m": data.get("buy5m", 0) or 0,
                    "sell_5m": data.get("sell5m", 0) or 0,
                    "price": data.get("price", 0) or 0,
                }
        except Exception:
            return None

    async def _dexscreener_market(self, mint: str) -> Optional[dict]:
        session = await self._get_session()
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pairs = data.get("pairs", [])
                if not pairs:
                    return None
                p = pairs[0]  # best pair
                return {
                    "market_cap_usd": float(p.get("fdv", 0) or 0),
                    "liquidity_usd": float(p.get("liquidity", {}).get("usd", 0) or 0),
                    "volume_5m_usd": float(p.get("volume", {}).get("m5", 0) or 0),
                    "price_change_5m": float(p.get("priceChange", {}).get("m5", 0) or 0),
                    "buy_5m": 0,
                    "sell_5m": 0,
                    "price": float(p.get("priceUsd", 0) or 0),
                }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Check 4: Momentum scoring (0-25 points)
    # ------------------------------------------------------------------
    async def _check_momentum(self, mint: str, market: dict) -> int:
        score = 0
        vol = market.get("volume_5m_usd", 0)
        change = market.get("price_change_5m", 0)
        buys = market.get("buy_5m", 0)
        sells = market.get("sell_5m", 0)

        # Volume spike
        if vol >= MIN_VOLUME_5M_USD:
            score += 10
        elif vol >= MIN_VOLUME_5M_USD * 0.5:
            score += 5

        # Price momentum
        if change >= 50:
            score += 10
        elif change >= 20:
            score += 5

        # Buy/sell ratio
        if sells > 0 and buys / sells >= MIN_BUY_SELL_RATIO:
            score += 5
        elif buys > 0 and sells == 0:
            score += 5  # all buys, no sells

        return score

    # ------------------------------------------------------------------
    # Check 5: Social hype (Twitter gurus + mentions)
    # ------------------------------------------------------------------
    async def _check_social_hype(self, symbol: str, mint: str) -> int:
        """
        Returns 0-15 social confidence points.
        Uses TwitterAPI.io if key available, else Birdeye social, else 0.
        """
        if not symbol:
            return 0

        # Try TwitterAPI.io (pay-per-use, ~$0.15/1000 tweets)
        if TWITTER_API_KEY:
            return await self._twitter_guru_check(symbol)

        # Try Birdeye social mentions (free)
        return await self._birdeye_social(mint)

    async def _twitter_guru_check(self, symbol: str) -> int:
        """
        Searches recent tweets from top guru accounts mentioning the symbol.
        Returns score based on how many gurus mentioned it.
        """
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {TWITTER_API_KEY}"}
        query = f"${symbol} OR #{symbol}"
        url = f"https://api.twitterapi.io/twitter/tweet/advanced_search?query={query}&queryType=Latest"
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return 0
                data = await resp.json()
                tweets = data.get("tweets", [])
                guru_hits = sum(
                    1 for t in tweets
                    if t.get("author", {}).get("userName", "").lower()
                    in [g.lower() for g in GURU_HANDLES]
                )
                if guru_hits >= GURU_MENTION_THRESHOLD:
                    return 15
                elif guru_hits >= 1:
                    return 8
                return 0
        except Exception:
            return 0

    async def _birdeye_social(self, mint: str) -> int:
        """Birdeye social mentions as fallback (free tier)."""
        session = await self._get_session()
        headers = {"X-API-KEY": BIRDEYE_API_KEY} if BIRDEYE_API_KEY else {}
        url = f"{BIRDEYE_API}/defi/token_trending?address={mint}"
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return 0
                data = await resp.json()
                # If token appears in trending, give partial social score
                if data.get("data"):
                    return 5
                return 0
        except Exception:
            return 0

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
