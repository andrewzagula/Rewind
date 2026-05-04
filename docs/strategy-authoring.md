# Strategy Authoring Guide

Rewind strategies are small Python classes that implement the current engine interface. The backend validates strategy code before saving, validates it again before queueing a run, and the worker validates it before execution.

## Minimal Shape

```python
from engine import Strategy, Signal


class MyStrategy(Strategy):
    def init(self, params):
        self.quantity = float(params.get("quantity", 10))

    def next(self, row, portfolio):
        return None
```

Rules:

- Define exactly one class that extends `Strategy`.
- Define both `init(self, params)` and `next(self, row, portfolio)`.
- Import only from the engine interface: `from engine import Strategy, Signal`.
- Return a `Signal` when you want to trade, otherwise return `None`.
- Use `params.get(...)` defaults so the strategy still works when a run uses `{}` params.

## `init(params)`

`init()` runs once before the backtest loop. Use it to read params and initialize state:

```python
def init(self, params):
    self.window = max(1, int(params.get("window", 20)))
    self.quantity = float(params.get("quantity", 10))
    self.closes = []
```

Keep expensive work out of `init()`. Strategy execution has a worker timeout, and long-running setup will fail the run.

## `next(row, portfolio)`

`next()` runs once for each bar. `row` is a dictionary with current sample data fields:

- `symbol`
- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

The `portfolio` object exposes:

- `portfolio.position_symbols` for symbols with non-zero positions.
- `portfolio.get_position(symbol)` to inspect the current position.

Example:

```python
def next(self, row, portfolio):
    symbol = row["symbol"]
    close = float(row["close"])
    self.closes.append(close)

    if len(self.closes) < self.window:
        return None

    average = sum(self.closes[-self.window:]) / self.window
    position = portfolio.get_position(symbol)

    if close > average and position.quantity <= 0:
        return Signal(symbol=symbol, side="buy", quantity=self.quantity)

    if close < average and position.quantity > 0:
        return Signal(symbol=symbol, side="sell", quantity=position.quantity)

    return None
```

## Signals

Use `Signal` to request a trade:

```python
Signal(
    symbol=row["symbol"],
    side="buy",
    quantity=10,
    reason="Close moved above moving average",
)
```

Fields:

- `symbol`: normally `row["symbol"]`.
- `side`: `"buy"` or `"sell"`.
- `quantity`: positive number.
- `reason`: optional text stored with the trade artifact.

For exits, sell the current position size to avoid accidentally shorting:

```python
position = portfolio.get_position(row["symbol"])
if position.quantity > 0:
    return Signal(symbol=row["symbol"], side="sell", quantity=position.quantity)
```

## Validation And Runtime Failures

Common validation errors:

- `Expected exactly one class that extends Strategy.` Add one `Strategy` subclass and remove extra strategy classes.
- `MyStrategy must define init().` Add `init(self, params)`.
- `MyStrategy must define next().` Add `next(self, row, portfolio)`.
- `Importing 'os' is not allowed in strategy code.` Remove filesystem, network, process, and dynamic import usage.
- `Calling 'open' is not allowed in strategy code.` Strategy code cannot read local files or make external calls.

Common runtime failures:

- Missing row key: use only the row fields listed above.
- Bad param type: cast params with `int(...)` or `float(...)` and provide defaults.
- Timeout: avoid unbounded loops and expensive calculations in `init()` or `next()`.
- No trades: confirm your conditions can trigger on the selected symbol and timeframe.

The sample strategies in `/strategies/new` are the best starting point for the current interface.
