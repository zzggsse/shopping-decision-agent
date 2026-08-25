import { useStore } from "../../lib/store";

/** 权重滑块:维度来自当前品类配置,拖动即时重排候选。 */
export function WeightSliders() {
  const { weights, setWeights, candidates, schema } = useStore();

  if (!schema) return null;

  const total = schema.dimensions.reduce(
    (sum, dimension) => sum + (weights[dimension.key] ?? 0), 0,
  ) || 1;

  return (
    <div className="weights">
      <div className="weights-head">
        <strong>你更看重什么</strong>
        <span>拖动即时重排{candidates.length ? `(${candidates.length} 款)` : ""}</span>
      </div>
      <div className="weight-grid">
        {schema.dimensions.map((dimension) => (
          <label key={dimension.key}>
            <span className="weight-name">{dimension.label}</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={weights[dimension.key] ?? dimension.default_weight}
              onChange={(event) =>
                void setWeights({ ...weights, [dimension.key]: Number(event.target.value) })
              }
            />
            <span className="weight-value">
              {Math.round(((weights[dimension.key] ?? 0) / total) * 100)}%
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}