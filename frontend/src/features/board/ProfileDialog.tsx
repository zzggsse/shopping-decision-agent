import { useStore } from "../../lib/store";

/** 用户档案编辑:健康状况、过敏禁忌、生活方式,跨会话生效。 */
export function ProfileDialog() {
  const {
    profile, profileOpen, setProfileOpen, conditionsMeta, toggleCondition,
  } = useStore();

  if (!profileOpen) return null;

  const groups = new Map<string, { key: string; label: string; hint: string }[]>();
  for (const [key, meta] of Object.entries(conditionsMeta)) {
    if (!groups.has(meta.group)) groups.set(meta.group, []);
    groups.get(meta.group)!.push({ key, label: meta.label, hint: meta.hint });
  }

  const active = new Set(profile?.conditions ?? []);

  return (
    <div className="modal-backdrop" onClick={() => setProfileOpen(false)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>我的健康与偏好档案</h2>
          <button onClick={() => setProfileOpen(false)}>×</button>
        </header>
        <p className="modal-tip">
          勾选后,推荐会自动考虑这些情况。例如选了"糖尿病",食品会避开添加糖;
          选了"敏感头皮",洗发水会优先氨基酸配方并标注 SLS。
        </p>

        {[...groups.entries()].map(([group, items]) => (
          <section key={group}>
            <h3>{group}</h3>
            <div className="condition-list">
              {items.map((item) => {
                const on = active.has(item.key);
                return (
                  <button
                    key={item.key}
                    className={on ? "condition on" : "condition"}
                    title={item.hint}
                    onClick={() => void toggleCondition(item.key)}
                  >
                    <span className="check">{on ? "✓" : ""}</span>
                    <span className="cond-label">{item.label}</span>
                    <em>{item.hint}</em>
                  </button>
                );
              })}
            </div>
          </section>
        ))}

        <footer>
          <button className="primary" onClick={() => setProfileOpen(false)}>完成</button>
        </footer>
      </div>
    </div>
  );
}