import { create } from "zustand";
import { api, forgetMemory, getProfile, getTrace, listMemory, streamChat, updateProfile } from "./api";
import type {
  Candidate,
  CategorySchema,
  ConditionMeta,
  LogEntry,
  MemoryItem,
  Message,
  Profile,
  Report,
  RunTrace,
  Weights,
} from "../types";

interface State {
  taskId: string | null;
  categories: CategorySchema[];
  schema: CategorySchema | null;
  messages: Message[];
  candidates: Candidate[];
  report: Report | null;
  weights: Weights;
  decisionLog: LogEntry[];
  state: string;
  busy: boolean;
  progress: string;
  warning: string;
  redirectNotice: string;
  selected: string[];
  profile: Profile | null;
  conditionsMeta: Record<string, ConditionMeta>;
  profileOpen: boolean;
  memories: MemoryItem[];
  memoryDigest: string;
  trace: RunTrace | null;
  traceOpen: boolean;
  memoryOpen: boolean;
}

interface Actions {
  init: () => Promise<void>;
  send: (text: string, quick?: { slot: string; option: string }) => Promise<void>;
  startCategory: (key: string) => Promise<void>;
  setWeights: (weights: Weights) => Promise<void>;
  dropSelected: () => Promise<void>;
  toggleSelect: (groupId: string) => void;
  refresh: () => Promise<void>;
  verifyAfterClick: (offerId: string) => Promise<void>;
  dismissRedirectNotice: () => void;
  loadProfile: () => Promise<void>;
  toggleCondition: (condition: string) => Promise<void>;
  setProfileOpen: (open: boolean) => void;
  loadMemories: () => Promise<void>;
  forgetMemory: (kind: string, value: string) => Promise<void>;
  loadTrace: () => Promise<void>;
  setTraceOpen: (open: boolean) => void;
  setMemoryOpen: (open: boolean) => void;
}

let weightTimer: ReturnType<typeof setTimeout> | undefined;

function defaultWeights(schema: CategorySchema | null): Weights {
  if (!schema) return {};
  return Object.fromEntries(
    schema.dimensions.map((dimension) => [dimension.key, dimension.default_weight]),
  );
}

