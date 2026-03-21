# Testing Checklist — v2.0 Validation

Use this checklist to verify the v2.0 upgrade is working correctly before going live.

## Pre-Testing Setup

- [ ] Backup current `.env` file: `cp .env .env.backup`
- [ ] Backup current code: `cp -r solana-sniper-bot solana-sniper-bot.backup`
- [ ] Pull latest code: `git pull origin main`
- [ ] Update dependencies: `pip install -r requirements.txt --upgrade`
- [ ] Set paper mode: `PAPER_TRADE_MODE=True` in `.env`
- [ ] Set network: `NETWORK=devnet` or `mainnet` in `.env`

## Phase 1: Startup & Configuration

### Basic Startup
- [ ] Bot starts without errors
- [ ] Wallet balance loads correctly
- [ ] RPC connection successful
- [ ] WebSocket monitor connects (Pump.fun)
- [ ] No import errors or missing dependencies

### Configuration Validation
- [ ] `POSITION_CHECK_INTERVAL = 0.5` in `core/config.py`
- [ ] `PRICE_FEED_TIMEOUT = 10.0` in `core/config.py`
- [ ] `BATCH_PRICE_FETCH = True` in `core/config.py`
- [ ] `ENABLE_WEBSOCKET_PRICES` set correctly in `.env`

### Log Output Check
Look for these in `data/logs/bot.log`:
- [ ] `[WALLET] Balance: X.XXXX SOL`
- [ ] `[MONITOR] Connected to Pump.fun WebSocket`
- [ ] `[EXECUTOR] Position manager started`
- [ ] No error messages on startup

## Phase 2: Batch Price Fetching

### Wait for a Trade Signal
- [ ] Bot detects a new token
- [ ] Analysis runs (RugCheck, market data, etc.)
- [ ] Token passes filters and enters position

### Verify Batch Fetching
Look for these log messages:
- [ ] `[BATCH] Fetched X/Y prices from Jupiter`
- [ ] Batch fetch happens once per loop (not per position)
- [ ] Fallback to individual fetch if batch fails for specific coin

### Performance Metrics
- [ ] Position checks happen every ~0.5s (check timestamps)
- [ ] API call count reduced (compare to v1.0 if you have logs)
- [ ] No rate limit errors from Jupiter

## Phase 3: Position Management

### Open Position Monitoring
With at least one open position:
- [ ] Price updates every 0.5s
- [ ] Stop-loss ratchets upward as price rises
- [ ] High water mark tracked correctly
- [ ] Phase 2 triggers at correct profit level

