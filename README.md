# Rewind

Use Rewind locally to write Python trading strategies, run backtests against checked-in sample OHLCV data, and review completed run results.

Use it to:

- Create, edit, validate, and delete Python strategy records
- Run asynchronous backtests through a FastAPI API, Redis, and an Arq worker
- Simulate portfolio trades over local Parquet OHLCV files
- Review completed run metrics, equity curves, drawdowns, params, dataset provenance, and trades
- Compare two or more completed runs with metric deltas and overlaid equity curves
- Use OpenAI-backed chat for run and comparison context when `OPENAI_API_KEY` is configured
- Start from sample strategies and sample daily data for `AAPL`, `SPY`, `TSLA`, `MSFT`, and `GOOG`

Use Rewind for research and backtesting workflows. Trading decisions remain your responsibility.

## Stack

| Area | Stack |
| --- | --- |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, Recharts |
| API | FastAPI, Pydantic v2, SQLAlchemy 2 async |
| Worker | Arq, Redis, Python multiprocessing timeout isolation |
| Backtest engine | Python, pandas, NumPy |
| Data | Parquet files queried with DuckDB, PyArrow for sample-data generation |
| Metadata | PostgreSQL |
| AI chat | OpenAI API, streaming responses, backend-resolved prompt context |

## Repository Layout

```text
backend/      FastAPI app, database models, migrations, worker, API tests
engine/       Strategy interface, executor, portfolio, metrics, engine tests
frontend/     Next.js app and UI components
llm/          Prompt context, OpenAI client wrapper, response parsing
data/sample/  Checked-in sample OHLCV Parquet files
docs/         Local onboarding and strategy authoring guides
scripts/      Utility scripts for database and sample-data setup
```

## Quick Start

Prerequisites:

- Docker and Docker Compose
- An OpenAI API key only if you want chat responses

Start the stack:

```bash
cp .env.example .env
docker compose up --build
```

In another terminal, run the database migrations:

```bash
docker compose exec backend alembic -c migrations/alembic.ini upgrade head
```

Open:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:8000](http://localhost:8000)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Sample Parquet data is checked in under `data/sample`, and the migrations register those files as selectable datasets.

## Configuration

Copy `.env.example` to `.env` before starting the Docker stack:

```bash
cp .env.example .env
```

The default values are set up for `docker compose up --build`.

| Variable | Used by | Description | Default in `.env.example` |
| --- | --- | --- | --- |
| `DATABASE_URL` | Backend, worker, migrations | Async SQLAlchemy connection string for PostgreSQL. Use the `postgres` host inside Docker. | `postgresql+asyncpg://rewind:rewind@postgres:5432/rewind` |
| `REDIS_URL` | Backend, worker | Redis connection string for queued backtest jobs. Use the `redis` host inside Docker. | `redis://redis:6379/0` |
| `OPENAI_API_KEY` | Backend chat API | Enables streaming chat responses. Replace the placeholder with a real key, or set it to an empty value if you do not want chat. | `sk-your-key-here` |
| `API_URL` | Frontend | Backend URL used by Next.js rewrites for `/api/*` and `/health`. Docker Compose overrides this to `http://backend:8000` for the frontend service. | `http://localhost:8000` |
| `POSTGRES_USER` | Postgres container | Database username created by the Postgres service. | `rewind` |
| `POSTGRES_PASSWORD` | Postgres container | Database password created by the Postgres service. | `rewind` |
| `POSTGRES_DB` | Postgres container | Database name created by the Postgres service. | `rewind` |

The backend also supports `CORS_ORIGINS` through Pydantic settings. If unset, local frontend origins are allowed:

```text
http://localhost:3000
http://127.0.0.1:3000
```

For custom origins, set `CORS_ORIGINS` as a JSON list:

```env
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

## First Backtest

1. Open [http://localhost:3000/strategies/new](http://localhost:3000/strategies/new).
2. Choose a sample strategy.
3. Create the strategy.
4. Pick a registered sample dataset on the strategy detail page.
5. Click `Run Backtest`.
6. Open the completed run to review metrics, equity, drawdown, params, dataset provenance, and trades.

Runs use the selected dataset and default params unless the UI or API sends different params:

```json
{
  "symbol": "AAPL",
  "timeframe": "1d",
  "initial_cash": 100000
}
```

To compare completed runs, open [http://localhost:3000/compare](http://localhost:3000/compare) and select two or more runs.

## Chat

Chat is optional. Strategy creation, validation, backtesting, run review, and comparison work without OpenAI credentials.

To enable chat, set `OPENAI_API_KEY` in `.env` before starting the services:

```env
OPENAI_API_KEY=sk-...
```

Leave `OPENAI_API_KEY` blank if you do not want chat responses.

Chat requests use backend-resolved context for the selected run or comparison. The system prompt instructs the assistant to use provided metrics and artifacts instead of inventing missing data.

## Strategy Authoring

Strategies are Python classes that extend `engine.Strategy` and return `engine.Signal` objects when they want to trade.

Minimal example:

```python
from engine import Signal, Strategy


class MyStrategy(Strategy):
    def init(self, params):
        self.quantity = float(params.get("quantity", 10))

    def next(self, row, portfolio):
        if row["close"] > row["open"]:
            return Signal(
                symbol=row["symbol"],
                side="buy",
                quantity=self.quantity,
                reason="Close finished above open",
            )
        return None
```

Strategy code is checked by AST validation rules before it is saved or queued for a run. It must define exactly one `Strategy` subclass with `init()` and `next()`, and the validator blocks selected filesystem, process, network, dynamic import, builtin, and dunder access patterns. Execution also runs in a worker subprocess with a timeout.

Run strategy code you trust.

See [docs/strategy-authoring.md](docs/strategy-authoring.md) for the current interface, allowed imports, signal shape, params, and common validation errors.

## Development

Useful commands:

```bash
# Start all services
docker compose up --build

# Run database migrations
docker compose exec backend alembic -c migrations/alembic.ini upgrade head

# Run Python tests in the backend container
docker compose exec backend pytest tests engine/tests llm/tests

# Lint the frontend
docker compose exec frontend pnpm lint

# Build the frontend
docker compose exec frontend pnpm build
```

For a guided local walkthrough, see [docs/local-onboarding.md](docs/local-onboarding.md).

## API Surface

Primary endpoints:

- `GET /health`
- `POST /api/v1/strategies`
- `GET /api/v1/strategies`
- `GET /api/v1/strategies/{strategy_id}`
- `PATCH /api/v1/strategies/{strategy_id}`
- `DELETE /api/v1/strategies/{strategy_id}`
- `POST /api/v1/runs`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{run_id}`
- `GET /api/v1/runs/{run_id}/trades`
- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{dataset_id}`
- `GET /api/v1/compare?run_ids=<uuid>,<uuid>`
- `POST /api/v1/chat`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/sessions/{session_id}`
- `DELETE /api/v1/chat/sessions/{session_id}`
- `POST /api/v1/chat/messages/{message_id}/actions/{action_id}`

FastAPI serves interactive API documentation at [http://localhost:8000/docs](http://localhost:8000/docs).

## Contributing

Keep changes focused on the current app, engine, backend, frontend, LLM, docs, or test surfaces. Before opening a pull request, run the relevant tests and linters for the area you changed.

## License

MIT
