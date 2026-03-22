# Visual Guide — Three-Phase Trailing Stop System

## New Coin Journey (Entry to Moonshot)

```
Price Chart:
│
│                                                    🌙 $100 (+9900%)
│                                                   /
│                                              🚀 $50 (+4900%)
│                                             /
│                                        $10 (+900%)
│                                       /│
│                                  $5  / │ Phase 3: 35% trail
│                                 /   /  │ (WIDE for moonshots)
│                            $3  /   /   │
│                           /│  /   /    │
│                      $2  / │ /   /     │
│                     /│  /  │/   /      │
│                $1.5/ │ /   /   /       │
│               /│   / │/   /   /        │
│          $1  / │  /  /   /   /         │
│         ────┘  │ /  /   /   /          │
│    Entry       │/  /   /   /           │
│    $1.00       /  /   /   /            │
│               /  /   /   /             │
│              /  /   /   /              │
│             /  /   /   /               │
│            /  /   /   /                │
│           /  /   /   /                 │
│          /  /   /   /                  │
│         /  /   /   /                   │
│        /  /   /   /                    │
│       /  /   /   /                     │
│      /  /   /   /                      │
│     /  /   /   /                       │
│    /  /   /   /                        │
│   /  /   /   /                         │
│  /  /   /   /                          │
│ /  /   /   /                           │
│/  /   /   /                            │
└──────────────────────────────────────────> Time
   │   │   │   │
   │   │   │   └─ Phase 3 stop: $65 (35% below $100)
   │   │   └───── Phase 3 stop: $6.50 (35% below $10)
   │   └───────── Phase 3 stop: $1.95 (35% below $3)
   └───────────── Phase 2 stop: $1.50 (25% below $2)

Phase 1: Entry → $2 (2x)
  Stop: $0.50 → $1.00 (50% trail)
  Protection: Wide (survive volatility)

Phase 2: $2 → $3 (2x → 3x)
  Stop: $1.50 → $2.25 (25% trail)
  Protection: Tight (lock in profits)

Phase 3: $3 → $100+ (3x → 100x) 🚀
  Stop: $1.95 → $65.00 (35% trail)
  Protection: WIDE (let it run!)
```

## Established Coin Journey

```
Price Chart:
│
│                                    🌙 $20 (+1900%)
│                                   /
│                              $10 /
│                             /│  /
│                        $5  / │ /  Phase 3: 30% trail
│                       /│  /  │/   (WIDE for moonshots)
│                  $3  / │ /   /
│                 /│  /  │/   /
│            $2  / │ /   /   /
│           /│  /  │/   /   /
│      $1.4/ │ /   /   /   /
│     /│   / │/   /   /   /
│$1  / │  /  /   /   /   /
│───┘  │ /  /   /   /   /
│      │/  /   /   /   /
│      /  /   /   /   /
│     /  /   /   /   /
│    /  /   /   /   /
│   /  /   /   /   /
│  /  /   /   /   /
│ /  /   /   /   /
│/  /   /   /   /
└────────────────────────────> Time
   │   │   │   │
   │   │   │   └─ Phase 3 stop: $14 (30% below $20)
   │   │   └───── Phase 3 stop: $2.10 (30% below $3)
   │   └───────── Phase 2 stop: $1.12 (20% below $1.4)
   └───────────── Phase 1 stop: $0.60 (40% below $1)

Phase 1: Entry → $1.40 (1.4x)
  Stop: $0.60 → $0.84 (40% trail)
  Protection: Wide (survive volatility)

Phase 2: $1.40 → $3 (1.4x → 3x)
  Stop: $1.12 → $2.40 (20% trail)
  Protection: Tight (lock in profits)

Phase 3: $3 → $20+ (3x → 20x) 🚀
  Stop: $2.10 → $14.00 (30% trail)
  Protection: WIDE (let it run!)
```

## Position Sizing Comparison

```
Balance: 1.0 SOL

NEW COIN:
┌─────────────────────────────────────┐
│ Confidence 60:  0.18 SOL (18%)     │
│ Confidence 80:  0.22 SOL (22%)     │
│ Confidence 100: 0.30 SOL (30%)     │
└─────────────────────────────────────┘

ESTABLISHED COIN (1.5x multiplier):
┌─────────────────────────────────────┐
│ Confidence 60:  0.27 SOL (27%) ✅  │
│ Confidence 80:  0.33 SOL (33%) ✅  │
│ Confidence 100: 0.45 SOL (45%) ✅  │
└─────────────────────────────────────┘
```

## API Call Reduction

