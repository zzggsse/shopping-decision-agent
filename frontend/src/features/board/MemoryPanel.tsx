import { useStore } from "../../lib/store";
import { MEMORY_KIND_LABEL } from "../../types";

/**
 * 长期记忆面板。
 *
 * 记忆必须可感知、可撤销：每条都展示“为什么记住了”的原话依据，
 * 并给出一个忘掉按钮。否则就是个黑盒子，用户会觉得系统在背后乱记东西。
 */
export function MemoryPanel() {
  const { memories, memoryDigest, memoryOpen, setMemoryOpen, forgetMemory } = useStore();

  if (!memoryOpen) {
    return (
      <button className="chip ghost" onClick={() => setMemoryOpen(true)}>
        记忆 {memories.length > 0 ? `(${memories.length})` : ""}
      </button>
    );
  }

  const grouped = memories.reduce<Record<string, typeof memories>>((acc, item) => {
    (acc[item.kind] ||= []).push(item);
    return acc;
  }, {});

  return (
    <div className="memory-panel">
      <header>
        <strong>我记住的事</strong>
        <button className="link" onClick={() => setMemoryOpen(false)}>收起</button>
      </header>

      {memories.length === 0 ? (
        <p className="hint">
          还没有记住任何长期偏好。你可以直接说“我有糖尿病”、
          “我是游戏重度用户”、“不要某个品牌”，下次就不用重复说了。
        </p>
      ) : (
        <>
          {memoryDigest && <p className="memory-digest">{memoryDigest}</p>}
          {Object.entries(grouped).map(([kind, items]) => (
            <div key={kind} className="memory-group">
              <span className="memory-kind">{MEMORY_KIND_LABEL[kind] ?? kind}</span>
              {items.map((item) => (
                <div key={`${item.kind}:${item.value}`} className="memory-item">
                  <div className="memory-main">
                    <strong>{item.label}</strong>
                    {item.confidence < 1 && (
                      <span className="memory-guess">推测</span>
                    )}
                  </div>
                  {item.evidence && (
                    <div className="memory-evidence">你说过：{item.evidence}</div>
                  )}
                  <button
                    className="link danger"
                    onClick={() => void forgetMemory(item.kind, item.value)}
                  >
                    忘掉它
                  </button>
                </div>
              ))}
            </div>
          ))}
        </>
      )}
    </div>
  );
}
