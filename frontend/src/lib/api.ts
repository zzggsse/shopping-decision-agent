import type {
  Candidate,
  ConditionMeta,
  CategorySchema,
  LogEntry,
  MemoryItem,
  Report,
  Profile,
  RunTrace,
  Weights,
} from "../types";

export interface StreamEvent {
  type: string;
  [key: string]: unknown;
}

/** 解析后端 SSE 流。逐块读取,按空行切分事件。 */
export async function streamChat(
  body: {
    message: string;
    task_id?: string | null;
    slot?: string;
    option?: string;
    category?: string | null;
  },
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.body) throw new Error("服务无响应");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as StreamEvent);
      } catch {
        /* 忽略半包 */
      }
    }
  }
}

async function post<T>(url: string, payload?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()) as T;
}

export const api = {
  listCategories: async () => {
    const response = await fetch("/api/categories");
    if (!response.ok) throw new Error("品类列表加载失败");
    return (await response.json()) as CategorySchema[];
  },

  updateWeights: (taskId: string, weights: Weights) =>
    post<{ candidates: Candidate[]; report: Report }>(
      `/api/tasks/${taskId}/weights`, { weights },
    ),

  dropCandidates: (taskId: string, groupIds: string[]) =>
    post<{ candidates: Candidate[]; report: Report }>(
      `/api/tasks/${taskId}/drop`, { group_ids: groupIds },
    ),

  refreshPrices: (taskId: string) =>
    post<{ candidates: Candidate[]; failed_platforms: string[] }>(
      `/api/tasks/${taskId}/refresh`,
    ),

  /** 跳转前二次校验:价格变动时需用户确认 */
  checkRedirect: (taskId: string, offerId: string) =>
    post<{
      ok: boolean;
      reason: string;
      message: string;
      shown_price: number;
      current_price: number | null;
      redirect_url: string;
    }>(`/api/tasks/${taskId}/redirect/${offerId}`),

  getTask: async (taskId: string) => {
    const response = await fetch(`/api/tasks/${taskId}`);
    if (!response.ok) throw new Error("任务加载失败");
    return (await response.json()) as {
      category: string;
      schema: CategorySchema;
      candidates: Candidate[];
      report: Report | null;
      weights: Weights;
      decision_log: LogEntry[];
      state: string;
    };
  },
};

/** 用户档案:跨会话的健康状况与生活方式偏好。 */
export async function getProfile(): Promise<{
  profile: Profile;
  conditions_meta: Record<string, ConditionMeta>;
}> {
  const response = await fetch("/api/profile");
  if (!response.ok) throw new Error("档案加载失败");
  return response.json();
}

export async function updateProfile(conditions: string[]): Promise<Profile> {
  const response = await fetch("/api/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conditions }),
  });
  if (!response.ok) throw new Error("档案保存失败");
  return (await response.json()).profile as Profile;
}


/** 长期记忆：可查看、可逐条忘掉。 */
export async function listMemory(): Promise<{
  backend: string;
  digest: string;
  items: MemoryItem[];
}> {
  const response = await fetch("/api/memory");
  if (!response.ok) throw new Error("记忆读取失败");
  return response.json();
}

export async function forgetMemory(kind: string, value: string): Promise<void> {
  const query = `kind=${encodeURIComponent(kind)}&value=${encodeURIComponent(value)}`;
  const response = await fetch(`/api/memory?${query}`, { method: "DELETE" });
  if (!response.ok) throw new Error("忘记失败");
}

/** 最近一次运行轨迹，给调试面板用。 */
export async function getTrace(): Promise<RunTrace | null> {
  const response = await fetch("/api/trace");
  if (!response.ok) return null;
  const data = await response.json();
  return data.available ? (data as RunTrace) : null;
}
