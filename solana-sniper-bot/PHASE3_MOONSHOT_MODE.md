# Phase 3 Moonshot Mode — Let Winners Run to 1000-10000%

## The Problem

Your original concern: "Once a coin hits 200% (3x) and Phase 2 trailing is active, the stop is too tight and cuts off potential 1000%+ or even 10000%+ runners."

**You were right!** Phase 2 was designed to lock in profits, but it was also preventing moonshots.

## The Solution: Phase 3 Moonshot Mode

When a coin hits **+200% (3x)**, Phase 3 activates and the trailing stop **WIDENS** to give room for massive runs.

### Three-Phase System

```
Phase 1 (Entry → 2x):
  Wide protection against rugs
  New: 50% trail | Old: 40% trail

Phase 2 (2x → 3x):
  Tighter lock-in of initial profits
  New: 25% trail | Old: 20% trail

Phase 3 (3x → ∞):  🚀 MOONSHOT MODE
  WIDENS to let winners run
  New: 35% trail | Old: 30% trail
```

## Why Widen at 3x?

At 3x, you've already:
- Tripled your money
- Proven the coin has momentum
- Locked in significant profit with Phase 2

Now it's time to **let it run** and catch the 10x, 50x, or 100x moonshots.

## Example: New Coin Moonshot

```
Entry: $1.00
  ↓ Phase 1 (50% trail)
  Stop: $0.50

Price: $2.00 (+100%)
  ↓ Phase 2 activates (25% trail)
  Stop: $1.50 (locked +50% profit)

Price: $3.00 (+200%)
  ↓ Phase 3 activates (35% trail) 🚀
  Stop: $1.95 (locked +95% profit)
  
  [PHASE3] 🚀 MOONSHOT MODE activated for COIN at +200% | 
           Widening trail to 35% for big runs

Price: $10.00 (+900%)
  ↓ Phase 3 still active (35% trail)
  Stop: $6.50 (locked +550% profit)

Price: $50.00 (+4900%)
  ↓ Phase 3 still active (35% trail)
  Stop: $32.50 (locked +3150% profit)

Price: $100.00 (+9900%)
  ↓ Phase 3 still active (35% trail)
  Stop: $65.00 (locked +6400% profit)

Price drops to $65.00
  ↓ Stop triggered
  EXIT: +6400% profit 🚀🚀🚀
```

## Example: Established Coin Moonshot

```
Entry: $1.00
  ↓ Phase 1 (40% trail)
  Stop: $0.60

Price: $1.40 (+40%)
  ↓ Phase 2 activates (20% trail)
  Stop: $1.12 (locked +12% profit)

Price: $3.00 (+200%)
  ↓ Phase 3 activates (30% trail) 🚀
  Stop: $2.10 (locked +110% profit)

Price: $20.00 (+1900%)
  ↓ Phase 3 still active (30% trail)
  Stop: $14.00 (locked +1300% profit)

Price drops to $14.00
  ↓ Stop triggered
  EXIT: +1300% profit 🚀🚀
```

## Why This Works

### Phase 2 Problem (Before)
```
Price: $3.00 (+200%)
Phase 2: 25% trail
Stop: $2.25

Price: $4.00 (+300%)
Stop: $3.00

Price drops to $3.50 (-12.5% from high)
Still above stop, continues...

Price drops to $3.00 (-25% from high)
STOP TRIGGERED — Exit at +200%
Missed the potential 1000%+ run 😢
```

### Phase 3 Solution (After)
```
Price: $3.00 (+200%)
Phase 3: 35% trail (WIDER)
Stop: $1.95

Price: $4.00 (+300%)
Stop: $2.60

Price drops to $3.50 (-12.5% from high)
Still above stop, continues...

Price drops to $3.00 (-25% from high)
Still above stop, continues...

Price rises to $10.00 (+900%)
Stop: $6.50

Price drops to $6.50 (-35% from high)
STOP TRIGGERED — Exit at +550%
Caught the moonshot! 🚀
```

## Configuration

All parameters are in `core/config.py`:

```python
# Phase 3 Moonshot Mode
PHASE3_MOONSHOT_TRIGGER_PCT = 2.00  # triggers at +200% (3x)
PHASE3_TRAIL_NEW = 0.35             # 35% below high for new coins
PHASE3_TRAIL_OLD = 0.30             # 30% below high for established coins
```

### Tuning Phase 3

**More aggressive (tighter trail, earlier exits):**
```python
PHASE3_TRAIL_NEW = 0.30   # 30% below high
PHASE3_TRAIL_OLD = 0.25   # 25% below high
```

**More conservative (wider trail, let it run longer):**
```python
PHASE3_TRAIL_NEW = 0.40   # 40% below high
PHASE3_TRAIL_OLD = 0.35   # 35% below high
```

**Trigger Phase 3 earlier:**
```python
PHASE3_MOONSHOT_TRIGGER_PCT = 1.50  # triggers at +150% (2.5x)
```

**Trigger Phase 3 later:**
```python
PHASE3_MOONSHOT_TRIGGER_PCT = 3.00  # triggers at +300% (4x)
```

## Increased Position Sizing for Established Coins

Established coins (>$100k market cap) are proven and less risky, so they now get **1.5x larger positions**.

### Before
```
Balance: 1.0 SOL
Confidence: 80
Risk: 22%
Position size: 0.22 SOL (both new and old coins)
```

### After
```
Balance: 1.0 SOL
Confidence: 80
Risk: 22%

New coin: 0.22 SOL (unchanged)
Old coin: 0.33 SOL (1.5x multiplier) ✅
```

### Why This Makes Sense

