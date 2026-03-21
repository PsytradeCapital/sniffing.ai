# URGENT: Jupiter API Update Required

## What Changed

Jupiter updated their API structure in 2024 and deprecated the old endpoints:

### Old (DEPRECATED)
- ❌ `quote-api.jup.ag/v6` — Swap/Quote API
- ❌ `price.jup.ag/v4` — Price API

### New (CURRENT)
- ✅ `api.jup.ag/swap/v2` — Unified Swap API (requires API key)
- ✅ `api.jup.ag/price/v3` — Price API (requires API key)
- ✅ `lite-api.jup.ag/swap/v1` — Free tier (will be deprecated Jan 2026)

## Action Required

### 1. Get a Free Jupiter API Key

Visit [https://portal.jup.ag](https://portal.jup.ag) and create a free account to get your API key.

### 2. Update Your `.env` File

Add these lines to your `.env`:

```bash
# Jupiter API Configuration
JUPITER_API_URL=https://lite-api.jup.ag/swap/v1
JUPITER_PRICE_API_URL=https://api.jup.ag/price/v3
JUPITER_API_KEY=your_api_key_here  # Get from portal.jup.ag
```

### 3. Test the Update

```bash
python main.py
```

Watch for these log messages:
- `[BATCH] Fetched X/Y prices from Jupiter v3` — Price API working
- No HTTP 401 or 404 errors from Jupiter

## What We Updated

### Files Modified
1. `core/config.py` — Added new API endpoints and API key config
2. `modules/trade_executor.py` — Updated price fetching to use v3 API
3. `.env.example` — Documented new configuration

### API Changes

#### Price API (v4 → v3)

**Old:**
```python
url = f"https://price.jup.ag/v4/price?ids={mint}"
response = {"data": {mint: {"price": 123.45}}}
```

**New:**
```python
url = f"https://api.jup.ag/price/v3?ids={mint}"
headers = {"x-api-key": JUPITER_API_KEY}
response = {mint: {"usdPrice": 123.45, "liquidity": 1000000, ...}}
```

#### Swap API (v6 → v1/v2)

**Old:**
```python
url = "https://quote-api.jup.ag/v6/quote"
```

**New (Free Tier):**
```python
url = "https://lite-api.jup.ag/swap/v1/quote"
```

**New (Production):**
```python
url = "https://api.jup.ag/swap/v2/order"
headers = {"x-api-key": JUPITER_API_KEY}
```

## Fallback Strategy

The bot now uses a 3-tier fallback for price fetching:

1. **Jupiter Price API v3** (primary, requires API key)
2. **Birdeye API** (fallback, free tier)
3. **Dexscreener API** (last resort, free)

If you don't have a Jupiter API key, the bot will automatically fall back to Birdeye and Dexscreener. However, Jupiter is the most accurate and fastest.

## Timeline

| Date | Event |
|------|-------|
| Aug 2024 | Jupiter announced new API structure |
| Sep 2024 | Old endpoints deprecated (reduced rate limits) |
| Jan 2026 | `lite-api.jup.ag` will be deprecated |
| Now | **Action required: Get API key and update config** |

## Why This Matters

### Without API Key
- ❌ Price API won't work (falls back to Birdeye/Dexscreener)
- ❌ Slower price updates
- ❌ Less accurate pricing
- ⚠️ Batch price fetching may fail

### With API Key
- ✅ Fastest price updates
- ✅ Most accurate pricing (same data as jup.ag)
- ✅ Batch fetching works (up to 50 tokens per request)
- ✅ Future-proof (ready for Jan 2026 migration)

## Testing Checklist

- [ ] Got Jupiter API key from portal.jup.ag
- [ ] Added `JUPITER_API_KEY` to `.env`
- [ ] Updated `JUPITER_API_URL` and `JUPITER_PRICE_API_URL` in `.env`
- [ ] Tested bot startup (no errors)
- [ ] Verified price fetching works (check logs for `[BATCH]` messages)
- [ ] No HTTP 401/404 errors from Jupiter

## Troubleshooting

### Error: HTTP 401 Unauthorized

**Cause**: Missing or invalid API key

**Fix**: 
1. Get API key from https://portal.jup.ag
2. Add to `.env`: `JUPITER_API_KEY=your_key_here`

### Error: HTTP 404 Not Found

**Cause**: Using old API endpoints

**Fix**: Update `.env`:
```bash
JUPITER_API_URL=https://lite-api.jup.ag/swap/v1
JUPITER_PRICE_API_URL=https://api.jup.ag/price/v3
```

### Prices not updating

**Cause**: Price API requires API key

**Fix**: Add `JUPITER_API_KEY` to `.env`

**Workaround**: Bot will fall back to Birdeye/Dexscreener (slower but works)

### Batch fetching not working

**Symptoms**: No `[BATCH]` messages in logs

**Cause**: Missing API key

**Fix**: Add `JUPITER_API_KEY` to `.env`

## Migration Path

### Immediate (Now)
1. Get free API key from portal.jup.ag
2. Update `.env` with new endpoints and API key
3. Test in paper mode

### Short Term (Before Jan 2026)
- Continue using `lite-api.jup.ag` (free tier)
- Monitor for deprecation announcements

### Long Term (After Jan 2026)
- Migrate to `api.jup.ag` (requires API key)
- Consider paid plan if hitting rate limits

## Rate Limits

### Free Tier (lite-api.jup.ag)
- Swap API: ~10 requests/second
- Price API: Requires API key (no free tier)

### Free API Key (api.jup.ag)
- Swap API: ~10 requests/second
- Price API: ~10 requests/second
- Up to 50 tokens per price request

### Paid Plans
- Higher rate limits
- Priority support
- See https://portal.jup.ag for pricing

## Support

- **Jupiter Docs**: https://station.jup.ag/docs/
- **API Portal**: https://portal.jup.ag
- **Discord**: https://discord.gg/jup
- **Updates**: https://dev.jup.ag/updates

## Summary

✅ **What to do now:**
1. Get free API key: https://portal.jup.ag
2. Add to `.env`: `JUPITER_API_KEY=your_key_here`
3. Update endpoints in `.env` (see above)
4. Test the bot

⚠️ **What happens if you don't:**
- Price API won't work (falls back to slower alternatives)
- Batch fetching disabled
- Less accurate pricing
- Bot still works but not optimal

🚀 **Benefits of updating:**
- 10x faster price updates
- Most accurate pricing
- Batch fetching enabled
- Future-proof

---

**Updated**: March 2024  
**Status**: Action Required  
**Priority**: High (for optimal performance)
