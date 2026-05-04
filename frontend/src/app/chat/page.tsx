"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { apiEventStream, apiFetch } from "@/lib/api";
import type {
  ApplyCodeActionPayload,
  ChatAction,
  ChatActionAuditRequest,
  ChatContext,
  CompareRunsActionPayload,
  CreateStrategyAndRunActionPayload,
  GeneratedStrategyDraft,
  GeneratedStrategyMetadata,
  ChatMessage,
  ChatRequest,
  ChatSession,
  ChatSessionListResponse,
  ChatSessionSummary,
  ChatStreamEvent,
  Run,
  RunBacktestActionPayload,
  Strategy,
} from "@/lib/types";

const GENERATED_STRATEGY_DRAFT_KEY = "rewind.generatedStrategyDraft.v1";
const ACTION_BLOCK_RE = /```rewind-action\s*[\r\n][\s\S]*?```/gi;
const RUN_POLL_INTERVAL_MS = 3000;
const TERMINAL_RUN_STATUSES = new Set<Run["status"]>(["completed", "failed"]);

interface ActionProgress {
  status: "creating" | Run["status"];
  detail: string;
  href?: string;
}

interface ExecutedAction {
  result: Record<string, unknown>;
  href?: string;
  navigate?: boolean;
  auditStatus?: ChatActionAuditRequest["status"];
  error?: string;
}

function formatDateTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function sessionLabel(session: ChatSessionSummary): string {
  const context = getChatContext(session.context);
  const label = contextLabel(context);
  if (label) return label;
  return `Session ${session.id.slice(0, 8)}...`;
}

function getChatContext(context: ChatSessionSummary["context"] | null | undefined): ChatContext | null {
  if (!context || typeof context !== "object") return null;
  const record = context as Record<string, unknown>;

  if (record.type === "run" && typeof record.run_id === "string") {
    return { type: "run", run_id: record.run_id };
  }

  const runIds = record.run_ids;
  if (
    record.type === "compare" &&
    Array.isArray(runIds) &&
    runIds.every((runId) => typeof runId === "string")
  ) {
    return { type: "compare", run_ids: runIds as string[] };
  }

  return null;
}

function contextLabel(context: ChatContext | null): string {
  if (!context) return "";
  if (context.type === "run") return `Run ${context.run_id.slice(0, 8)}...`;
  return `Compare ${context.run_ids.length} runs`;
}

function parseChatQuery(searchParams: { get: (name: string) => string | null }): {
  context: ChatContext | null;
  error: string;
  prompt: string;
} {
  const prompt = searchParams.get("prompt")?.trim() ?? "";
  const contextType = searchParams.get("context");

  if (!contextType) return { context: null, error: "", prompt };

  if (contextType === "run") {
    const runId = searchParams.get("run_id")?.trim();
    if (!runId) {
      return { context: null, error: "Run chat context is missing a run ID.", prompt };
    }
    return { context: { type: "run", run_id: runId }, error: "", prompt };
  }

  if (contextType === "compare") {
    const runIds = (searchParams.get("run_ids") ?? "")
      .split(",")
      .map((runId) => runId.trim())
      .filter(Boolean);
    if (runIds.length < 2) {
      return { context: null, error: "Compare chat context needs at least two run IDs.", prompt };
    }
    return { context: { type: "compare", run_ids: runIds }, error: "", prompt };
  }

  return { context: null, error: "Chat context type is not supported.", prompt };
}

function tempMessage(content: string, sessionId: string | null): ChatMessage {
  return {
    id: `temp-${Date.now()}`,
    session_id: sessionId ?? "pending",
    role: "user",
    content,
    linked_run_id: null,
    metadata: {},
    ordering: 0,
    created_at: new Date().toISOString(),
  };
}

