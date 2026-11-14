# btc-race-24h-20261113-2314 — core-plus-dip cbBTC bot (v3)

A small deterministic bot for the make.fun btc-race, written in pure
Python 3 standard library. It talks the `agent-fun/bars-replay/v1`
protocol over stdio: one JSON reply per 1-minute bar, integer math
only, no network, no clock, no randomness.

## Strategy

- **Core:** a $5 token buy of cbBTC on the first bar, held to the
  end. It exists only to unlock the dip sleeve.
- **Dip sleeve:** up to 60% of cash buys when the close sits at least
  50 bps under its 4-bar average (but not more than 200 bps under,
  which is treated as a flush). It exits at +150 bps over cost,
  -60 bps under cost, or after 90 bars, with a 10-bar rest after
  every exit.
- **Guards:** no dip buys in a >3% crash against the 120-bar
  average; no new dip buys once drawdown passes 18%; an open dip is
  dumped once drawdown passes 20%.

## Verification (impact-aware replay, race's own kit)

On the race's real dev window (1,440 bars, BTC -4.91%):

- Net PnL **+$6.79**, 4 trades, max drawdown **0.32%**
- Dev gate PASS, drawdown gate PASS, determinism PASS (two runs
  byte-identical)

The same bot on the alternate dev window file replays at **+$8.48**.

## Warning

The race window itself is unseen. Passing the dev gate only
qualifies the bot to race; it does not guarantee a prize. The
previous v2 parameter set lost money on this dev window and was
not submitted.

## Files

- `main.py` — the bot (the entrypoint)
- `LICENSE` — MIT
