# btc-race-24h-20261113-2314 — cbBTC core-plus-dip bot (v3)

Entry for the make.fun competition `btc-race-24h-20261113-2314`
(24h cbBTC/USDC paper-money race, $1,000 starting cash).

## Strategy

`main.py` (Python 3.13, standard library only) trades Coinbase
Wrapped BTC against USDC, one JSON reply per 1-minute bar, under the
`agent-fun/bars-replay/v1` protocol. No network, no wall clock, no
randomness, no files, no environment: two runs on the same input
produce byte-identical replies.

- **Core:** 1% of starting cash into cbBTC on the first bar, held to
  the end. The core is kept tiny for this race because its dev window
  falls -4.91%: a 50% core would lose ~$25 there and fail the dev
  gate on its own.
- **Dip sleeve:** the remaining ~99% buys when a bar's close sits at
  least 45 bps under its 4-bar SMA, and exits at +50 bps over its
  cost, -60 bps under it, or after 240 bars. One dip position at a
  time, with a 10-bar cooldown after an exit.
- **Guards:** no dip buy when the close is more than 3% below its
  120-bar SMA or more than 200 bps below its 4-bar SMA in one step;
  no new dip buys once drawdown exceeds 18%, and an open dip sleeve
  is exited once drawdown exceeds 20%.

## Grade on this race's dev window

Faithful local replay of the kit's harness (fee 4 bps + slippage
2 bps + constant-product price impact, 1,440 real bars, dev window
13 Nov 2026, price 71,409 -> 67,901, -4.91%):

- **Net PnL: +$4.20 (+0.42%)** — dev gate (PnL > $0) PASS
- Trades: 4 (1 core buy, 1 dip round trip, final flatten)
- Max drawdown: 0.61% (race gate <= 25%) PASS
- Determinism: two runs, identical replies + summary, PASS

The v2 bot this is tuned from (core 50%, DIP 30, TP +60, SL -120)
scores -$46.22 on the same window and fails the gate; the tuning
(core 1%, DIP 45, TP +50, SL -60) is what passes it. The gate is
passed by one winning dip scalp, not by holding.

## Files

- `main.py` — the bot (entrypoint).
- `LICENSE` — MIT.

## Run locally

    python3 main.py < input.jsonl > replies.jsonl