export const useStore = create<State & Actions>((set, get) => ({
  taskId: null,
  categories: [],
  schema: null,
  messages: [],
  candidates: [],
  report: null,
  weights: {},
  decisionLog: [],
  state: "intent_clarify",
  busy: false,
  progress: "",
  warning: "",
  redirectNotice: "",
  selected: [],
  profile: null,
  conditionsMeta: {},
  profileOpen: false,
  memories: [],
  memoryDigest: "",
  trace: null,
  traceOpen: false,
  memoryOpen: false,

  init: async () => {
    const [categories, profileData] = await Promise.all([
      api.listCategories(), getProfile(),
    ]);
    set({
      categories,
      profile: profileData.profile,
      conditionsMeta: profileData.conditions_meta,
    });
    void get().loadMemories();
  },

  /** 从品类选择器进入:显式指定品类,不依赖关键词猜测。 */
  startCategory: async (key) => {
    const schema = get().categories.find((item) => item.key === key);
    if (!schema) return;
    set({
      taskId: null,
      schema,
      weights: defaultWeights(schema),
      messages: [],
      candidates: [],
      report: null,
      decisionLog: [],
      selected: [],
      warning: "",
    });
    await get().send(`我想买${schema.label}`);
  },

  send: async (text, quick) => {
    if (!text.trim() || get().busy) return;
    const userMessage: Message = {
      id: crypto.randomUUID(), role: "user", content: text,
    };
    set((s) => ({
      messages: [...s.messages, userMessage], busy: true, progress: "", warning: "",
    }));

    try {
      await streamChat(
        {
          message: text,
          task_id: get().taskId,
          slot: quick?.slot,
          option: quick?.option,
          category: get().taskId ? undefined : get().schema?.key,
        },
        (event) => {
          switch (event.type) {
            case "task_created": {
              const schema = event.schema as CategorySchema;
              set((s) => ({
                taskId: event.task_id as string,
                schema,
                weights: Object.keys(s.weights).length ? s.weights : defaultWeights(schema),
              }));
              break;
            }
            case "select_category":
              push(
                set,
                event.question as string,
                undefined,
                event.categories as { key: string; label: string }[],
              );
              break;
            case "category": {
              const schema = event.schema as CategorySchema;
              set({
                schema,
                weights: defaultWeights(schema),
                candidates: [],
                report: null,
                selected: [],
              });
              push(set, `好的,我们来看${event.label as string}。`);
              break;
            }
            case "task_state":
              set({ state: event.state as string });
              break;
            case "progress":
              set({ progress: event.message as string });
              break;
            case "warning":
              set({ warning: event.message as string });
              break;
            case "memory_updated": {
              const learned = (event.learned as string[]) ?? [];
              if (learned.length) {
                const msg = "已记住：" + learned.join("、") + "（可在档案里修改）";
                push(set, msg);
              }
              void get().loadMemories();
              break;
            }
            case "understood": {
              const signals = (event.signals as string[]) ?? [];
              const notes = (event.weight_notes as string[]) ?? [];
              if (signals.length || notes.length) {
                push(set, `已记录:${[...signals, ...notes].join("、")}`);
              }
              break;
            }
            case "clarify":
              push(set, event.question as string, {
                slot: event.slot as string,
                values: event.options as string[],
              });
              break;
            case "candidates_update":
              set({ candidates: event.candidates as Candidate[] });
              break;
            case "report": {
              const report = event.report as Report;
              set({ report });
              push(set, report.summary);
              break;
            }
            case "trace":
              set({ trace: event.trace as RunTrace });
              break;
            case "error":
              push(set, `抱歉,${event.message as string}`);
              break;
          }
        },
      );

      const taskId = get().taskId;
      if (taskId) {
        const detail = await api.getTask(taskId);
        set({
          decisionLog: detail.decision_log,
          weights: detail.weights,
          schema: detail.schema,
        });
      }
    } finally {
      set({ busy: false, progress: "" });
    }
  },

  /** 滑块调整:本地即时反馈 + 防抖请求后端重排 */
  setWeights: async (weights) => {
    set({ weights });
    const taskId = get().taskId;
    if (!taskId || !get().candidates.length) return;
    clearTimeout(weightTimer);
    weightTimer = setTimeout(async () => {
      const result = await api.updateWeights(taskId, weights);
      set({ candidates: result.candidates, report: result.report });
    }, 220);
  },

  toggleSelect: (groupId) =>
    set((s) => ({
      selected: s.selected.includes(groupId)
        ? s.selected.filter((id) => id !== groupId)
        : [...s.selected, groupId],
    })),

  dropSelected: async () => {
    const { taskId, selected } = get();
    if (!taskId || !selected.length) return;
    const result = await api.dropCandidates(taskId, selected);
    const detail = await api.getTask(taskId);
    set({
      candidates: result.candidates,
      report: result.report,
      decisionLog: detail.decision_log,
      selected: [],
    });
  },

  refresh: async () => {
    const taskId = get().taskId;
    if (!taskId) return;
    set({ busy: true, progress: "正在实时复核价格…" });
    try {
      const result = await api.refreshPrices(taskId);
      set({
        candidates: result.candidates,
        warning: result.failed_platforms.length
          ? `以下平台价格暂无法确认:${result.failed_platforms.join("、")}`
          : "",
      });
    } finally {
      set({ busy: false, progress: "" });
    }
  },

  /** 点击即由 <a> 直接跳转(浏览器不会拦截);这里只做后台价格校验,
   *  若跳转前发现价格已变动,等用户回到页面时用横幅提示核对。 */
  verifyAfterClick: async (offerId: string) => {
    const taskId = get().taskId;
    if (!taskId) return;
    try {
      const result = await api.checkRedirect(taskId, offerId);
      if (!result.ok) {
        set({ redirectNotice: result.message });
      }
    } catch {
      /* 校验失败不影响用户已在新标签打开的页面 */
    }
  },

  dismissRedirectNotice: () => set({ redirectNotice: "" }),

  loadProfile: async () => {
    const data = await getProfile();
    set({ profile: data.profile, conditionsMeta: data.conditions_meta });
  },

  toggleCondition: async (condition: string) => {
    const current = get().profile?.conditions ?? [];
    const next = current.includes(condition)
      ? current.filter((c) => c !== condition)
      : [...current, condition];
    const profile = await updateProfile(next);
    set({ profile });
  },

    loadMemories: async () => {
    try {
      const data = await listMemory();
      set({ memories: data.items, memoryDigest: data.digest });
    } catch { /* 静默失败 */ }
  },

  forgetMemory: async (kind: string, value: string) => {
    try {
      await forgetMemory(kind, value);
      await get().loadMemories();
    } catch { /* 静默失败 */ }
  },

  loadTrace: async () => {
    try {
      const trace = await getTrace();
      set({ trace });
    } catch { /* 静默失败 */ }
  },

  setTraceOpen: (traceOpen: boolean) => {
    set({ traceOpen });
    if (traceOpen) void get().loadTrace();
  },

  setMemoryOpen: (memoryOpen: boolean) => {
    set({ memoryOpen });
    if (memoryOpen) void get().loadMemories();
  },

setProfileOpen: (profileOpen: boolean) => set({ profileOpen }),
}));

function push(
  set: (fn: (s: State) => Partial<State>) => void,
  content: string,
  options?: Message["options"],
  categoryOptions?: Message["categoryOptions"],
) {
  set((s) => ({
    messages: [
      ...s.messages,
      { id: crypto.randomUUID(), role: "assistant" as const, content, options, categoryOptions },
    ],
  }));
}