# Local Onboarding

This guide takes a new local user from a fresh checkout to a completed backtest and chat analysis.

## 1. Start The App

From the repository root:

```bash
cp .env.example .env
docker compose up --build
```

Default endpoints:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8000](http://localhost:8000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

If you want chat responses from OpenAI, set `OPENAI_API_KEY` in `.env` before starting the stack. The core strategy and backtest workflow works without it.

## 2. Seed Sample Data

The worker reads local Parquet files from `data/sample`. The repository usually includes sample files for `AAPL`, `SPY`, `TSLA`, `MSFT`, and `GOOG`. Regenerate them with:

```bash
docker compose exec backend python scripts/seed_data.py
```

Each generated file is daily OHLCV data named like `AAPL_1d.parquet`.

## 3. Create A Sample Strategy

1. Open [http://localhost:3000/strategies/new](http://localhost:3000/strategies/new).
2. Select one of the sample strategies:
   - `BuyAndHoldStrategy`
   - `SMACrossoverStrategy`
   - `RSIMeanReversionStrategy`
   - `MomentumStrategy`
3. Review the populated name, description, and code.
4. Click `Create Strategy`.

The backend validates strategy code before saving. If validation fails, the editor shows the API error.

## 4. Run A Backtest

1. On the strategy detail page, click `Run Backtest`.
2. Rewind creates a pending run and navigates to the run detail page.
3. The worker executes the run against default params:

```json
{
  "symbol": "AAPL",
  "timeframe": "1d",
  "initial_cash": 100000
}
```

4. Refresh the run detail page after the worker completes if the status has not updated yet.

A completed run shows metrics, equity, drawdown, params, and trades. A failed run shows the worker or validation error.

## 5. Compare Runs

To compare strategy variants:

1. Create at least two completed runs.
2. Open [http://localhost:3000/compare](http://localhost:3000/compare).
3. Select two or more runs.
4. Review metric deltas and overlaid equity curves.

The first selected run is the baseline for deltas.

## 6. Ask Chat About Results

If `OPENAI_API_KEY` is configured:

1. Open a completed run detail page.
2. Use the chat link or open [http://localhost:3000/chat](http://localhost:3000/chat).
3. Ask questions such as:

```text
Why did this run perform this way?
```

For comparisons, open chat from the compare page and ask:

```text
Which run had the better risk-adjusted performance?
```

Chat uses backend-resolved run or comparison context. It should reference actual metrics and limitations instead of inventing missing data.

## 7. Write Your Own Strategy

Use [Strategy Authoring Guide](./strategy-authoring.md) for the current strategy interface, allowed imports, params, signals, and common failure messages.