### Stop-Loss Testing
Simulate or wait for a price drop:
- [ ] Stop-loss triggers within 0.5-1.0s of price hitting stop
- [ ] Sell order fires asynchronously (doesn't block loop)
- [ ] Other positions continue updating during sell
- [ ] Exit reason logged correctly

### Price Feed Timeout
Simulate or wait for a dead price feed:
- [ ] "Price feed dead" exit triggers at 10s (not 15s)
- [ ] Position exits cleanly
- [ ] Other positions unaffected

## Phase 4: Enhanced Rug Detection

### Pre-Entry Filters
Monitor analysis logs for new tokens:
- [ ] LP burn/lock check working
- [ ] Mint authority check working
- [ ] Freeze authority check working
- [ ] Top holder concentration checks (50% / 70%)

### Rejection Logs
Look for these rejection reasons:
- [ ] `LP not secured (burned=False, locked=X%)`
- [ ] `Mint authority not revoked`
- [ ] `Freeze authority not revoked`
- [ ] `Top 5 holders own X%` (if > 50%)
- [ ] `Top 10 holders own X%` (if > 70%)

### Pass-Through Rate
- [ ] Fewer tokens passing filters (stricter = better)
- [ ] Only high-quality tokens entering positions
- [ ] No obvious rugs getting through

## Phase 5: Async Sell Orders

### Multiple Positions
Open 2-3 positions simultaneously:
- [ ] All positions update independently
- [ ] Sell order on one position doesn't block others
- [ ] Timestamps show parallel execution

### Sell Order Logs
Look for:
- [ ] `[EXECUTOR] ✅ SELL symbol | reason=X | tx=...`
- [ ] Sell completes while loop continues
- [ ] No "waiting for sell" delays

## Phase 6: WebSocket Streaming (Optional)

Only if `ENABLE_WEBSOCKET_PRICES=True`:

### Connection
- [ ] WebSocket connects to `HELIUS_WSS_URL`
- [ ] Subscription successful for open positions
- [ ] No connection errors

### Price Updates
- [ ] Prices update from WebSocket feed
- [ ] Fallback to batch/individual if WebSocket fails
- [ ] No gaps in price data

### Failure Handling
Disconnect WebSocket manually (if possible):
- [ ] Bot detects disconnection
- [ ] Auto-fallback to batch polling
- [ ] No position exits due to WebSocket failure

## Phase 7: Performance Validation

### Timing Metrics
Record these from logs:
- [ ] Average loop time: ~0.5-0.6s (with network latency)
- [ ] Price update frequency: 2 checks per second
- [ ] Stop-loss trigger latency: <1s from price drop

### API Usage
Monitor API calls over 5 minutes:
- [ ] Jupiter price API: ~120 calls (1 per 0.5s loop)
- [ ] Compare to v1.0: Should be 66-80% reduction
- [ ] No rate limit errors

### Resource Usage
Check system resources:
- [ ] Memory: ~55-60MB (slight increase from v1.0)
- [ ] CPU: 5-10% idle, 20-35% active
- [ ] Network: Stable, no spikes

## Phase 8: Edge Cases

### No Open Positions
- [ ] Loop continues running
- [ ] No API calls when no positions
- [ ] Sleeps 0.5s between checks

### All Positions Exit Simultaneously
- [ ] All sell orders fire in parallel
- [ ] No blocking or delays
- [ ] Loop continues normally

### Network Interruption
Disconnect network briefly:
- [ ] Bot handles gracefully
- [ ] Reconnects automatically
- [ ] No crashes or hangs

### Emergency Sell All
Set `EMERGENCY_SELL_ALL=True`:
- [ ] All positions exit immediately
- [ ] Sell orders fire in parallel
- [ ] No new positions opened

## Phase 9: Paper Trade Validation

### Run for 24 Hours
- [ ] No crashes or errors
- [ ] Positions managed correctly
- [ ] Paper P&L tracked accurately
- [ ] Logs clean and readable

### Performance Summary
After 24 hours, check:
- [ ] Total trades executed
- [ ] Average entry-to-exit time
- [ ] Stop-loss trigger accuracy
- [ ] False "price feed dead" exits (should be minimal)

## Phase 10: Production Readiness

### Final Checks
- [ ] All tests above passed
- [ ] No critical errors in logs
- [ ] Performance meets expectations
- [ ] Comfortable with faster response times

### Go Live Preparation
- [ ] Set `PAPER_TRADE_MODE=False` in `.env`
- [ ] Verify wallet has sufficient SOL
- [ ] Telegram alerts configured (optional)
- [ ] Monitoring in place (logs, alerts)

### Post-Launch Monitoring
First 24 hours live:
- [ ] Monitor logs closely
- [ ] Verify real trades execute correctly
- [ ] Check stop-loss triggers are accurate
- [ ] Validate P&L tracking

## Troubleshooting

### Issue: Batch fetching not working
**Symptoms**: No `[BATCH]` messages in logs
**Fix**: Check `BATCH_PRICE_FETCH = True` in `core/config.py`

### Issue: Position checks still slow (5s)
**Symptoms**: Timestamps show 5s gaps
**Fix**: Check `POSITION_CHECK_INTERVAL = 0.5` in `core/config.py`

### Issue: Too many "price feed dead" exits
**Symptoms**: Positions exit at 10s frequently
**Fix**: Increase `PRICE_FEED_TIMEOUT = 15.0` in `core/config.py`

### Issue: API rate limits
**Symptoms**: HTTP 429 errors from Jupiter
**Fix**: Slow down `POSITION_CHECK_INTERVAL = 1.0` in `core/config.py`

### Issue: WebSocket not connecting
**Symptoms**: No WebSocket price updates
**Fix**: 
1. Verify premium RPC subscription
2. Check `HELIUS_WSS_URL` in `.env`
3. Set `ENABLE_WEBSOCKET_PRICES=False` to use polling

## Success Criteria

✅ **Minimum Requirements:**
- [ ] Bot runs without crashes for 24+ hours
- [ ] Batch price fetching working (1 API call per loop)
- [ ] Position checks every 0.5s
- [ ] Stop-loss triggers within 1s of price drop
- [ ] No blocking sell orders

✅ **Optimal Performance:**
- [ ] All minimum requirements met
- [ ] Enhanced rug detection rejecting obvious scams
- [ ] API usage 66-80% lower than v1.0
- [ ] No false "price feed dead" exits
- [ ] WebSocket streaming working (if enabled)

## Sign-Off

- [ ] All critical tests passed
- [ ] Performance validated
- [ ] Ready for production
- [ ] Monitoring in place

**Tested by**: _______________  
**Date**: _______________  
**Version**: 2.0.0  
**Status**: ☐ Pass ☐ Fail ☐ Needs Review

---

**Notes:**
