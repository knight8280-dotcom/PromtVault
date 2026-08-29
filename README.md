# CBot

An automated crypto trading bot with backtesting, paper trading, and risk
controls that are enforced before every order.

Works with any [ccxt](https://github.com/ccxt/ccxt) exchange (Binance, Kraken,
Coinbase, Bybit, …). Three strategies ship with it, and adding your own is about
twenty lines.

> **Read this first.** Automated trading can lose money faster than you can
> react. This software comes with no warranty and no promise of profit — the
> bundled strategies are textbook examples, not edges. Backtest results are not
> predictions. Run on a testnet, then on money you can afford to lose entirely,
> and never before you understand what every setting in your config does.

## Install

```bash
git clone https://github.com/knight8280-dotcom/PromtVault.git cbot
cd cbot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.10+. Everything except live data and live trading works without `ccxt`.

## Try it in one command

No exchange account, no API keys, no network:

```bash
python -m tradingbot.cli backtest --synthetic --strategy sma_cross
```

```
  BTC/USDT — sma_cross(fast_period=20, slow_period=50, ...)
  ============================================================
  Starting equity            10,000.00
  Ending equity               9,072.05
  Total return                  -9.28%
  Max drawdown                  14.55%
  Sharpe ratio                   -2.86
  Trades                            61
  Win rate                      42.62%  (26W / 35L)
  Profit factor                   0.66
```

Synthetic data is a random walk, so a losing result is the *correct* one — no
edge, minus fees, is negative. It exercises the machinery; it tells you nothing
about a strategy. Use real data before drawing any conclusion.

## Real data

```bash
cp config/config.example.yaml config/config.yaml

# Download and cache a year of hourly candles
python -m tradingbot.cli fetch -c config/config.yaml --days 365

# Backtest against it
python -m tradingbot.cli backtest -c config/config.yaml
```

Fetching needs no API key — public market data is unauthenticated. Candles are
cached in `data_cache/` so repeat backtests are instant and offline. You can also
supply your own file with `--csv path.csv` (columns:
`timestamp,open,high,low,close,volume`).

## Paper trading

Real prices, simulated money, the same code path live trading uses:

```bash
python -m tradingbot.cli paper -c config/config.yaml
```

It polls for new closed bars, applies the strategy, sizes through the risk
manager, and simulates fills with fees and slippage. State is written to
`state/bot_state.json` after every change, so a restart resumes with open
positions and risk counters intact. Ctrl-C stops cleanly at the end of a cycle.

Check on it any time:

```bash
python -m tradingbot.cli status -c config/config.yaml
```

## Live trading

**Live mode places real orders with real money.** Three independent locks stand
between a typo and a filled order:

1. `execution.confirm_live: true` in your config file
2. `--i-understand-the-risk` on the command line
3. Typing `TRADE REAL MONEY` at the prompt (skipped on a testnet)

```bash
set -a && source .env && set +a
python -m tradingbot.cli live -c config/config.yaml --i-understand-the-risk
```

Credentials come from environment variables only, never from the config file —
a config is always safe to commit or share. Create exchange API keys with
**trading permission only**; never enable withdrawals on a key a bot holds.

Start with `exchange.testnet: true`. Run it for weeks. Only then consider real
funds, and start with an amount whose total loss would not matter to you.

## Strategies

```bash
python -m tradingbot.cli strategies    # list all, with parameters and defaults
```

| Strategy | Idea | Key parameters |
|---|---|---|
| `sma_cross` | Trend following. Long when a fast MA crosses above a slow one, exit on the reverse. | `fast_period`, `slow_period`, `use_ema`, `atr_stop_multiple` |
| `rsi_reversion` | Mean reversion. Buy oversold dips, but only inside an uptrend. | `rsi_period`, `oversold`, `exit_level`, `trend_filter_period` |
| `breakout` | Donchian channel. Buy N-bar highs, exit on M-bar lows, ATR stop. | `entry_period`, `exit_period`, `atr_stop_multiple`, `volume_factor` |

Override any parameter without editing the config:

```bash
python -m tradingbot.cli backtest -c config/config.yaml \
    --strategy breakout --param entry_period=30 --param atr_stop_multiple=3
```

### Writing your own

A strategy maps a window of candles to an intent. It never places orders and
never sees a bar that had not closed at the moment it is judging — which is what
makes a backtest meaningful.

```python
from tradingbot.indicators import ema
from tradingbot.models import Signal, SignalType
from tradingbot.strategies.base import Strategy, register