function getGeneratedStrategyMetadata(message: ChatMessage): GeneratedStrategyMetadata | null {
  const generated = message.metadata.generated_strategy;
  if (!generated || typeof generated !== "object") return null;
  if (typeof generated.code !== "string" || typeof generated.valid !== "boolean") return null;
  if (!Array.isArray(generated.errors)) return null;

  return {
    code: generated.code,
    valid: generated.valid,
    class_name: typeof generated.class_name === "string" ? generated.class_name : null,
    errors: generated.errors.filter((error): error is string => typeof error === "string"),
  };
}

function stripActionBlocks(content: string): string {
  return content.replace(ACTION_BLOCK_RE, "").trim();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isChatActionStatus(value: unknown): value is ChatAction["status"] {
  return (
    value === "proposed" ||
    value === "completed" ||
    value === "failed" ||
    value === "cancelled"
  );
}

function getAssistantActions(message: ChatMessage): ChatAction[] {
  const actions = message.metadata.assistant_actions;
  if (!Array.isArray(actions)) return [];

  return actions.filter((action): action is ChatAction => {
    if (!isRecord(action) || !isRecord(action.payload)) return false;
    return (
      typeof action.id === "string" &&
      (action.type === "apply_code" ||
        action.type === "run_backtest" ||
        action.type === "compare_runs" ||
        action.type === "create_strategy_and_run") &&
      typeof action.label === "string" &&
      isChatActionStatus(action.status)
    );
  });
}

function isApplyCodePayload(payload: ChatAction["payload"]): payload is ApplyCodeActionPayload {
  return (
    isRecord(payload) &&
    typeof payload.strategy_id === "string" &&
    typeof payload.code === "string"
  );
}

function isRunBacktestPayload(
  payload: ChatAction["payload"]
): payload is RunBacktestActionPayload {
  return (
    isRecord(payload) &&
    typeof payload.strategy_id === "string" &&
    isRecord(payload.params)
  );
}

function isCompareRunsPayload(payload: ChatAction["payload"]): payload is CompareRunsActionPayload {
  return (
    isRecord(payload) &&
    Array.isArray(payload.run_ids) &&
    payload.run_ids.every((runId) => typeof runId === "string")
  );
}

function isCreateStrategyAndRunPayload(
  payload: ChatAction["payload"]
): payload is CreateStrategyAndRunActionPayload {
  return (
    isRecord(payload) &&
    typeof payload.name === "string" &&
    typeof payload.description === "string" &&
    typeof payload.code === "string" &&
    isRecord(payload.params)
  );
}

function actionSummary(action: ChatAction): string {
  if (action.type === "apply_code" && isApplyCodePayload(action.payload)) {
    const className = action.payload.class_name ? ` (${action.payload.class_name})` : "";
    return `Update strategy ${action.payload.strategy_id.slice(0, 8)}...${className}`;
  }

  if (action.type === "run_backtest" && isRunBacktestPayload(action.payload)) {
    const params = Object.keys(action.payload.params).length
      ? JSON.stringify(action.payload.params)
      : "{}";
    return `Start run for strategy ${action.payload.strategy_id.slice(0, 8)}... with ${params}`;
  }

  if (action.type === "compare_runs" && isCompareRunsPayload(action.payload)) {
    return `Open comparison for ${action.payload.run_ids.length} runs`;
  }

  if (action.type === "create_strategy_and_run" && isCreateStrategyAndRunPayload(action.payload)) {
    const params = Object.keys(action.payload.params).length
      ? JSON.stringify(action.payload.params)
      : "{}";
    const className = action.payload.class_name ? ` (${action.payload.class_name})` : "";
    return `Create "${action.payload.name}"${className} and run with ${params}`;
  }

  return "Action payload is invalid";
}

function actionStatusClass(status: ChatAction["status"] | ActionProgress["status"]): string {
  if (status === "completed") return "border-green-800 bg-green-950/30 text-green-300";
  if (status === "failed") return "border-red-800 bg-red-950/30 text-red-300";
  if (status === "cancelled") return "border-zinc-700 bg-zinc-900 text-zinc-400";
  if (status === "running") return "border-amber-800 bg-amber-950/30 text-amber-300";
  if (status === "creating" || status === "pending") {
    return "border-blue-800 bg-blue-950/30 text-blue-300";
  }
  return "border-blue-800 bg-blue-950/30 text-blue-300";
}

function actionResultText(action: ChatAction): string {
  if (action.error) return action.error;
  if (!action.result || Object.keys(action.result).length === 0) return "";

  if (typeof action.result.run_id === "string") {
    const status =
      typeof action.result.status === "string" ? ` ${action.result.status}` : "";
    const metrics = isRecord(action.result.metrics) ? metricSummary(action.result.metrics) : "";
    return `Run ${action.result.run_id.slice(0, 8)}...${status}.${metrics ? ` ${metrics}` : ""}`;
  }
  if (typeof action.result.strategy_version === "number") {
    return `Strategy updated to v${action.result.strategy_version}.`;
  }
  if (Array.isArray(action.result.run_ids)) {
    return `Comparison opened for ${action.result.run_ids.length} runs.`;
  }

  return JSON.stringify(action.result);
}

function metricSummary(metrics: Record<string, unknown>): string {
  const parts: string[] = [];
  const totalReturn = formatMetric(metrics.total_return, "percent");
  const sharpe = formatMetric(metrics.sharpe_ratio, "decimal");
  const maxDrawdown = formatMetric(metrics.max_drawdown, "percent");
  const totalTrades = formatMetric(metrics.total_trades, "integer");

  if (totalReturn) parts.push(`Return ${totalReturn}`);
  if (sharpe) parts.push(`Sharpe ${sharpe}`);
  if (maxDrawdown) parts.push(`Max DD ${maxDrawdown}`);
  if (totalTrades) parts.push(`${totalTrades} trades`);

  return parts.join(", ");
}

function formatMetric(value: unknown, kind: "decimal" | "integer" | "percent"): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  if (kind === "integer") return String(Math.round(value));
  if (kind === "percent") return `${(value * 100).toFixed(2)}%`;
  return value.toFixed(2);
}

