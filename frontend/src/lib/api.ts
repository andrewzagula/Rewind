function getApiError(error: unknown): Error {
  if (error instanceof TypeError && error.message === "Failed to fetch") {
    return new Error(
      "Unable to reach the API. Start the backend or check the frontend API proxy configuration."
    );
  }

  return error instanceof Error ? error : new Error("Unexpected API error");
}

async function getResponseError(res: Response): Promise<Error> {
  let detail = `${res.status} ${res.statusText}`;

  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (body.detail != null) {
      detail = JSON.stringify(body.detail);
    }
  } catch {
    // Keep the status text if the response body is empty or not JSON.
  }

  return new Error(`API error: ${detail}`);
}

export async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;

  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...options?.headers },
      ...options,
    });
  } catch (error) {
    throw getApiError(error);
  }

  if (!res.ok) {
    throw await getResponseError(res);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function* apiStream(path: string, body: unknown): AsyncGenerator<string> {
  let res: Response;

  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    throw getApiError(error);
  }

  if (!res.ok) {
    throw await getResponseError(res);
  }

  if (!res.body) {
    throw new Error("API error: response body is unavailable");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    yield decoder.decode(value, { stream: true });
  }
}

function parseSseBlock<T>(block: string): T | null {
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");

  if (!data) return null;
  return JSON.parse(data) as T;
}

export async function* apiEventStream<T>(path: string, body: unknown): AsyncGenerator<T> {
  let buffer = "";

  for await (const chunk of apiStream(path, body)) {
    buffer += chunk;
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      const event = parseSseBlock<T>(block);
      if (event) yield event;
    }
  }

  const event = parseSseBlock<T>(buffer);
  if (event) yield event;
}
