/** 品类元信息,由后端 /api/categories 下发,前端据此动态渲染。 */
export interface DimensionMeta {
  key: string;
  label: string;
  default_weight: number;
}

export interface AttributeMeta {
  key: string;
  label: string;
  unit: string;
  kind: "number" | "enum" | "text";
  summary: boolean;
  /** 枚举值 -> 中文展示名 */
  labels: Record<string, string>;
}

export interface CategorySchema {
  key: string;
  label: string;
  dimensions: DimensionMeta[];
  attributes: AttributeMeta[];
  budget_options: string[];
  triggers?: string[];
  platforms?: string[];
}

export interface PriceComponent {
  label: string;
  amount: number;
  evidence: string;
}

export interface Breakdown {
  final_price: number | null;
  list_price: number;
  saved: number;
  components: PriceComponent[];
  fetched_at: string;
  stale: boolean;
}

export interface OfferView {
  offer_id: string;
  platform: string;
  title: string;
  list_price: number;
  final_price: number | null;
  shop_name: string | null;
  review_score: number | null;
  review_count: number;
  in_stock: boolean;
  delivery_days: number | null;
  url: string;
  fetched_at: string;
  stale: boolean;
  breakdown: Breakdown;
}

export interface Score {
  group_id: string;
  total: number;
  dimensions: Record<string, number>;
  pros: string[];
  cons: string[];
}

export interface PriceSpread {
  min_platform: string;
  min_price: number;
  max_platform: string;
  max_price: number;
  saved: number;
}

/** 候选商品。属性为动态字典,渲染依赖 CategorySchema。 */
export interface Candidate {
  group_id: string;
  category: string;
  title: string;
  brand: string;
  model: string;
  attributes: Record<string, string | number | null>;
  /** 后端预渲染的可读文本,前端优先使用 */
  display: Record<string, string>;
  summary: string;
  best_price: number | null;
  best_platform: string | null;
  best_url: string | null;
  price_breakdown: Breakdown | null;
  offers: OfferView[];
  score: Score | null;
  price_spread: PriceSpread | null;
  ingredient_analysis?: IngredientAnalysis | null;
}

export interface Pick {
  label: string;
  group_id: string;
  title: string;
  summary: string;
  final_price: number;
  platform: string;
  url: string;
  score: number | null;
  pros: string[];
  cons: string[];
  price_spread: PriceSpread | null;
  fetched_at: string;
  needs_recheck: boolean;
}

export interface Report {
  category: string;
  category_label: string;
  summary: string;
  picks: Pick[];
  weights?: Record<string, number>;
  requirement?: Record<string, unknown>;
}

/** 权重为动态字典,键取自当前品类的 dimensions。 */
export type Weights = Record<string, number>;

export interface LogEntry {
  at: string;
  state: string;
  action: string;
  detail: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  options?: { slot: string; values: string[] };
  categoryOptions?: { key: string; label: string }[];
  note?: string;
}

export const PLATFORM_LABEL: Record<string, string> = {
  jd: "京东",
  tmall: "天猫",
  pdd: "拼多多",
  amazon: "亚马逊",
};

export function platformName(key: string | null): string {
  if (!key) return "-";
  return PLATFORM_LABEL[key] ?? key;
}
export interface IngredientInfo {
  name: string;
  benefits: string[];
  risks: string[];
  helps_with: string[];
}

export interface IngredientAnalysis {
  raw: string;
  recognized: IngredientInfo[];
  unrecognized: string[];
  benefits: string[];
  cautions: string[];
  avoids: string[];
  matched_concerns: string[];
  score: number;
}

export interface ConditionMeta {
  label: string;
  group: string;
  hint: string;
}

export interface Profile {
  user_id: string;
  display_name: string;
  conditions: string[];
  notes: string;
}


/** 长期记忆条目。记忆必须可感知、可撤销，所以带上原话依据。 */
export interface MemoryItem {
  kind: string;
  value: string;
  label: string;
  confidence: number;
  evidence: string;
  created_at: string;
}

export interface TraceStep {
  index: number;
  kind: "decide" | "tool" | "final" | "error" | string;
  name: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  detail: string;
  elapsed_ms: number;
  tokens: number;
}

/** 一次运行的轨迹，用于调试面板。 */
export interface RunTrace {
  steps: TraceStep[];
  tool_calls: string[];
  tokens_used: number;
  elapsed_seconds: number;
  stop_reason: string;
  failure_count: number;
  summary?: string;
}

export const MEMORY_KIND_LABEL: Record<string, string> = {
  condition: "健康/生活",
  brand_deny: "不要的品牌",
  brand_prefer: "偏好的品牌",
  price_attitude: "价格态度",
  note: "其他",
};
