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

Prefer a browser? `python -m tradingbot.cli serve` opens the same thing as a
[dashboard](#dashboard).

## Real data

```bash
cp config/config.example.yaml config/config.yaml

# Download and cache a year of hourly candles from the configured exchange
python -m tradingbot.cli fetch -c config/config.yaml --days 365

# Or, with no API key and no ccxt — works where exchanges are geo-blocked
python -m tradingbot.cli fetch --source coingecko -s BTC/USD --days 90

# Backtest against it
python -m tradingbot.cli backtest -c config/config.yaml
```

The CoinGecko source returns **closing prices only**, so bars carry no true
intrabar high or low. Stops and targets are evaluated against the close and
trigger less often than they would live, which flatters stop-heavy strategies.
Use it to get moving; confirm anything promising on exchange data.

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
python -m tradingbot.cli preflight -c config/config.yaml   # check first
python -m tradingbot.cli live -c config/config.yaml --i-understand-the-risk
```

### CBot uses exchange API keys, not a wallet

This is the part people get wrong, so it is worth being blunt about.

CBot trades on **centralized exchanges** — Binance, Kraken, Coinbase, Bybit and
the rest — through their trading APIs. It does **not** connect a self-custody
wallet, does not trade on DEXs, and has no code path that touches a private key
or seed phrase.

**Never give your seed phrase or private key to any trading bot, including this
one.** A seed phrase grants permanent, total control of every asset in that
wallet, and no bot needs it. Anything that asks for one can empty the wallet, and
that is usually the point. `preflight` fails loudly if a seed phrase is pasted
where an API key belongs.

What CBot needs instead is an exchange API key, which is revocable, permission-
scoped, and cannot move funds off the exchange when created correctly.

### Connecting an exchange account

1. **Fund an exchange account** with the quote currency you configured (USDT for
   `BTC/USDT`). The bot trades the balance sitting on the exchange.
2. **Create an API key** in that exchange's security settings with:
   - **Enable Spot Trading** — on. This is all the bot needs.
   - **Enable Withdrawals** — **off**. Never on. This is what stops a leaked key
     becoming a drained account.
   - **IP allowlist** — set it to the machine that will run the bot. Most venues
     support this and it is the single most effective protection available.
3. **Put the key in your environment**, never in the config file:
   ```bash
   cp .env.example .env      # then edit it
   set -a && source .env && set +a
   ```
   `.env` is gitignored. The config file only stores the *names* of these
   variables, so it stays safe to share.
4. **Point the config at the venue** and start on its testnet:
   ```yaml
   exchange:
     name: binance
     testnet: true       # real funds only after this has run clean
   execution:
     mode: live
     confirm_live: true
   ```
5. **Run preflight.** It checks the key works, the balance is readable and large
   enough to clear the venue's minimum order size, and the symbols are actually
   tradable there — all without placing an order:
   ```bash
   python -m tradingbot.cli preflight -c config/config.yaml
   ```
6. **Trade the testnet for a few weeks.** Not hours. You are looking for whether
   it behaves as the backtest suggested, and how it handles restarts and
   disconnects.
7. **Go live small.** Flip `testnet: false` and fund the account with an amount
   whose total loss would not change your life. First live size should feel
   almost pointless.

### Once it is live

- `python -m tradingbot.cli status -c config/config.yaml` shows open positions and
  risk counters. The dashboard shows the same thing.
- Ctrl-C stops cleanly at the end of a cycle. **It does not close open positions**
   — close those yourself, on the exchange, if you want to be flat.
- If a circuit breaker trips, the bot flattens and halts, and stays halted across
  restarts. That is deliberate: work out what happened before restarting it.
- Revoke the API key on the exchange if anything looks wrong. That is the kill
  switch, and it works even if the machine running the bot does not respond.

Realistically: the bundled strategies are textbook examples, not edges. Expect a
live run to lose money net of fees. Treat the first live deployment as a test of
the plumbing, not of the strategy.

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
  preflight.py      live-setup checks that place no orders
  config.py         YAML config loading and validation
  models.py         Candle, Signal, Order, Position, Trade
  indicators.py     SMA, EMA, RSI, ATR, Bollinger, rolling extremes
  risk.py           position sizing and circuit breakers
  backtest.py       event-driven backtester
  engine.py         live/paper trading loop
  metrics.py        Sharpe, Sortino, drawdown, profit factor, buy-and-hold
  validation.py     walk-forward, bootstrap, random baseline, cost sweeps
  execution.py      fee tiers, maker vs taker economics
  regime.py         regime detection and strategy gating
  carry/            perpetual funding carry: sources, scanner, scoring
  state.py          crash-safe state persistence
  notifier.py       log and webhook notifications
  strategies/       sma_cross, rsi_reversion, breakout
  exchange/         paper broker and ccxt adapter
  data/             OHLCV loading, CSV cache, CoinGecko, synthetic generator
  research/         token contract due diligence (chain sources + heuristics)
  web/              site backend: HTTP server, API handlers, background jobs
web/                site frontend: router, views, charts (no build step)
tests/              464 tests
```

## Tests

```bash
pip install pytest && python -m pytest
```

They run offline in a few seconds — no API keys, no network. The suite covers
indicator maths, risk limits and circuit breakers, cash and fee accounting,
look-ahead prevention, state recovery after a crash, the live-trading guards, the
contract heuristics, and the dashboard API — including tests asserting the web
layer has no path to submitting an order and that the research report never
claims to know who a team is.



## Does the strategy actually work?

A single backtest number is close to worthless: it is one path, on data the
parameters were probably fitted to, with no comparison to doing nothing. Two
commands exist to attack a result rather than present it.

### validate — is this luck?

```bash
python -m tradingbot.cli validate -c config/config.yaml
```

Four checks, each of which most strategies fail:

| Check | What it catches |
|---|---|
| **vs buy and hold** | +3% while the asset did +40% is value destroyed. Every backtest now reports this. |
| **Bootstrap confidence interval** | Resamples the trade sequence. If the 90% interval spans zero, the headline number is noise. |
| **vs random entries** | A random trader with the same trade count and holding period. If they match you, your logic is not what made the money — market exposure was. |
| **Cost sensitivity** | Sweeps the fee rate to find where the edge dies. A strategy that only works below your actual fee tier is not tradable. |

It prints a verdict, and "0 of 4 passed" is the normal result:

```
  Verdict: 0 of 4 checks passed
     [FAIL] beats buy and hold
     [FAIL] statistically positive
     [FAIL] beats random entries
     [FAIL] survives realistic fees
```

### walkforward — does it survive unseen data?

`optimize` grid-searches and hands you the best row, which is the definition of
overfitting. `walkforward` is the honest version: tune on one window, test on the
**next unseen** window, roll forward, and report only the out-of-sample result.

```bash
python -m tradingbot.cli walkforward -c config/config.yaml \
    --grid fast_period=10,20 --grid slow_period=30,50 --train 1200 --test 400
```

```
  In-sample mean            2.16%
  Out-of-sample mean       -0.03%
  Degradation              -0.01    (1.0 = held up, <=0 = fitted noise)
  Profitable windows           4 of 9
```

That is what overfitting looks like: every window profitable in training, nothing
left once the data is unseen. It also reports **parameter stability** — a
parameter the optimiser rechooses every window is being fitted to noise.

### What this buys you

Not a profitable strategy. It buys you the ability to tell the difference between
one that works and one that got lucky — and to find out on your laptop instead of
on an exchange. Most strategies fail these checks. That is the tooling working.


## Looking for an actual edge

Price-prediction strategies on liquid crypto do not work — the search below is
the evidence, not an opinion. These three tools exist because the interesting
question is not "which moving average" but "where does a real edge live".

### The search that motivated all of this

197 parameter configurations across all three strategies, run on **real hourly
data** for BTC, ETH, SOL and LINK:

```
Buy and hold:  BTC +6.12%   ETH +22.58%   SOL +29.21%   LINK +26.42%

Configs beating buy-and-hold on all four assets:   0
Configs with a positive mean excess return:        0 / 197
Best performer:                                    -16.96% vs holding
```

Not one. This is the expected result, and it is why the tools below focus on
costs, regime and carry rather than on inventing a fourth crossover.

### carry — a structural edge, not a forecast

A perpetual swap has no expiry, so exchanges use a **funding payment** to tether
it to spot. Hold long spot and short perp in equal size and you are flat on
price while collecting that funding. It pays you for providing balance sheet
rather than for predicting anything, which is why it is measurable in advance.

```bash
python -m tradingbot.cli carry --venue binance --maker
python -m tradingbot.cli carry --symbols "BTC/USDT:USDT" "ETH/USDT:USDT" --json carry.json
```

The scanner is deliberately pessimistic. It ranks by carry **net of fees**,
prefers the historical mean over the current print, and refuses to call anything
viable that trips one of these:

| Check | Why |
|---|---|
| Net of round-trip costs | 1bp funding looks like 11% APR and takes **16 days** just to pay for entering |
| Breakeven inside your holding period | Set with `--max-breakeven-days` (default 5). At maker fees, 3bp funding is ~33% APR and breaks even in 3.2 days; 0.5bp takes 19 days and is rejected |
| Funding positive ≥70% of intervals | A high average driven by a few spikes is not bankable |
| Volatility below its own mean | If funding swings more than it averages, the carry is unreliable |
| No spot borrow required | Negative funding means shorting spot, which most retail accounts cannot do cheaply |

**Carry is not free money.** Funding can flip while you hold. The perp leg can be
liquidated in a fast move if margin is thin. And the whole position depends on the
venue staying solvent — the trade that pays 15% a year loses 100% if the exchange
does an FTX.

### execution — the thing that was actually killing you

`validate` kept returning the same verdict: profitable at zero fees, unprofitable
at real ones. That is an execution problem, and it has a real fix.

```bash
python -m tradingbot.cli execution
```

```
  binance USD-M futures VIP0
    mode        fill rate   eff. fee   round trip   breakeven move
    taker           100%    0.0500%      0.1400%           0.140%
    maker            90%    0.0230%      0.0500%           0.050%
```

The last column is the gross move a trade must capture just to break even. **A
strategy whose average winner is smaller than that number cannot be profitable,
however often it is right.** On Coinbase taker fees it is 1.64%; on perp maker
fees it is 0.04% — a 40x difference in the edge you need.

Set it in config and every backtest uses your real costs:

```yaml
execution:
  fee_tier: binance_perp    # binance, binance_bnb, bybit_perp, okx_perp, coinbase, kraken
  prefer_maker: true
  maker_fill_rate: 0.8      # honest: orders that do not fill are trades you did not make
```

### regime — knowing when your premise does not hold

Trend following needs price to travel; mean reversion needs it to oscillate. Run
either in the wrong regime and it bleeds fees on false starts.

```bash
python -m tradingbot.cli regime -c config/config.yaml
```

```
  BTC/USD 1h — 2160 bars
    choppy         64%  #########################
    quiet          16%  ######
    trending       14%  #####
    volatile        7%  ##
```

Hourly crypto trends about 20% of the time. A crossover strategy has a premise for
one bar in five and pays fees for the other four — which is most of the answer to
why the search above found nothing.

`RegimeGatedStrategy` wraps any strategy so it only *enters* when the regime suits
it. Exits are never gated: a position opened in one regime must stay closable in
another.

**Tested honestly, gating did not rescue the bundled strategies** — it cut 90
trades to 13 and made the result slightly worse, because over a rising 90-day
window anything that reduces exposure loses to holding. The tool is sound; the
premise it was gating was not.

## Contract research

Before you trade a token, check what its contract can actually do:

```bash
export ETHERSCAN_API_KEY=your_key   # free, one key covers every chain
python -m tradingbot.cli research 0xdAC17F958D2ee523a2206206994597C13D831ec7
python -m tradingbot.cli research 0x... --chain bsc --json report.json
```

Supported chains: ethereum, bsc, base, polygon, arbitrum, optimism, avalanche.
The same review is available in the dashboard's **Contract research** tab.

It reports **capabilities and who holds them**, with the evidence for each:

| Check | Why it matters |
|---|---|
| Source verified | Unverified source means nobody can review it. Treated as critical. |
| Mint function | Supply can be inflated and sold into your liquidity. |
| Blacklist / bot blocking | Your ability to sell can be revoked after you buy — a honeypot. |
| Pausable transfers | Trading can be frozen. |
| Fee setters | Trade fees can be raised, potentially to the point of blocking sells. |
| Upgradeable proxy | Today's audited code can be replaced tomorrow. |
| Ownership renounced | Whether those powers are still reachable at all. |
| Contract and deployer age | Most rug pulls happen within days of deployment. |
| Deployer's other contracts | The closest thing on-chain to a track record. |

Findings escalate when powers combine: a mint function is *high*; a mint function
plus a live owner is *critical*, because that is the rug pull rather than the
capability. Every finding cites the source line or RPC result behind it, so you
can check the tool rather than trust it.

### On "are the developers doxxed"

**No on-chain tool can answer that, and this one does not pretend to.** Identity
is off-chain; any tool showing a confident doxxed/anonymous badge is guessing.

What *is* verifiable, and what CBot reports:

- the deployer's address, and when it first transacted
- **every other contract that address has deployed** — the past-projects question,
  answered from chain data
- which address funded it
- direct links to continue: the explorer, holders, market data, and a honeypot check

A deployer with a history of abandoned tokens is the most useful signal available
on-chain. A brand-new address with no history is not proof of anything — it is
just an absence of evidence, and the report says so in those terms.

This tool describes what a contract *can* do. It cannot tell you what anyone
*intends* to do, and it is not financial advice.

## The web app

Everything above has a browser front end:

```bash
python -m tradingbot.cli serve -c config/config.yaml
# CBot: http://127.0.0.1:8000
```

Standard library only — no build step, no bundler, no dependencies. It binds to
localhost by default; `--host 0.0.0.0` exposes it to your network, and it has no
authentication, so only do that on a network you trust.

| Page | What it does |
|---|---|
| **Overview** | Mode, open positions, cached data, and where to start |
| **Backtest** | Run a strategy, always charted against buy and hold, with a hoverable equity curve and the full trade list |
| **Validate** | The four checks, with a bootstrap interval, a random-entry comparison and a fee-sensitivity curve |
| **Walk-forward** | Build a parameter grid, watch windows run, see in-sample versus out-of-sample and parameter stability |
| **Regime** | Time spent in each regime, and price coloured by regime |
| **Funding carry** | Scan perpetual funding, ranked net of your fee tier |
| **Execution costs** | Every fee tier and the move a trade must capture to break even |
| **Contract review** | The full due-diligence report with evidence per finding |
| **Bot status** | Open positions and risk counters from saved state |
| **Data** | What history is cached, and how to fetch more |
| **Jobs** | Long-running analysis, with progress and cancellation |

**Background jobs.** Validation, walk-forward and carry scans take minutes, so
they run on a worker thread and the page polls for progress rather than holding a
request open until the browser gives up. Jobs report real progress, can be
cancelled mid-run, and live in the server's memory — they die with it, which is
correct for something you started from a terminal.

**The site cannot place orders.** It runs analysis and reads saved state, nothing
more. There is no order path in the web layer at all, and tests assert it — both
that no Python module in `tradingbot/web/` references a broker or an order, and
that no front-end file even names an order endpoint. Live trading stays on the
command line where the confirmation locks are.


## License

MIT. No warranty — see the note at the top.
