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

## 2. Fetch Real Market Data

The worker reads local Parquet files. Fetch real daily history for the starter tickers from free providers (no API key):

```bash
docker compose exec backend python scripts/fetch_market_data.py AAPL SPY TSLA MSFT GOOG
```

Each file lands in `data/market` as `AAPL_1d.parquet` and is registered as a dataset with source `stooq` or `yahoo`. You can also add tickers on the Datasets page at [http://localhost:3000/datasets](http://localhost:3000/datasets), or ask the chat assistant to fetch them.

The repository also ships synthetic sample files under `data/sample`, registered with source `synthetic`. They are random walks for smoke-testing only; the UI labels them and prefers real datasets when picking a default.

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

1. On the strategy detail page, use the dataset selector to choose a registered dataset. A real AAPL daily dataset is selected by default when available; synthetic datasets are labeled.
2. Click `Run Backtest`.
3. Rewind creates a pending run and navigates to the run detail page.
4. The worker executes the run against params derived from the selected dataset:

```json
{
  "symbol": "AAPL",
  "timeframe": "1d",
  "initial_cash": 100000
}
```

5. Refresh the run detail page after the worker completes if the status has not updated yet.

A completed run shows metrics, equity, drawdown, params, dataset provenance, and trades. A failed run shows the worker or validation error.

## 5. Compare Runs

To compare strategy variants:

1. Create at least two completed runs.
2. Open [http://localhost:3000/compare](http://localhost:3000/compare).
3. Select two or more runs.
4. Review metric deltas and overlaid equity curves.

The first selected run is the baseline for deltas.

## 6. Let Chat Do The Work

If `OPENAI_API_KEY` is configured, open [http://localhost:3000/chat](http://localhost:3000/chat). The assistant can operate the app itself, and each tool call appears in the conversation as it runs. Try:

```text
Backtest a 20/50 SMA crossover on NVDA over the last five years and tell me how it did.
```

The assistant writes the strategy, fetches NVDA data if no real dataset exists, runs the backtest, waits for the result, and summarizes the metrics with links to the run.

```text
How did my last three runs compare?
```

It lists the runs, compares them, and explains the deltas.

Opening chat from a run or compare page also passes that run or comparison as context, so questions like "Why did this run perform this way?" work without naming ids. The only thing the assistant will not do on its own is delete a strategy; it proposes that as an action you confirm.

## 7. Write Your Own Strategy

Use [Strategy Authoring Guide](./strategy-authoring.md) for the current strategy interface, allowed imports, params, signals, and common failure messages.
