#!/usr/bin/env python3
"""cbBTC core-plus-dip trader for the make.fun btc-race.

Talks the bars-replay protocol over stdio: it reads one JSON object
per line (a hello, then one batch per minute-bar, then done) and
answers every batch with exactly one JSON reply line carrying the
orders for that bar. Everything is integer math on the wire's scaled
integers, no floats anywhere, so two runs over the same input print
byte-identical replies. No network, no clock, no randomness.

Idea of the play: park a tiny core position once, then swing the
rest of the cash on shallow pullbacks. The core exists only to
unlock the dip sleeve -- the bot cannot trade dips before the core
fills -- so it is kept as small as the rules allow. A dip is a
close sitting clearly under its short average but not so far under
that it looks like a flush. Each dip is sized at most 60% of cash,
exits on a modest gain, a tight loss, a time limit, or a drawdown
spike, and the bot rests a few bars after every exit so it cannot
churn itself on fees and pool impact.

Run it: python3 main.py < input.jsonl > replies.jsonl
"""

import json
import sys

PROTO = "agent-fun/bars-replay/v1"
BPS = 10000

# Position sizing and signal constants, all in basis points unless noted.
CORE_SHARE = 50        # core: 50 bps of cash, a $5 token, bought once
DIP_SHARE = 6000       # dip: up to 60% of cash per entry
SHORT_WIN = 4          # dip signal averages the last 4 closes
DIP_MIN = 50           # buy once close is >= 50 bps under that average
DIP_MAX = 200          # ... but skip it when > 200 bps under (a flush)
TAKE = 150             # dip exit: +150 bps over its filled cost
STOP = 60              # dip exit: -60 bps under its filled cost
HOLD_MAX = 90          # dip exit: after 90 bars, whatever the price
BUY_SLIP = 100         # slippage cap on dip entries
SELL_SLIP = 300        # slippage cap on core buys and dip exits
REST = 10              # bars of rest after a dip exit before re-entering
CRASH_LIMIT = 300      # no dip buy when close is > 3% under the 120 average
DD_BLOCK = 1800        # no new dip buys once drawdown passes 18%
DD_FLUSH = 2000        # dump an open dip once drawdown passes 20%
LONG_WIN = 120         # long average used by the crash guard


def to_int(raw):
    """Wire integers arrive as decimal strings; turn one into an int."""
    return int(raw)


