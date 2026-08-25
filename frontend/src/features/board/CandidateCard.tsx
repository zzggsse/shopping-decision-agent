import { useState } from "react";
import {
  platformName,
  type AttributeMeta,
  type Candidate,
  type CategorySchema,
} from "../../types";
import { useStore } from "../../lib/store";
import { IngredientPanel } from "./Ingredients";

/** 属性可读化:优先用后端预渲染值,其次查枚举标签,最后回退原值+单位。 */
function readable(candidate: Candidate, attribute: AttributeMeta): string {
  const raw = candidate.attributes[attribute.key];
  if (raw === null || raw === undefined || raw === "") return "";
  const pre = candidate.display?.[attribute.key];
  if (pre) return pre;
  if (attribute.kind === "enum") {
    return attribute.labels?.[String(raw)] ?? String(raw);
  }
  return `${raw}${attribute.unit}`;
}

function freshness(fetchedAt: string): string {
  const minutes = Math.floor((Date.now() - new Date(fetchedAt).getTime()) / 60000);
  if (minutes < 1) return "刚刚更新";
  if (minutes < 60) return `更新于 ${minutes} 分钟前`;
  return `更新于 ${Math.floor(minutes / 60)} 小时前`;
}

/** 按品类配置渲染摘要行,不同品类展示完全不同的参数。 */
function summaryOf(candidate: Candidate, schema: CategorySchema | null): string {
  if (!schema) return candidate.summary;
  const parts: string[] = [];
  for (const attribute of schema.attributes) {
    if (!attribute.summary) continue;
    const text = readable(candidate, attribute);
    if (text) parts.push(text);
  }
  return parts.join(" · ") || candidate.summary;
}

export function CandidateCard({ candidate, rank }: { candidate: Candidate; rank: number }) {
  const [open, setOpen] = useState(false);
  const { selected, toggleSelect, verifyAfterClick, schema } = useStore();
  const { score, price_spread: spread } = candidate;
  const best = candidate.offers.find((offer) => offer.platform === candidate.best_platform);
  const checked = selected.includes(candidate.group_id);

  return (
    <article className={`card ${checked ? "picked" : ""}`}>
      <div className="card-head">
        <div>
          <span className="rank">#{rank}</span>
          <strong>{candidate.title}</strong>
          <div className="spec-line">{summaryOf(candidate, schema)}</div>
        </div>
        <div className="price-block">
          <div className={`price ${best?.stale ? "stale" : ""}`}>
            ¥{candidate.best_price?.toLocaleString()}
          </div>
          <div className="price-meta">{platformName(candidate.best_platform)} 最低</div>
          {best && (
            <div className="fetched">
              {best.stale ? "价格待核对" : freshness(best.fetched_at)}
            </div>
          )}
          {score && <div className="score">匹配度 {score.total}</div>}
        </div>
      </div>

      {spread && spread.saved > 0 && (
        <div className="spread">
          同款在 {platformName(spread.max_platform)} 需 ¥{spread.max_price.toLocaleString()},
          选对平台可省 <b>¥{spread.saved.toLocaleString()}</b>
        </div>
      )}

      {score && (
        <div className="reasons">
          {score.pros.map((item) => <div key={item} className="pro">+ {item}</div>)}
          {score.cons.map((item) => <div key={item} className="con">− {item}</div>)}
        </div>
      )}

      {candidate.ingredient_analysis && (
        <IngredientPanel candidate={candidate} />
      )}

      <div className="card-actions">
        <button onClick={() => setOpen(!open)}>
          {open ? "收起比价明细" : `展开 ${candidate.offers.length} 个平台报价`}
        </button>
        <button onClick={() => toggleSelect(candidate.group_id)}>
          {checked ? "取消排除" : "排除它"}
        </button>
        {best && best.url && (
          <a
            className="btn primary"
            href={best.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={() => void verifyAfterClick(best.offer_id)}
          >
            去购买
          </a>
        )}
      </div>

      {open && (
        <div className="offers">
          {schema && (
            <div className="attr-table">
              {schema.attributes
                .filter((attribute) => candidate.attributes[attribute.key] != null)
                .map((attribute) => (
                  <div key={attribute.key} className="attr-cell">
                    <span>{attribute.label}</span>
                    <b>{readable(candidate, attribute)}</b>
                  </div>
                ))}
            </div>
          )}

          {candidate.offers.map((offer) => (
            <div key={offer.offer_id} className="offer">
              <div className="offer-head">
                <span className="platform">{platformName(offer.platform)}</span>
                <span className={`offer-price ${offer.stale ? "stale" : ""}`}>
                  ¥{offer.final_price?.toLocaleString()}
                </span>
                <span className="offer-meta">
                  {offer.in_stock ? `${offer.delivery_days ?? "?"} 天达` : "无货"}
                  {offer.review_score ? ` · 评分 ${offer.review_score}` : ""}
                </span>
                <a
                  className="btn"
                  href={offer.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => void verifyAfterClick(offer.offer_id)}
                >
                  去看看
                </a>
              </div>
              <ul className="components">
                {offer.breakdown.components.map((component) => (
                  <li key={component.label}>
                    <span>{component.label}</span>
                    <span className={component.amount < 0 ? "minus" : ""}>
                      {component.amount < 0 ? "−" : ""}
                      ¥{Math.abs(component.amount).toLocaleString()}
                    </span>
                    <em>{component.evidence}</em>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}