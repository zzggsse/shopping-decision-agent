import { useStore } from "../../lib/store";

/**
 * 运行轨迹面板（调试用）。
 *
 * 把 agent 每一步“想了什么 / 调了哪个工具 / 结果如何”摄开摆明，
 * 还包括预算消耗与收敛原因。出了问题能直接看到卡在哪一步。
 */
export function TracePanel() {
  const { trace, traceOpen, setTraceOpen } = useStore();

  if (!traceOpen) {
    return (
      <button className="chip ghost" onClick={() => setTraceOpen(true)}>
        运行轨迹
      </button>
    );
  }

  return (
    <div className="trace-panel">
      <header>
        <strong>这一轮我做了什么</strong>
        <button className="link" onClick={() => setTraceOpen(false)}>收起</button>
      </header>

      {!trace ? (
        <p className="hint">还没有轨迹，先发一句话试试。</p>
      ) : (
        <>
          <div className="trace-meta">
            <span>{trace.steps.length} 步</span>
            <span>{trace.elapsed_seconds.toFixed(1)}s</span>
            <span>~{trace.tokens_used} tokens</span>
            {trace.failure_count > 0 && (
              <span className="bad">{trace.failure_count} 次失败</span>
            )}
          </div>
          {trace.stop_reason && (
            <p className="hint">收敛原因：{trace.stop_reason}</p>
          )}
          <ol className="trace-steps">
            {trace.steps.map((step) => (
              <li key={step.index} className={step.ok ? "" : "bad"}>
                <span className={`trace-kind ${step.kind}`}>{step.kind}</span>
                <strong>{step.name || "-"}</strong>
                {step.elapsed_ms > 0 && (
                  <span className="trace-ms">{step.elapsed_ms}ms</span>
                )}
                {step.detail && <div className="trace-detail">{step.detail}</div>}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