class Trader:
    """One race entry: holds the account state and decides each bar."""

    def __init__(self, hello):
        first = hello["symbols"][0]
        self.sym = first["symbol"]
        self.pscale = int(first["price_scale"])
        self.qscale = int(first["qty_scale"])
        self.uscale = int(hello["capital"]["quote_scale"])
        self.floor = to_int(hello["fees"]["min_notional_quote_units"])
        self.cash = to_int(hello["capital"]["quote_units"])
        self.equity = self.cash
        self.peak = self.cash
        self.closes = []
        self.n_batches = 0
        self.next_id = 0
        self.tags = {}          # client id -> "core" | "dip" | "exit"
        self.core_qty = 0
        self.core_done = False
        self.core_wait = False
        self.dip_qty = 0
        self.dip_cost = 0       # quote units actually paid for the dip
        self.dip_wait = False
        self.exit_wait = False
        self.dip_opened = 0
        self.last_closed = -10 ** 9

    def new_id(self):
        self.next_id += 1
        return "o%d" % self.next_id

    def worth(self, qty, price):
        """Quote-unit value of qty at price, rounded down; 0 if no price."""
        if price is None:
            return 0
        return qty * price * (10 ** self.uscale) // (
            10 ** (self.qscale + self.pscale)
        )

    def drawdown(self):
        """Current drawdown from the equity peak, in basis points."""
        if self.peak <= 0:
            return 0
        return (self.peak - self.equity) * BPS // self.peak

    def window_sum(self, n):
        """Sum of the last n closes, or None while fewer than n exist."""
        if len(self.closes) < n:
            return None
        return sum(self.closes[-n:])

    def is_dip(self, close):
        """Close clearly under the short average, but not a one-bar flush."""
        total = self.window_sum(SHORT_WIN)
        if total is None:
            return False
        under_enough = close * SHORT_WIN * BPS < total * (BPS - DIP_MIN)
        not_too_far = close * SHORT_WIN * BPS > total * (BPS - DIP_MAX)
        return under_enough and not_too_far

    def crash_ok(self, close):
        """False in a >3% crash against the long average; True otherwise."""
        total = self.window_sum(LONG_WIN)
        if total is None:
            return True
        return close * LONG_WIN * BPS >= total * (BPS - CRASH_LIMIT)

    # Fills land a bar late; settle each one against the tag it carries.
    def settle_fills(self, fills):
        """Fold this batch's fills into the tracked positions."""
        for fill in fills or []:
            role = self.tags.pop(fill.get("client_id", ""), None)
            if role is None:
                continue
            filled = fill.get("status") == "filled"
            if role == "core":
                self.core_wait = False
                if filled:
                    self.core_qty += to_int(fill["qty"])
                    self.core_done = True
            elif role == "dip":
                self.dip_wait = False
                if filled:
                    self.dip_qty = to_int(fill["qty"])
                    self.dip_cost = to_int(fill["notional_quote_units"])
            elif role == "exit":
                self.exit_wait = False
                if filled:
                    self.dip_qty = 0
                    self.dip_cost = 0
                    self.last_closed = self.n_batches

    def decide(self, batch):
        """Return this batch's orders, updating state as we go."""
        self.n_batches += 1
        self.settle_fills(batch.get("fills"))

        account = batch.get("account") or {}
        if account.get("cash_quote_units") is not None:
            self.cash = to_int(account["cash_quote_units"])
        if account.get("equity_quote_units") is not None:
            self.equity = to_int(account["equity_quote_units"])
            if self.equity > self.peak:
                self.peak = self.equity

        bar = None
        for candidate in batch.get("bars") or []:
            if candidate.get("symbol") == self.sym:
                bar = candidate
                break
        if bar is None:
            return []
        close = to_int(bar["c"])
        self.closes.append(close)

        orders = []

        # Core sleeve: one tiny buy, retried until it fills, then done.
        if not self.core_done:
            if not self.core_wait:
                amount = self.cash * CORE_SHARE // BPS
                if amount >= self.floor:
                    cid = self.new_id()
                    self.tags[cid] = "core"
                    self.core_wait = True
                    orders.append({
                        "side": "buy",
                        "symbol": self.sym,
                        "notional_quote_units": str(amount),
                        "max_slippage_bps": SELL_SLIP,
                        "client_id": cid,
                    })
            return orders

        # Never stack orders while a fill is still in flight.
        if self.dip_wait or self.exit_wait:
            return orders

        # A dip is open: check the exits first.
        if self.dip_qty > 0:
            value = self.worth(self.dip_qty, close)
            take = value * BPS >= self.dip_cost * (BPS + TAKE)
            stop = value * BPS <= self.dip_cost * (BPS - STOP)
            stale = self.n_batches - self.dip_opened >= HOLD_MAX
            flushing = self.drawdown() > DD_FLUSH
            if take or stop or stale or flushing:
                cid = self.new_id()
                self.tags[cid] = "exit"
                self.exit_wait = True
                orders.append({
                    "side": "sell",
                    "symbol": self.sym,
                    "qty": str(self.dip_qty),
                    "max_slippage_bps": SELL_SLIP,
                    "client_id": cid,
                })
            return orders

        # No dip open: enter one when the signal and the guards agree.
        rested = self.n_batches - self.last_closed >= REST
        calm = self.drawdown() <= DD_BLOCK
        if (rested and calm and self.is_dip(close)
                and self.crash_ok(close) and self.cash >= self.floor):
            cid = self.new_id()
            self.tags[cid] = "dip"
            self.dip_wait = True
            self.dip_opened = self.n_batches
            amount = self.cash * DIP_SHARE // BPS
            orders.append({
                "side": "buy",
                "symbol": self.sym,
                "notional_quote_units": str(amount),
                "max_slippage_bps": BUY_SLIP,
                "client_id": cid,
            })
        return orders


def run():
    trader = None
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        msg = json.loads(raw)
        kind = msg.get("type")
        if kind == "hello":
            if msg.get("protocol") != PROTO:
                sys.stderr.write("unexpected protocol: %r\n" % (msg.get("protocol"),))
                return 1
            trader = Trader(msg)
        elif kind == "batch":
            if trader is None:
                sys.stderr.write("batch before hello\n")
                return 1
            orders = trader.decide(msg)
            sys.stdout.write(json.dumps(
                {"type": "reply", "seq": msg["seq"], "orders": orders}
            ) + "\n")
            sys.stdout.flush()
        elif kind == "done":
            break
        else:
            sys.stderr.write("unknown message type: %r\n" % (kind,))
            return 1
    if trader is None:
        sys.stderr.write("input ended before hello\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