```
OLD (5s polling):
┌─────────────────────────────────────┐
│ Position 1: API call                │
│ Position 2: API call                │
│ Position 3: API call                │
│ Sleep 5s                            │
│ Repeat...                           │
└─────────────────────────────────────┘
Total: 3 calls per loop, 5s latency

NEW (0.5s batch):
┌─────────────────────────────────────┐
│ Batch API call (all 3 positions)   │
│ Sleep 0.5s                          │
│ Repeat...                           │
└─────────────────────────────────────┘
Total: 1 call per loop, 0.5s latency
```

## Phase Transitions in Logs

```
[EXECUTOR] ✅ BUY 0.22 SOL of PEPE @ $0.00001234 | target=10x

[POS] PEPE | P&L=+15.2% | stop=0.00000617 | high=0.00001420 | P1

[POS] PEPE | P&L=+105.8% | stop=0.00001543 | high=0.00002540 | P2

[PHASE3] 🚀 MOONSHOT MODE activated for PEPE at +215% | 
         Widening trail to 35% for big runs

[POS] PEPE | P&L=+450.2% | stop=0.00004123 | high=0.00006789 | P3-MOONSHOT

[POS] PEPE | P&L=+2847.5% | stop=0.00019123 | high=0.00029421 | P3-MOONSHOT

[STOP] P3 trailing stop for PEPE | P&L=+1950.3% | stop=+1850.0%
[EXECUTOR] ✅ SELL PEPE | reason=trailing_stop_p3 | tx=...

🚀 SELL PEPE (trailing_stop_p3) | P&L: +1950.3% | +4.29 SOL
```

## Risk vs Reward Matrix

```
                    Risk Level
                    │
              Low   │   Medium   │   High
        ──────────────────────────────────
        │           │            │
Phase 1 │    ✅     │            │
        │  Survive  │            │
        │           │            │
        ──────────────────────────────────
        │           │            │
Phase 2 │           │     ✅     │
        │           │  Lock In   │
        │           │            │
        ──────────────────────────────────
        │           │            │
Phase 3 │           │            │    🚀
        │           │            │ Moonshot
        │           │            │
        ──────────────────────────────────
                    │
              Reward Potential
```

## Decision Tree

```
Position opened
    │
    ▼
Is profit > 200% (3x)?
    │
    ├─ NO ──> Is profit > 100% (2x)?
    │             │
    │             ├─ NO ──> Phase 1 (wide protection)
    │             │
    │             └─ YES ──> Phase 2 (lock in profits)
    │
    └─ YES ──> Phase 3 (MOONSHOT MODE) 🚀
                Widen trail, let it run!
```

## Real-World Example

### BONK (Hypothetical)

```
Day 1:  Entry $0.000001 (0.22 SOL)
        Phase 1: 50% trail

Day 2:  $0.000002 (+100%)
        Phase 2: 25% trail
        Partial TP: Sell 33% at 2x

Day 3:  $0.000003 (+200%)
        Phase 3: 35% trail 🚀
        MOONSHOT MODE activated

Day 7:  $0.000010 (+900%)
        Phase 3 stop: $0.0000065
        Partial TP: Sell 33% at 5x

Day 14: $0.000050 (+4900%)
        Phase 3 stop: $0.0000325
        Partial TP: Sell 33% at 10x

Day 30: $0.000100 (+9900%)
        Phase 3 stop: $0.0000650
        Remaining: 1% of position

Day 31: Price drops to $0.0000650
        STOP TRIGGERED
        Exit at +6400%

Total profit: 
  33% at 2x = 0.22 SOL
  33% at 5x = 0.88 SOL
  33% at 10x = 1.98 SOL
  1% at 64x = 0.14 SOL
  ─────────────────────
  Total: 3.22 SOL profit on 0.22 SOL investment
  ROI: +1464%
```

## Key Takeaways

1. **Phase 3 activates at 3x** — You're already winning big
2. **Trail widens to 35%/30%** — Gives room for 10x, 50x, 100x runs
3. **Partial TPs still active** — Lock profits along the way
4. **Established coins get 1.5x sizing** — Better allocation for proven tokens
5. **All safety features intact** — No increased risk on entry

## Quick Reference

| Phase | Trigger | New Trail | Old Trail | Purpose |
|-------|---------|-----------|-----------|---------|
| P1 | Entry | 50% | 40% | Survive volatility |
| P2 | 2x / 1.4x | 25% | 20% | Lock in profits |
| P3 | 3x | 35% 🚀 | 30% 🚀 | Catch moonshots |

| Coin Type | Sizing Multiplier | Example (1.0 SOL balance, 80 conf) |
|-----------|-------------------|-------------------------------------|
| New | 1.0x | 0.22 SOL |
| Established | 1.5x ✅ | 0.33 SOL |

---

**Ready to catch moonshots while staying protected!** 🚀
