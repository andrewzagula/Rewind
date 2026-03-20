export default function Home() {
  return (
    <div className="flex-1">
      <div className="mx-auto max-w-4xl px-6 py-20">
        <h1 className="text-5xl font-bold tracking-tight">Rewind</h1>
        <p className="mt-4 text-xl text-zinc-400">
          AI-native quant research &amp; backtesting platform
        </p>

        <div className="mt-16 grid gap-6 sm:grid-cols-2">
          <Card
            title="Strategies"
            description="Write and manage trading strategies in Python"
            href="/strategies"
          />
          <Card
            title="Runs"
            description="View backtest results, metrics, and equity curves"
            href="/runs"
          />
          <Card
            title="Compare"
            description="Side-by-side run comparison and analysis"
            href="/compare"
          />
          <Card
            title="Chat"
            description="AI assistant for strategy research and debugging"
            href="/chat"
          />
        </div>

        <div className="mt-20 rounded-lg border border-zinc-800 bg-zinc-900 p-6">
          <h2 className="text-lg font-semibold">Quick Start</h2>
          <pre className="mt-4 overflow-x-auto rounded bg-zinc-950 p-4 text-sm text-zinc-300">
{`# Clone and start
git clone <repo-url> rewind
cd rewind
cp .env.example .env
docker compose up

# Open http://localhost:3000`}
          </pre>
        </div>
      </div>
    </div>
  );
}

function Card({ title, description, href }: { title: string; description: string; href: string }) {
  return (
    <a
      href={href}
      className="group rounded-lg border border-zinc-800 bg-zinc-900 p-6 transition-colors hover:border-zinc-600 hover:bg-zinc-800"
    >
      <h3 className="text-lg font-semibold group-hover:text-white">{title}</h3>
      <p className="mt-2 text-sm text-zinc-400">{description}</p>
    </a>
  );
}
