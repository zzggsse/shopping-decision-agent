import { useState } from "react";
import { useStore } from "../../lib/store";
import { CandidateCard } from "./CandidateCard";
import { WeightSliders } from "./WeightSliders";
import { DecisionReport } from "../task/DecisionReport";
import { TaskTimeline } from "../task/TaskTimeline";
import { ProfileBar } from "./Ingredients";
import { ProfileDialog } from "./ProfileDialog";

const STATE_LABEL: Record<string, string> = {
  intent_clarify: "了解需求",
  candidate_gather: "多平台检索",
  compare: "计算到手价",
  preference_rank: "按偏好排序",
  user_feedback: "根据反馈调整",
  decision_ready: "可以决策了",
};

type Tab = "候选对比" | "决策报告" | "决策链路";

export function BoardPanel() {
  const {
    candidates, state, warning, redirectNotice, dismissRedirectNotice,
    selected, dropSelected, refresh, busy,
    schema, categories, startCategory, profile, setProfileOpen,
  } = useStore();
  const [tab, setTab] = useState<Tab>("候选对比");

  return (
    <section className="board">
      <ProfileBar profile={profile} onOpen={() => setProfileOpen(true)} />
      <ProfileDialog />
      <div className="board-head">
        <div className="steps">
          {Object.entries(STATE_LABEL).map(([key, label]) => (
            <span key={key} className={key === state ? "step active" : "step"}>{label}</span>
          ))}
        </div>
        <div className="board-tools">
          <button onClick={() => void refresh()} disabled={busy || !candidates.length}>
            实时刷新价格
          </button>
          {selected.length > 0 && (
            <button className="danger" onClick={() => void dropSelected()}>
              排除选中 {selected.length} 款
            </button>
          )}
        </div>
      </div>

      <div className="category-bar">
        {categories.map((category) => (
          <button
            key={category.key}
            className={schema?.key === category.key ? "chip active" : "chip"}
            disabled={busy}
            onClick={() => void startCategory(category.key)}
          >
            {category.label}
          </button>
        ))}
      </div>

      {warning && <div className="warning">{warning}</div>}
      {redirectNotice && (
        <div className="warning notice" onClick={dismissRedirectNotice}>
          ⚠ {redirectNotice}（点击关闭）
        </div>
      )}

      <WeightSliders />

      <nav className="tabs">
        {(["候选对比", "决策报告", "决策链路"] as Tab[]).map((item) => (
          <button
            key={item}
            className={tab === item ? "active" : ""}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </nav>

      <div className="board-body">
        {tab === "候选对比" && (
          candidates.length ? (
            candidates.map((candidate, index) => (
              <CandidateCard key={candidate.group_id} candidate={candidate} rank={index + 1} />
            ))
          ) : (
            <div className="empty">
              选个品类或直接描述需求,这里会出现跨平台比价结果
            </div>
          )
        )}
        {tab === "决策报告" && <DecisionReport />}
        {tab === "决策链路" && <TaskTimeline />}
      </div>
    </section>
  );
}