@register
class MyStrategy(Strategy):
    name = "my_strategy"
    default_params = {"period": 20}

    @property
    def warmup(self) -> int:
        return self.params["period"] + 1

    def generate(self, candles, position):
        closes = [c.close for c in candles]
        trend = ema(closes, self.params["period"])
        if trend[-1] is None:
            return self._hold()
        if position is None and closes[-1] > trend[-1]:
            return Signal(SignalType.ENTER_LONG, reason="above trend",
                          stop_price=closes[-1] * 0.97)
        if position is not None and closes[-1] < trend[-1]:
            return Signal(SignalType.EXIT, reason="below trend")
        return self._hold()
```

Import it once (add it to `tradingbot/strategies/__init__.py`) and it is
available everywhere by name.

## Parameter search

```bash
python -m tradingbot.cli optimize -c config/config.yaml \
    --strategy sma_cross \
    --grid fast_period=5,10,20 --grid slow_period=30,50,100 --sort sharpe
```

The top row is the best fit to *that* data — which is exactly what overfitting
looks like. Re-test the winner on a period you did not search over before
believing it.

## Risk controls

Strategies decide *whether* to trade. The risk manager decides *how much*, and
it is the only component allowed to. Every limit is enforced before an order
exists.

**Position sizing** is derived from the stop, not picked arbitrarily. With
`risk_per_trade: 0.01`, each trade is sized so that hitting its stop costs 1% of
equity — a wide stop produces a small position, a tight stop a larger one. Three
caps then apply: single-position notional, total exposure, and available cash.

**Circuit breakers** flatten every open position and stop trading:

| Limit | Behaviour |
|---|---|
| `max_daily_loss_pct` | Halts for the day; resets at UTC midnight |
| `max_drawdown_pct` | Halts until you manually restart — it does not reset on its own |

A halt survives a restart. If the drawdown breaker trips, the bot will not
quietly resume when you bring it back up; that is deliberate.

**Protective exits** are checked every polling cycle, not only on new bars, so a
stop does not wait for an hourly candle to close. When one bar spans both the
stop and the target, the stop is assumed to have hit first — a backtest should
not flatter itself about which came first, and a gap through a stop fills at the
open, not at the stop price.

## How a backtest avoids lying to you

Most backtests are optimistic in ways that are easy to miss. This one:

- shows a strategy only the candles that had closed at that point — never a bar from the future;
- fills an entry at the **next** bar's open, the earliest a real order could execute, not at the close that triggered it;
- charges fees on both sides and applies slippage against you on every fill;
- refuses to spend cash the account does not have;
- assumes the worse fill when a bar breaches both the stop and the target;
- closes open positions at the end so results are realised P&L, not paper gains.

It still cannot model order book depth, funding rates, exchange downtime, or
partial fills. Treat every result as an upper bound.

## Project layout

```
tradingbot/
  cli.py            command line entry point
  config.py         YAML config loading and validation
  models.py         Candle, Signal, Order, Position, Trade
  indicators.py     SMA, EMA, RSI, ATR, Bollinger, rolling extremes
  risk.py           position sizing and circuit breakers
  backtest.py       event-driven backtester
  engine.py         live/paper trading loop
  metrics.py        Sharpe, Sortino, drawdown, profit factor
  state.py          crash-safe state persistence
  notifier.py       log and webhook notifications
  strategies/       sma_cross, rsi_reversion, breakout
  exchange/         paper broker and ccxt adapter
  data/             OHLCV loading, CSV cache, synthetic generator
web/                CBot dashboard (static site)
tests/              151 tests
```

## Tests

```bash
pip install pytest && python -m pytest
```

They run offline in a few seconds. The suite covers indicator maths, risk limits
and circuit breakers, cash and fee accounting, look-ahead prevention, state
recovery after a crash, and the live-trading guards.

## Dashboard

A static dashboard lives in `web/`. Open `web/index.html` directly, or:

```bash
python -m http.server 8000 --directory web
```

It renders backtest results exported with `--json`, so you can look at an equity
curve and a trade list instead of a wall of terminal output:

```bash
python -m tradingbot.cli backtest -c config/config.yaml --json web/results.json
```

## License

MIT. No warranty — see the note at the top.
