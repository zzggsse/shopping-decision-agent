import type { Candidate, Profile, IngredientInfo } from "../../types";

/** 成分分析展示块:配料表逐成分解释 + 针对用户的禁忌/适合结论。 */
export function IngredientPanel({ candidate }: { candidate: Candidate }) {
  const analysis = candidate.ingredient_analysis;
  if (!analysis) return null;

  return (
    <div className="ingredients">
      <div className="ing-head">
        <span>成分/营养分析</span>
        {analysis.matched_concerns.length > 0 && (
          <em>针对:{analysis.matched_concerns.join("、")}</em>
        )}
      </div>

      {analysis.avoids.length > 0 && (
        <div className="ing-avoid">
          <b>⛔ 不建议你使用:</b>
          <ul>{analysis.avoids.map((item: string) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}

      {analysis.benefits.length > 0 && (
        <div className="ing-benefit">
          <b>✓ 适合点:</b>
          <ul>{analysis.benefits.map((item: string) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}

      {analysis.cautions.length > 0 && (
        <div className="ing-caution">
          <b>⚠ 需注意:</b>
          <ul>{analysis.cautions.map((item: string) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}

      <details className="ing-detail">
        <summary>查看完整配料表({analysis.recognized.length} 种已识别)</summary>
        <div className="ing-list">
          {analysis.recognized.map((item: IngredientInfo) => (
            <div key={item.name} className="ing-item">
              <b>{item.name}</b>
              {item.helps_with.length > 0 && (
                <span className="helps">针对 {item.helps_with.join("、")}</span>
              )}
              {item.benefits.map((b: string) => <p key={b} className="pro">+ {b}</p>)}
              {item.risks.map((r: string) => <p key={r} className="con">- {r}</p>)}
            </div>
          ))}
          {analysis.unrecognized.length > 0 && (
            <div className="ing-unknown">
              未在知识库中:{analysis.unrecognized.join("、")}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}

/** 顶部档案条:展示当前生效的健康/偏好标签,点击打开编辑。 */
export function ProfileBar({
  profile, onOpen,
}: { profile: Profile | null; onOpen: () => void }) {
  const count = profile?.conditions.length ?? 0;
  return (
    <button className="profile-bar" onClick={onOpen} title="点击编辑你的健康与偏好档案">
      <span>👤 我的档案</span>
      {count > 0 ? (
        <span className="profile-tags">{count} 项偏好已生效</span>
      ) : (
        <span className="profile-empty">未设置,点此添加(如糖尿病、敏感肌)</span>
      )}
    </button>
  );
}