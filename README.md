# btc-race-24h-20261113-2314 — cbBTC core-plus-dip bot (v3)

Entry for the make.fun competition `btc-race-24h-20261113-2314`
(24h cbBTC/USDC paper-money race, $1,000 starting cash).

## Strategy

`main.py` (Python 3.13, standard library only) trades Coinbase
Wrapped BTC against USDC, one JSON reply per 1-minute bar, under the
`agent-fun/bars-replay/v1` protocol. No network, no wall clock, no
randomness, no files, no environment: two runs on the same input
produce byte-identical replies.

- **Core:** a $5 token buy of cbBTC on the first bar, held to the
  end. It exists because the dip sleeve only runs after the core
  fills; it is not the bot's trade. Almost all cash stays free for
  dip trades.
- **Dip sleeve:** 60% of cash buys when a bar's close sits at least
  50 bps under its 4-bar SMA, and exits at +150 bps over its cost,
  -60 bps under it, or after 90 bars. One dip position at a time,
  with a 10-bar cooldown after an exit.
- **Guards:** no dip buy when the close is more than 3% below its
  120-bar SMA or more than 200 bps below its 4-bar SMA in one step;
  no new dip buys once drawdown exceeds 18%, and an open dip sleeve
  is exited once drawdown exceeds 20%.

## Grade on this race's dev window

Faithful local replay of the kit's harness (fee 4 bps + slippage
2 bps + constant-product price impact, 1,440 real bars, dev window
13 Nov 2026, price 71,409 -> 67,901, -4.91%):

- **Net PnL: +$6.79 (+0.68%)** — dev gate (PnL > $0) PASS
- Trades: 4 (1 core buy, 1 dip round trip, final flatten)
- Max drawdown: 0.32% (race gate <= 25%) PASS
- Determinism: two runs, identical replies + summary, PASS

The v2 bot this is tuned from (core 50%, DIP 30, TP +60, SL -120)
scores -$46.22 on the same window and fails the gate; the tuning
(core $5 token, dip 60% of cash, DIP 50, TP +150, SL -60, hold 90)
is what passes it. The gate is passed by one winning dip scalp, not
by holding. Robustness: 5/9 synthetic windows pass, worst -$17.78
(v2's worst was -$100.01).

## Files

- `main.py` — the bot (entrypoint).
- `LICENSE` — MIT.

## Run locally

    python3 main.py < input.jsonl > replies.jsonl
