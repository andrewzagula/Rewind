# Rewind

AI-native quant research & backtesting platform.

Design, test, analyze, and refine trading strategies — with an AI assistant in the loop.

## What is Rewind?

Rewind combines fast backtesting with an integrated LLM assistant that helps you generate, debug, and improve trading strategies through natural conversation.

- **Write strategies in Python** — simple `Strategy` base class with `init()` and `next()`
- **Run backtests** — vectorized engine powered by NumPy, with DuckDB + Parquet for data
- **Visualize results** — equity curves, drawdowns, trade logs, and run comparisons
- **Chat with AI** — ask it to generate strategies, explain results, debug performance, or run backtests from natural language

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
- An [OpenAI API key](https://platform.openai.com/api-keys) (for the chat assistant)

### Run

```bash
git clone https://github.com/your-username/rewind.git
cd rewind
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

docker compose up --build
```

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

### Generate Sample Data

```bash
docker compose exec backend python scripts/seed_data.py
```

This creates synthetic daily OHLCV data for AAPL, SPY, TSLA, MSFT, and GOOG (2020–2024).

## Writing a Strategy

Strategies extend the `Strategy` base class:

```python
from engine import Strategy, Signal

class SMACrossover(Strategy):
    def init(self, params):
        self.fast = params.get("fast_period", 10)
        self.slow = params.get("slow_period", 30)

    def next(self, row, portfolio):
        if row["sma_fast"] > row["sma_slow"]:
            if not portfolio.position_symbols:
                return Signal(symbol=row["symbol"], side="buy", quantity=100)
        elif row["sma_fast"] < row["sma_slow"]:
            if portfolio.position_symbols:
                return Signal(symbol=row["symbol"], side="sell", quantity=100)
        return None
```

Or just describe what you want in the chat:

> "Create a momentum strategy using 20-day returns on AAPL"

The AI assistant generates the code, and you can run it with one click.

## Architecture

```
Frontend (Next.js)  →  Backend API (FastAPI)  →  Backtest Worker (Python)
                              ↕                         ↕
                        LLM Service             DuckDB / Parquet
                       (OpenAI API)                    ↕
                              ↕                   PostgreSQL
                            Redis
```

| Service | Tech | Port |
|---|---|---|
| Frontend | Next.js, TypeScript, Tailwind, Plotly | 3000 |
| Backend | FastAPI, Pydantic, SQLAlchemy | 8000 |
| Engine | NumPy, Polars, DuckDB | — |
| LLM | OpenAI API | — |
| Database | PostgreSQL 16 | 5432 |
| Cache/Queue | Redis 7 | 6379 |

## Project Structure

```
rewind/
├── backend/          # FastAPI API server
│   ├── app/
│   │   ├── api/v1/   # Route handlers
│   │   ├── core/     # Config, database, dependencies
│   │   ├── models/   # SQLAlchemy ORM models
│   │   ├── schemas/  # Pydantic request/response schemas
│   │   └── services/ # Business logic
│   └── tests/
├── engine/           # Backtest engine (core logic)
│   ├── strategy.py   # Base Strategy class
│   ├── executor.py   # Backtest loop
│   ├── portfolio.py  # Portfolio state
│   ├── metrics.py    # Performance calculations
│   └── tests/
├── llm/              # LLM chat service
│   ├── client.py     # OpenAI wrapper
│   ├── context.py    # Context builder
│   ├── prompts/      # Prompt templates
│   └── tests/
├── frontend/         # Next.js frontend
│   └── src/
├── data/             # Historical data (Parquet)
└── scripts/          # Dev utilities
```

## Development

### Backend (without Docker)

```bash
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
uvicorn app.main:app --reload
```

### Frontend (without Docker)

```bash
cd frontend
pnpm install
pnpm dev
```

### Tests

```bash
# Engine tests (no external dependencies)
cd engine && python -m pytest tests/

# Backend tests
cd backend && python -m pytest tests/
```

## API

The backend auto-generates OpenAPI docs at `/docs` when running.

Key endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/run` | Submit a backtest |
| `GET` | `/api/v1/runs` | List runs |
| `GET` | `/api/v1/runs/{id}` | Get run results |
| `POST` | `/api/v1/strategies` | Create strategy |
| `POST` | `/api/v1/chat` | Send chat message (streaming) |
| `GET` | `/health` | Health check |

## Chat Assistant

The chat assistant can:

- **Generate strategies** — "Create a mean reversion strategy using Bollinger Bands"
- **Explain results** — "Why did this strategy lose money in Q1 2024?"
- **Debug** — "Why is the Sharpe ratio so low?"
- **Compare runs** — "Compare run A vs run B"
- **Run backtests** — "Test RSI < 30 on AAPL daily data"

## Roadmap

- [x] Project scaffolding
- [ ] Backtest engine with sample data
- [ ] Core API endpoints
- [ ] Visualization dashboard
- [ ] Experiment tracking & run comparison
- [ ] LLM chat integration
- [ ] Strategy sandboxing
- [ ] Production hardening

See [REWIND.md](REWIND.md) for the full project reference document with detailed phase breakdowns.

## Contributing

Contributions welcome. Please read [REWIND.md](REWIND.md) for architecture decisions and coding conventions before submitting a PR.

## License

MIT
