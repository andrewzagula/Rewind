# Rewind

AI-native quant research environment for designing, testing, analyzing, and refining trading strategies with an AI assistant in the loop.

This README describes the intended end-state product for Rewind: the experience, workflows, and platform scope this repository is being built toward.

## The Product

Rewind is designed to make quantitative research feel like a fast, modern, conversational workflow instead of a collection of disconnected scripts and dashboards.

The core loop is:

**Design -> Test -> Analyze -> Refine -> Repeat**

In the finished product, a user can:

- Write or edit Python strategies in the browser with a dedicated strategy workspace
- Generate new strategies from natural-language prompts
- Run asynchronous backtests on versioned datasets
- Inspect rich run artifacts including metrics, equity curves, drawdowns, and trade logs
- Compare multiple runs side by side to understand changes in behavior
- Ask an AI research assistant to explain results, debug weak performance, and suggest improvements
- Apply those suggestions directly and launch the next run without leaving the app

## What Rewind Looks Like

### Dashboard

The home experience is a research dashboard, not a marketing shell. It surfaces:

- Recent runs
- Best-performing strategies
- Active experiments
- Dataset coverage
- Quick links back into the research workflow

### Strategy Workspace

Each strategy has a dedicated workspace with:

- A browser-based code editor
- Versioned strategy code and descriptions
- Parameter controls
- Run history
- Links to prior results and comparisons

This is the place where ideas become executable strategies and where iteration happens fastest.

### Run Analysis

Each backtest run resolves into a detailed analysis view with:

- Equity curve visualization
- Drawdown chart
- Trade markers overlaid on charts
- Full metrics table
- Paginated trade log
- Parameters and dataset metadata used for the run

Every run is meant to be reproducible. Results are not just snapshots; they are tracked experiments with enough context to understand exactly what happened.

### Comparison View

Rewind includes a dedicated comparison workflow for evaluating multiple runs at once:

- Side-by-side metrics
- Overlaid equity curves
- Run-to-run diffs
- Clear tradeoff analysis between parameter sets or strategy versions

The goal is to make experiment tracking a first-class feature rather than an afterthought.

### AI Research Assistant

The assistant is the defining feature of Rewind. It is context-aware and tied directly to the strategy and run data the user is looking at.

In the finished product, the assistant can:

- Generate valid strategy code from plain-English requests
- Explain why a run performed well or poorly using real metrics and trade data
- Diagnose weak Sharpe, drawdown, turnover, or win-rate behavior
- Suggest concrete code changes and parameter adjustments
- Compare runs in natural language
- Trigger new backtests from chat
- Maintain persistent research conversations linked to strategies and runs

Typical prompts look like:

- `Create a momentum strategy using 20-day returns on AAPL`
- `Why did this strategy underperform in Q1 2024?`
- `Compare this run against the last two versions`
- `Add a volatility filter and run it again`

## How It Works

Rewind is built as a multi-service research platform:

- `Frontend`: Next.js application for the dashboard, editor, analysis views, and chat UX
- `Backend API`: FastAPI service for strategies, runs, datasets, comparisons, and chat orchestration
- `Backtest Worker`: asynchronous execution layer for running strategies against historical data
- `LLM Service`: prompt orchestration, context assembly, streaming responses, and action generation
- `Data Layer`: Parquet and DuckDB for historical market data, PostgreSQL for metadata and artifacts, Redis for job dispatch and streaming support

At a high level, the workflow is:

1. A user creates or updates a strategy.
2. Rewind records the strategy version, parameters, and dataset selection.
3. A backtest job is queued and executed asynchronously.
4. Metrics, trades, and artifacts are stored and attached to the run.
5. The frontend renders analysis views and makes the full context available to the assistant.
6. The user keeps iterating until the strategy is worth keeping, improving, or discarding.

## Core Product Principles

- **AI-native**: the assistant is built into the research loop, not bolted on afterward
- **Reproducible**: runs capture strategy version, parameters, datasets, trades, and artifacts
- **Fast**: local-first backtesting and efficient data access keep iteration tight
- **Explainable**: users can see what happened and ask why it happened
- **Modern**: the interface is designed as a real product for research, not a thin UI over scripts

## Planned Platform Scope

The full vision for Rewind extends beyond a single backtest UI.

### Research Features

- Parameter sweeps and optimization runs
- Walk-forward and out-of-sample testing
- Slippage, commission, and market-impact modeling
- Multi-asset and portfolio-level simulation
- Multi-timeframe strategies

### AI Features

- Autonomous strategy refinement loops
- Paper-to-strategy generation from uploaded research
- Factor discovery workflows
- Multi-step agentic research tooling

### Platform Features

- User accounts and personal workspaces
- Shared strategies and run collaboration
- Cloud-executed backtests
- Strategy publishing and discovery
- Live paper-trading integrations

## Technology

| Layer | Planned Stack |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind, Plotly, Monaco |
| Backend API | FastAPI, Pydantic, SQLAlchemy |
| Backtest Engine | Python, NumPy, Polars |
| Data Access | DuckDB, PyArrow, Parquet |
| Metadata Store | PostgreSQL |
| Queue / Streaming Support | Redis, Arq |
| AI Layer | OpenAI API with structured prompting and streaming chat |

## Local Development

```bash
cp .env.example .env
docker compose up --build
```

Default local endpoints:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8000](http://localhost:8000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

To generate the sample dataset:

```bash
docker compose exec backend python scripts/seed_data.py
```

## License

MIT
