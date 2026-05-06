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
  dataset_id?: string | null;
  dataset_version: string;
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

export type ChatRole = "user" | "assistant" | "system";

export type ChatContext =
  | { type: "run"; run_id: string }
  | { type: "compare"; run_ids: string[] };

export interface GeneratedStrategyMetadata {
  code: string;
  valid: boolean;
  class_name?: string | null;
  errors: string[];
}

export interface GeneratedStrategyDraft {
  code: string;
  className: string | null;
  sourceMessageId: string;
  createdAt: string;
}

export type ChatActionType =
  | "apply_code"
  | "run_backtest"
  | "compare_runs"
  | "create_strategy_and_run";
export type ChatActionStatus = "proposed" | "completed" | "failed" | "cancelled";
export type ChatActionAuditStatus = Exclude<ChatActionStatus, "proposed">;

export interface ApplyCodeActionPayload {
  strategy_id: string;
  code: string;
  class_name?: string | null;
}

export interface RunBacktestActionPayload {
  strategy_id: string;
  params: Record<string, unknown>;
}

export interface CompareRunsActionPayload {
  run_ids: string[];
}

export interface CreateStrategyAndRunActionPayload {
  name: string;
  description: string;
  code: string;
  class_name?: string | null;
  params: Record<string, unknown>;
}

export type ChatActionPayload =
  | ApplyCodeActionPayload
  | RunBacktestActionPayload
  | CompareRunsActionPayload
  | CreateStrategyAndRunActionPayload;

export interface ChatAction {
  id: string;
  type: ChatActionType;
  label: string;
  status: ChatActionStatus;
  payload: ChatActionPayload;
  result?: Record<string, unknown>;
  error?: string;
  created_at?: string;
  completed_at?: string;
}

export interface ChatActionAuditRequest {
  status: ChatActionAuditStatus;
  result?: Record<string, unknown>;
  error?: string;
}

export type ChatMessageMetadata = Record<string, unknown> & {
  generated_strategy?: GeneratedStrategyMetadata;
  assistant_actions?: ChatAction[];
  assistant_action_errors?: string[];
};

export interface ChatMessage {
  id: string;
  session_id: string;
  role: ChatRole;
  content: string;
  linked_run_id?: string | null;
  metadata: ChatMessageMetadata;
  ordering: number;
  created_at: string;
}

export interface ChatSessionSummary {
  id: string;
  context: ChatContext | Record<string, unknown>;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_at?: string | null;
}

export interface ChatSession extends ChatSessionSummary {
  messages: ChatMessage[];
}

export interface ChatRequest {
  session_id?: string | null;
  message: string;
  context?: ChatContext;
}

export type ChatStreamEvent =
  | { type: "session"; session: ChatSessionSummary; message?: null; content: ""; error: "" }
  | { type: "chunk"; session?: null; message?: null; content: string; error: "" }
  | { type: "done"; session?: null; message: ChatMessage; content: ""; error: "" }
  | { type: "error"; session?: null; message?: null; content: ""; error: string };

export interface ChatSessionListResponse {
  items: ChatSessionSummary[];
  total: number;
}

export interface Dataset {
  id: string;
  name: string;
  symbols: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  row_count: number;
  file_path: string;
  checksum: string;
  created_at: string;
}