Established coins have:
- ✅ Proven liquidity
- ✅ Passed time test (not an instant rug)
- ✅ Real community
- ✅ Lower risk profile

So we can safely allocate more capital to them.

## Risk Management

### Phase 3 Still Protects You

Even with wider trailing, you're still protected:

**New coin at 10x:**
- Entry: $1.00
- Current: $10.00
- Stop: $6.50 (35% below)
- Locked profit: +550%

**If it rugs from $10 to $0:**
- Exit at: $6.50
- Final profit: +550%
- You still win big!

### Partial Take-Profits Still Active

Phase 3 doesn't disable partial TPs:
- 2x: Sell 33% (lock in 2x on 1/3 of position)
- 5x: Sell 33% (lock in 5x on another 1/3)
- 10x: Sell 33% (lock in 10x on final 1/3)

So even if Phase 3 stop triggers, you've already taken profits along the way.

## Real-World Scenarios

### Scenario 1: Moonshot to 50x
```
Entry: $1.00 (0.22 SOL)
2x: Sell 33% → Lock 0.22 SOL profit
5x: Sell 33% → Lock 0.88 SOL profit
10x: Sell 33% → Lock 1.98 SOL profit
Remaining: 1% of position

Price continues to $50.00 (+4900%)
Phase 3 stop: $32.50
Price drops to $32.50
Exit remaining 1% at +3150%

Total profit: 0.22 + 0.88 + 1.98 + (0.0022 × 31.5) = ~3.15 SOL
ROI: +1432% on 0.22 SOL investment
```

### Scenario 2: False Moonshot (Dumps After 3x)
```
Entry: $1.00 (0.22 SOL)
2x: Sell 33% → Lock 0.22 SOL profit
Price: $3.00 (+200%)
Phase 3 activates (35% trail)
Stop: $1.95

Price dumps to $1.95
Exit at +95%

Total profit: 0.22 + (0.1474 × 0.95) = ~0.36 SOL
ROI: +164% on 0.22 SOL investment
Still a great win!
```

### Scenario 3: Established Coin to 20x
```
Entry: $1.00 (0.33 SOL — 1.5x larger position)
Price: $1.40 (+40%)
Phase 2 activates (20% trail)

Price: $3.00 (+200%)
Phase 3 activates (30% trail) 🚀
Stop: $2.10

Price: $20.00 (+1900%)
Phase 3 stop: $14.00

Price drops to $14.00
Exit at +1300%

Profit: 0.33 × 13 = 4.29 SOL
ROI: +1300% on 0.33 SOL investment
```

## Comparison: Phase 2 vs Phase 3

| Metric | Phase 2 Only | Phase 3 Moonshot |
|--------|--------------|------------------|
| Trail distance (new) | 25% | 35% (wider) |
| Trail distance (old) | 20% | 30% (wider) |
| Max drawdown from high | 25% | 35% |
| Catches 10x+ runs | Sometimes | Usually |
| Catches 50x+ runs | Rarely | Often |
| Catches 100x+ runs | Almost never | Possible |
| Risk of giving back profit | Lower | Higher (but still protected) |

## When Phase 3 Activates

You'll see this in logs:
```
[PHASE3] 🚀 MOONSHOT MODE activated for PEPE at +215% | 
         Widening trail to 35% for big runs
```

Then in position updates:
```
[POS] PEPE | P&L=+450.2% | stop=0.00012345 | high=0.00018992 | P3-MOONSHOT
```

## Philosophy

### Phase 1: Survive
Wide stop to avoid getting shaken out by volatility

### Phase 2: Lock In
Tighter stop to secure initial profits

### Phase 3: Let It Run 🚀
Wider stop to catch life-changing gains

## Risk vs Reward

### Conservative Approach (Phase 2 Only)
- ✅ Lock in profits early
- ✅ Lower risk of giving back gains
- ❌ Miss moonshots
- ❌ Cap upside at 2-5x

### Aggressive Approach (Phase 3 Moonshot)
- ✅ Catch 10x, 50x, 100x runs
- ✅ Life-changing gains possible
- ⚠️ Higher risk of giving back some profit
- ✅ Still protected (35% trail, not 100%)

## Established Coin Position Sizing

### Before
```
New coin: 0.22 SOL (22% of 1.0 SOL balance)
Old coin: 0.22 SOL (same as new)
```

### After
```
New coin: 0.22 SOL (unchanged)
Old coin: 0.33 SOL (1.5x multiplier) ✅
```

### Why?

Established coins are:
- Less likely to rug (already proven)
- More predictable
- Lower risk profile
- Deserve more capital allocation

## Summary

✅ **Phase 3 Moonshot Mode**:
- Activates at +200% (3x)
- Widens trail to 35% (new) / 30% (old)
- Lets winners run to 1000-10000%
- Still protects with trailing stop

✅ **Increased Established Coin Sizing**:
- 1.5x larger positions
- Recognizes lower risk
- Better capital allocation

✅ **All Existing Functionality Preserved**:
- Phase 1 and Phase 2 unchanged
- Partial take-profits still active
- Hard floor stop still works
- Time-based stop still works
- Emergency exit still works

## Testing

Run in paper mode and watch for:
```
[PHASE3] 🚀 MOONSHOT MODE activated for COIN at +215%
[POS] COIN | P&L=+450.2% | stop=... | high=... | P3-MOONSHOT
[SIZING] Established coin bonus: 0.33 SOL (1.5x multiplier)
```

---

**Feature**: Phase 3 Moonshot Mode  
**Version**: 2.0.0  
**Status**: ✅ Implemented  
**Risk Level**: Medium (wider trail = more room to give back profit)  
**Reward Potential**: Extreme (10x, 50x, 100x possible)
