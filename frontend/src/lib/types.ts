export interface Strategy {
  id: string;
  name: string;
  description: string;
  code: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

export interface Run {
  id: string;
  strategy_id: string;
  params: Record<string, unknown>;
  metrics: RunMetrics;
  artifacts: Record<string, unknown>;
  status: "pending" | "running" | "completed" | "failed";
  error?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
}

export interface RunMetrics {
  total_return: number;
  annualized_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  calmar_ratio: number;
  volatility_annual: number;
  total_trades: number;
  win_rate: number;
  profit_factor: number;
  avg_trade_pnl: number;
  avg_win: number;
  avg_loss: number;
}

export interface CompareEquityPoint {
  index: number;
  timestamp: string;
  value: number;
}

export interface ComparedRun {
  id: string;
  strategy_id: string;
  status: Run["status"];
  params: Record<string, unknown>;
  metrics: Partial<RunMetrics> & Record<string, unknown>;
  error?: string | null;
  created_at: string;
  completed_at?: string | null;
  equity_points: CompareEquityPoint[];
}

export interface MetricDelta {
  key: string;
  base: number | null;
  values: Array<number | null>;
  deltas: Array<number | null>;
}

export interface CompareResponse {
  runs: ComparedRun[];
  metric_deltas: MetricDelta[];
}

export interface Trade {
  id: string;
  run_id: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  timestamp: string;
  pnl: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  linked_run_id?: string;
  created_at: string;
}

export interface ChatSession {
  id: string;
  context: Record<string, unknown>;
  messages: ChatMessage[];
  created_at: string;
}

export interface Dataset {
  id: string;
  name: string;
  symbols: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  row_count: number;
  created_at: string;
}