function actionRunHref(action: ChatAction): string {
  return typeof action.result?.run_id === "string" ? `/runs/${action.result.run_id}` : "";
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-6xl px-6 py-10 text-sm text-zinc-400">
          Loading chat...
        </div>
      }
    >
      <ChatPageClient />
    </Suspense>
  );
}

function ChatPageClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryKey = searchParams.toString();
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [activeContext, setActiveContext] = useState<ChatContext | null>(null);
  const [contextError, setContextError] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [actionBusyKey, setActionBusyKey] = useState<string | null>(null);
  const [actionProgress, setActionProgress] = useState<Record<string, ActionProgress>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    void loadSessions();
  }, []);

  useEffect(() => {
    const parsed = parseChatQuery(searchParams);
    setContextError(parsed.error);
    setActiveContext(parsed.context);

    if (parsed.context || parsed.prompt || parsed.error) {
      setSelectedSessionId(null);
      setMessages([]);
      setStreamingText("");
      setError("");
    }

    if (parsed.prompt) {
      setInput(parsed.prompt);
    }
  }, [queryKey, searchParams]);

  async function loadSessions() {
    setLoadingSessions(true);
    try {
      const res = await apiFetch<ChatSessionListResponse>("/api/v1/chat/sessions");
      setSessions(res.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setLoadingSessions(false);
    }
  }

  async function loadSession(sessionId: string) {
    setLoadingMessages(true);
    setError("");
    try {
      const session = await apiFetch<ChatSession>(`/api/v1/chat/sessions/${sessionId}`);
      setSelectedSessionId(session.id);
      setMessages(session.messages);
      setActiveContext(getChatContext(session.context));
      setContextError("");
      setStreamingText("");
      setActionProgress({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load session");
    } finally {
      setLoadingMessages(false);
    }
  }

  async function deleteSession(sessionId: string) {
    setError("");
    try {
      await apiFetch<void>(`/api/v1/chat/sessions/${sessionId}`, { method: "DELETE" });
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(null);
        setMessages([]);
        setActiveContext(null);
        setStreamingText("");
      }
      await loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete session");
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setError("");
    setSending(true);
    setStreamingText("");
    setMessages((current) => [...current, tempMessage(text, selectedSessionId)]);

    let activeSessionId = selectedSessionId;
    let streamError = "";
    const body: ChatRequest = {
      session_id: selectedSessionId,
      message: text,
    };
    if (activeContext) {
      body.context = activeContext;
    }

    try {
      for await (const streamEvent of apiEventStream<ChatStreamEvent>("/api/v1/chat", body)) {
        if (streamEvent.type === "session") {
          activeSessionId = streamEvent.session.id;
          setSelectedSessionId(streamEvent.session.id);
          setSessions((current) => {
            const withoutCurrent = current.filter((item) => item.id !== streamEvent.session.id);
            return [streamEvent.session, ...withoutCurrent];
          });
        } else if (streamEvent.type === "chunk") {
          setStreamingText((current) => current + streamEvent.content);
        } else if (streamEvent.type === "error") {
          streamError = streamEvent.error || "Assistant failed to respond";
          setError(streamError);
        }
      }

      if (activeSessionId) {
        await loadSession(activeSessionId);
      }
      await loadSessions();
      if (streamError) setError(streamError);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message");
    } finally {
      setSending(false);
      setStreamingText("");
    }
  }

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) ?? null,
    [sessions, selectedSessionId]
  );
  const activeContextLabel = contextLabel(activeContext);

  function useGeneratedStrategy(message: ChatMessage, generated: GeneratedStrategyMetadata) {
    const draft: GeneratedStrategyDraft = {
      code: generated.code,
      className: generated.class_name ?? null,
      sourceMessageId: message.id,
      createdAt: new Date().toISOString(),
    };

    try {
      sessionStorage.setItem(GENERATED_STRATEGY_DRAFT_KEY, JSON.stringify(draft));
      router.push("/strategies/new?draft=generated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to prepare generated strategy draft");
    }
  }

  function replaceMessage(updatedMessage: ChatMessage) {
    setMessages((current) =>
      current.map((message) => (message.id === updatedMessage.id ? updatedMessage : message))
    );
  }

  async function recordActionAudit(
    message: ChatMessage,
    action: ChatAction,
    body: ChatActionAuditRequest
  ): Promise<ChatMessage> {
    const updatedMessage = await apiFetch<ChatMessage>(
      `/api/v1/chat/messages/${message.id}/actions/${action.id}`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    );
    replaceMessage(updatedMessage);
    await loadSessions();
    return updatedMessage;
  }

  function setActionProgressForKey(key: string, progress: ActionProgress) {
    setActionProgress((current) => ({ ...current, [key]: progress }));
  }

  async function pollRunToTerminal(run: Run, key: string): Promise<Run> {
    let currentRun = run;
    setActionProgressForKey(key, {
      status: currentRun.status,
      detail: `Run ${currentRun.id.slice(0, 8)}... is ${currentRun.status}.`,
      href: `/runs/${currentRun.id}`,
    });

    while (!TERMINAL_RUN_STATUSES.has(currentRun.status)) {
      await wait(RUN_POLL_INTERVAL_MS);
      currentRun = await apiFetch<Run>(`/api/v1/runs/${currentRun.id}`);
      setActionProgressForKey(key, {
        status: currentRun.status,
        detail: `Run ${currentRun.id.slice(0, 8)}... is ${currentRun.status}.`,
        href: `/runs/${currentRun.id}`,
      });
    }

    return currentRun;
  }

  async function executeAction(action: ChatAction, key: string): Promise<ExecutedAction> {
    if (action.type === "apply_code") {
      if (!isApplyCodePayload(action.payload)) {
        throw new Error("Apply-code action payload is invalid.");
      }
      const strategy = await apiFetch<Strategy>(
        `/api/v1/strategies/${action.payload.strategy_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ code: action.payload.code }),
        }
      );
      return {
        result: {
          strategy_id: strategy.id,
          strategy_version: strategy.version,
          class_name: action.payload.class_name ?? null,
        },
      };
    }

    if (action.type === "run_backtest") {
      if (!isRunBacktestPayload(action.payload)) {
        throw new Error("Run-backtest action payload is invalid.");
      }
      const run = await apiFetch<Run>("/api/v1/runs", {
        method: "POST",
        body: JSON.stringify({
          strategy_id: action.payload.strategy_id,
          params: action.payload.params,
        }),
      });
      return {
        result: {
          run_id: run.id,
          strategy_id: run.strategy_id,
          status: run.status,
        },
        href: `/runs/${run.id}`,
      };
    }

    if (action.type === "create_strategy_and_run") {
      if (!isCreateStrategyAndRunPayload(action.payload)) {
        throw new Error("Create-strategy-and-run action payload is invalid.");
      }
      setActionProgressForKey(key, {
        status: "creating",
        detail: `Creating strategy "${action.payload.name}".`,
      });
      const strategy = await apiFetch<Strategy>("/api/v1/strategies", {
        method: "POST",
        body: JSON.stringify({
          name: action.payload.name,
          description: action.payload.description,
          code: action.payload.code,
        }),
      });
      const run = await apiFetch<Run>("/api/v1/runs", {
        method: "POST",
        body: JSON.stringify({
          strategy_id: strategy.id,
          params: action.payload.params,
        }),
      });
      const finalRun = await pollRunToTerminal(run, key);

      return {
        result: {
          strategy_id: strategy.id,
          strategy_version: strategy.version,
          run_id: finalRun.id,
          status: finalRun.status,
          metrics: finalRun.metrics,
          error: finalRun.error ?? "",
          completed_at: finalRun.completed_at ?? new Date().toISOString(),
          class_name: action.payload.class_name ?? null,
        },
        href: `/runs/${finalRun.id}`,
        navigate: false,
        auditStatus: finalRun.status === "failed" ? "failed" : "completed",
        error: finalRun.status === "failed" ? finalRun.error ?? "Backtest failed." : "",
      };
    }

    if (action.type === "compare_runs") {
      if (!isCompareRunsPayload(action.payload)) {
        throw new Error("Compare-runs action payload is invalid.");
      }
      return {
        result: { run_ids: action.payload.run_ids },
        href: `/compare?runs=${encodeURIComponent(action.payload.run_ids.join(","))}`,
      };
    }

    throw new Error("Unsupported chat action.");
  }

  async function confirmAction(message: ChatMessage, action: ChatAction) {
    const key = `${message.id}:${action.id}`;
    if (actionBusyKey) return;

    setActionBusyKey(key);
    setError("");

    let execution: ExecutedAction;
    try {
      execution = await executeAction(action, key);
    } catch (err) {
      const actionError = err instanceof Error ? err.message : "Action failed.";
      try {
        await recordActionAudit(message, action, {
          status: "failed",
          result: {},
          error: actionError,
        });
      } catch {
        // Keep the execution error visible if audit recording also fails.
      }
      setActionBusyKey(null);
      setActionProgress((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      setError(actionError);
      return;
    }

    try {
      await recordActionAudit(message, action, {
        status: execution.auditStatus ?? "completed",
        result: execution.result,
        error: execution.error ?? "",
      });
      if (execution.href && execution.navigate !== false) router.push(execution.href);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action completed but audit failed.");
    } finally {
      setActionBusyKey(null);
      setActionProgress((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
    }
  }

  async function cancelAction(message: ChatMessage, action: ChatAction) {
    const key = `${message.id}:${action.id}`;
    if (actionBusyKey) return;

    setActionBusyKey(key);
    setError("");
    try {
      await recordActionAudit(message, action, { status: "cancelled", result: {} });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel action.");
    } finally {
      setActionBusyKey(null);
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl flex-1 gap-6 px-6 py-10 lg:grid-cols-[18rem_1fr]">
      <aside className="border-b border-zinc-800 pb-5 lg:min-h-[32rem] lg:border-b-0 lg:border-r lg:pb-0 lg:pr-4">
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-xl font-bold">Chat</h1>
          <button
            onClick={() => {
              router.replace("/chat", { scroll: false });
              setSelectedSessionId(null);
              setMessages([]);
              setActiveContext(null);
              setContextError("");
              setInput("");
              setStreamingText("");
              setActionProgress({});
              setError("");
            }}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            New
          </button>
        </div>

        <div className="mt-5 space-y-2">
          {loadingSessions ? (
            <p className="text-sm text-zinc-400">Loading...</p>
          ) : sessions.length === 0 ? (
            <p className="text-sm text-zinc-500">No sessions yet</p>
          ) : (
            sessions.map((session) => (
              <div
                key={session.id}
                className={`rounded border p-3 ${
                  session.id === selectedSessionId
                    ? "border-blue-700 bg-blue-950/30"
                    : "border-zinc-800 bg-zinc-900"
                }`}
              >
                <button
                  onClick={() => void loadSession(session.id)}
                  className="block w-full text-left"
                >
                  <span className="block text-sm font-medium text-zinc-100">
                    {sessionLabel(session)}
                  </span>
                  <span className="mt-1 block text-xs text-zinc-500">
                    {session.message_count} messages
                  </span>
                  <span className="mt-1 block text-xs text-zinc-500">
                    {formatDateTime(session.last_message_at ?? session.updated_at)}
                  </span>
                </button>
                <button
                  onClick={() => void deleteSession(session.id)}
                  className="mt-3 text-xs text-zinc-500 hover:text-red-300"
                >
                  Delete
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      <main className="flex min-h-[32rem] flex-col">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-4">
          <div>
            <h2 className="text-lg font-semibold">
              {selectedSession ? sessionLabel(selectedSession) : "New Session"}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              {selectedSession
                ? `Updated ${formatDateTime(selectedSession.updated_at)}`
                : "Drafting a new conversation"}
            </p>
            {activeContextLabel ? (
              <p className="mt-1 text-sm text-blue-300">Context: {activeContextLabel}</p>
            ) : null}
          </div>
          <button
            onClick={() => void loadSessions()}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
          >
            Refresh
          </button>
        </div>

        {error ? (
          <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}
        {contextError ? (
          <p className="mt-4 rounded border border-red-800 bg-red-950 px-3 py-2 text-sm text-red-300">
            {contextError}
          </p>
        ) : null}

        <section className="mt-5 flex-1 overflow-y-auto">
          {loadingMessages ? (
            <p className="text-sm text-zinc-400">Loading...</p>
          ) : messages.length === 0 && !streamingText ? (
            <div className="rounded border border-zinc-800 bg-zinc-900 p-5 text-sm text-zinc-500">
              No messages yet
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  onUseGeneratedStrategy={useGeneratedStrategy}
                  onConfirmAction={confirmAction}
                  onCancelAction={cancelAction}
                  busyActionKey={actionBusyKey}
                  actionProgress={actionProgress}
                />
              ))}
              {streamingText ? (
                <div className="rounded border border-zinc-800 bg-zinc-900 p-4">
                  <p className="text-xs font-medium uppercase text-zinc-500">
                    Assistant
                  </p>
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-100">
                    {streamingText}
                  </p>
                </div>
              ) : null}
            </div>
          )}
        </section>

        <form onSubmit={sendMessage} className="mt-5 border-t border-zinc-800 pt-4">
          <textarea
            value={input}
            onChange={(event) => setInput(event.target.value)}
            disabled={sending}
            rows={4}
            className="w-full resize-none rounded border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-blue-600 disabled:opacity-60"
            placeholder="Message Rewind"
          />
          <div className="mt-3 flex justify-end">
            <button
              type="submit"
              disabled={!input.trim() || sending}
              className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
            >
              {sending ? "Sending..." : "Send"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}

function MessageBubble({
  message,
  onUseGeneratedStrategy,
  onConfirmAction,
  onCancelAction,
  busyActionKey,
  actionProgress,
}: {
  message: ChatMessage;
  onUseGeneratedStrategy: (message: ChatMessage, generated: GeneratedStrategyMetadata) => void;
  onConfirmAction: (message: ChatMessage, action: ChatAction) => void;
  onCancelAction: (message: ChatMessage, action: ChatAction) => void;
  busyActionKey: string | null;
  actionProgress: Record<string, ActionProgress>;
}) {
  const isUser = message.role === "user";
  const generatedStrategy = isUser ? null : getGeneratedStrategyMetadata(message);
  const assistantActions = isUser ? [] : getAssistantActions(message);
  const visibleContent = isUser ? message.content : stripActionBlocks(message.content);

  return (
    <div
      className={`rounded border p-4 ${
        isUser ? "border-blue-800 bg-blue-950/30" : "border-zinc-800 bg-zinc-900"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase text-zinc-500">
          {isUser ? "You" : "Assistant"}
        </p>
        <p className="text-xs text-zinc-600">{formatDateTime(message.created_at)}</p>
      </div>
      {visibleContent ? (
        <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-zinc-100">
          {visibleContent}
        </p>
      ) : null}
      {generatedStrategy?.valid ? (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-zinc-800 pt-4">
          <button
            onClick={() => onUseGeneratedStrategy(message, generatedStrategy)}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500"
          >
            Review generated strategy
          </button>
          <span className="text-xs text-zinc-500">
            {generatedStrategy.class_name ?? "Strategy"} will open as an unsaved draft.
          </span>
        </div>
      ) : null}
      {assistantActions.length > 0 ? (
        <div className="mt-4 space-y-3 border-t border-zinc-800 pt-4">
          {assistantActions.map((action) => (
            <ActionCard
              key={action.id}
              message={message}
              action={action}
              onConfirm={onConfirmAction}
              onCancel={onCancelAction}
              busy={busyActionKey === `${message.id}:${action.id}`}
              disabled={busyActionKey !== null}
              progress={actionProgress[`${message.id}:${action.id}`]}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ActionCard({
  message,
  action,
  onConfirm,
  onCancel,
  busy,
  disabled,
  progress,
}: {
  message: ChatMessage;
  action: ChatAction;
  onConfirm: (message: ChatMessage, action: ChatAction) => void;
  onCancel: (message: ChatMessage, action: ChatAction) => void;
  busy: boolean;
  disabled: boolean;
  progress?: ActionProgress;
}) {
  const resultText = actionResultText(action);
  const runHref = progress?.href ?? actionRunHref(action);
  const visibleStatus = progress?.status ?? action.status;

  return (
    <div className="rounded border border-zinc-800 bg-zinc-950 p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-zinc-100">{action.label}</p>
          <p className="mt-1 text-xs text-zinc-500">{actionSummary(action)}</p>
        </div>
        <span
          className={`rounded border px-2 py-1 text-xs font-medium ${actionStatusClass(
            visibleStatus
          )}`}
        >
          {visibleStatus}
        </span>
      </div>

      {progress ? <p className="mt-3 text-xs text-blue-300">{progress.detail}</p> : null}
      {resultText ? <p className="mt-3 text-xs text-zinc-400">{resultText}</p> : null}
      {runHref ? (
        <a
          href={runHref}
          className="mt-3 inline-flex text-xs font-medium text-blue-300 hover:text-blue-200"
        >
          Open run detail
        </a>
      ) : null}

      {action.status === "proposed" ? (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => onConfirm(message, action)}
            disabled={disabled}
            className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-500 disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500"
          >
            {busy ? "Working..." : "Confirm"}
          </button>
          <button
            onClick={() => onCancel(message, action)}
            disabled={disabled}
            className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800 disabled:cursor-not-allowed disabled:text-zinc-600"
          >
            Cancel
          </button>
        </div>
      ) : null}
    </div>
  );
}
