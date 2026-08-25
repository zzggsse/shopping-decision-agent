import { useStore } from "../../lib/store";

const ACTION_LABEL: Record<string, string> = {
  category: "切换品类",
  understand: "理解需求",
  clarify: "追问",
  gather: "检索",
  align: "同款识别",
  drop: "排除",
  verify: "实时复核",
  refine: "重排",
  reweight: "调整偏好",
  redirect: "跳转校验",
};

/** 决策链路时间线:长链路里"我为什么排除了 A"随时可回溯。 */
export function TaskTimeline() {
  const { decisionLog } = useStore();

  if (!decisionLog.length) {
    return <div className="empty">这里会记录每一步决策依据,方便你随时回溯</div>;
  }

  return (
    <ol className="timeline">
      {decisionLog.map((entry, index) => (
        <li key={`${entry.at}-${index}`} className={entry.action === "drop" ? "dropped" : ""}>
          <span className="action">{ACTION_LABEL[entry.action] ?? entry.action}</span>
          <span className="detail">{entry.detail}</span>
          <time>
            {new Date(entry.at).toLocaleTimeString("zh-CN", {
              hour: "2-digit", minute: "2-digit",
            })}
          </time>
        </li>
      ))}
    </ol>
  );
}