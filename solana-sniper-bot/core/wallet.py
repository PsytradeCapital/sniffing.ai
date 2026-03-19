"""
wallet.py — Secure keypair loading, balance queries, SOL/USD conversion.
Never hardcodes secrets. Reads only from .env via config.
"""
import logging
import base58
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from core.config import (
    PRIVATE_KEY_BASE58, HELIUS_RPC_URL, FALLBACK_RPC_URL, NETWORK
)

logger = logging.getLogger(__name__)

# Approximate SOL price fallback (updated at runtime via get_sol_price)
_SOL_PRICE_USD: float = 200.0


class WalletManager:
    """Manages the bot's hot wallet: load, balance, conversion."""

    def __init__(self):
        if not PRIVATE_KEY_BASE58:
            raise ValueError(
                "PRIVATE_KEY_BASE58 not set in .env! "
                "Run: python -c \"from solders.keypair import Keypair; k=Keypair(); "
                "import base58; print(base58.b58encode(bytes(k)).decode())\" "
                "to generate a fresh keypair."
            )

        try:
            secret_bytes = base58.b58decode(PRIVATE_KEY_BASE58)
            self.keypair = Keypair.from_bytes(secret_bytes)
        except Exception as e:
            raise ValueError(f"Invalid PRIVATE_KEY_BASE58 in .env: {e}")

        self.pubkey: Pubkey = self.keypair.pubkey()
        self._rpc_url = HELIUS_RPC_URL
        # commitment="confirmed" skips the /health preflight that Helius returns 404 on
        self.client = AsyncClient(self._rpc_url, commitment="confirmed")
        logger.info(f"Wallet loaded: {self.pubkey} | Network: {NETWORK}")

    async def _ensure_client(self):
        """Switch to fallback RPC if primary is unreachable."""
        try:
            await self.client.is_connected()
        except Exception:
            logger.warning("Primary RPC unreachable, switching to fallback...")
            await self.client.close()
            self._rpc_url = FALLBACK_RPC_URL
            self.client = AsyncClient(FALLBACK_RPC_URL, commitment="confirmed")

    async def get_sol_balance(self) -> float:
        """Returns SOL balance as a float."""
        await self._ensure_client()
        try:
            response = await self.client.get_balance(self.pubkey)
            return response.value / 1_000_000_000
        except Exception as e:
            logger.error(f"Failed to fetch SOL balance: {e}")
            return 0.0

    async def get_sol_price_usd(self) -> float:
        """Fetches live SOL/USD price. Tries multiple free sources with fallback."""
        import aiohttp
        global _SOL_PRICE_USD
        sources = [
            # Binance (no key, very reliable)
            ("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", "binance"),
            # CoinGecko free (no key)
            ("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", "coingecko"),
        ]
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            for url, source in sources:
                try:
                    async with session.get(url) as r:
                        if r.status != 200:
                            continue
                        data = await r.json()
                        if source == "binance":
                            _SOL_PRICE_USD = float(data["price"])
                        elif source == "coingecko":
                            _SOL_PRICE_USD = float(data["solana"]["usd"])
                        return _SOL_PRICE_USD
                except Exception:
                    continue
        logger.warning(f"All price sources failed, using cached ${_SOL_PRICE_USD}")
        return _SOL_PRICE_USD

    async def get_balance_usd(self) -> float:
        sol = await self.get_sol_balance()
        price = await self.get_sol_price_usd()
        return sol * price

    def sol_to_lamports(self, sol: float) -> int:
        return int(sol * 1_000_000_000)

    def lamports_to_sol(self, lamports: int) -> float:
        return lamports / 1_000_000_000

    async def close(self):
        await self.client.close()
