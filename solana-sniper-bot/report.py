"""
report.py — Generate trade history summary from bot logs.
Run anytime while the bot is running (or after) to see all closed trades.

Usage:
    .venv\Scripts\activate
    python report.py
"""
import os
import re


def generate_report():
    log_file = "data/logs/bot.log"

    if not os.path.exists(log_file):
        print("No log file found. Bot hasn't run yet.")
        return

    buys = {}   # mint -> {symbol, size_sol, entry_price}
    trades = [] # closed trades

    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            # Parse BUY: [PAPER] BUY 0.0100 SOL of SYMBOL @ $0.00001234 | target=3x
            if "[PAPER] BUY" in line:
                m = re.search(
                    r"\[PAPER\] BUY ([\d.]+) SOL of (\S+) @ \$([\d.eE+\-]+)",
                    line
                )
                if m:
                    size_sol = float(m.group(1))
                    symbol = m.group(2)
                    entry_price = float(m.group(3))
                    buys[symbol] = {"symbol": symbol, "size_sol": size_sol, "entry_price": entry_price}

            # Parse SELL: [PAPER] SELL 100% of SYMBOL | reason=X | P&L=+X.X% | realized=+X.XXXX SOL
            elif "[PAPER] SELL" in line:
                m = re.search(
                    r"\[PAPER\] SELL [\d]+% of (\S+) \| reason=(\S+) \| P&L=([+\-\d.]+)% \| realized=([+\-\d.]+) SOL",
                    line
                )
                if m:
                    symbol = m.group(1)
                    reason = m.group(2)
                    pnl_pct = float(m.group(3))
                    pnl_sol = float(m.group(4))
                    buy = buys.get(symbol, {})
                    trades.append({
                        "symbol": symbol,
                        "size_sol": buy.get("size_sol", 0),
                        "entry_price": buy.get("entry_price", 0),
                        "pnl_pct": pnl_pct,
                        "pnl_sol": pnl_sol,
                        "reason": reason,
                    })

    if not trades:
        print("\nNo closed trades yet — positions are still open or bot just started.")
        return

    wins = [t for t in trades if t["pnl_sol"] > 0]
    losses = [t for t in trades if t["pnl_sol"] <= 0]
    total_pnl = sum(t["pnl_sol"] for t in trades)
    total_invested = sum(t["size_sol"] for t in trades)
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0

    print("\n" + "=" * 72)
    print("  📊  PAPER TRADE SUMMARY")
    print("=" * 72)
    print(f"  Total Trades   : {len(trades)}")
    print(f"  Wins / Losses  : {len(wins)} / {len(losses)}")
    print(f"  Win Rate       : {len(wins)/len(trades)*100:.1f}%")
    print(f"  Avg Win        : {avg_win:+.1f}%")
    print(f"  Avg Loss       : {avg_loss:+.1f}%")
    print(f"  Total Invested : {total_invested:.4f} SOL")
    print(f"  Total P&L      : {total_pnl:+.4f} SOL")
    print("=" * 72)
    print(f"  {'Symbol':<12} {'Invested':>10} {'P&L %':>8} {'P&L SOL':>10}  Exit Reason")
    print("-" * 72)

    for t in trades:
        marker = "✅" if t["pnl_sol"] > 0 else "❌"
        print(
            f"  {marker} {t['symbol']:<10} "
            f"{t['size_sol']:>8.4f} SOL "
            f"{t['pnl_pct']:>+8.1f}% "
            f"{t['pnl_sol']:>+10.4f} SOL  "
            f"{t['reason']}"
        )

    print("=" * 72 + "\n")


if __name__ == "__main__":
    generate_report()
