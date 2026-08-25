import { useEffect, useRef, useState } from "react";
import { useStore } from "../../lib/store";

export function ChatPanel() {
  const {
    messages, busy, progress, send, categories, startCategory, schema,
  } = useStore();
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, progress]);

  const submit = () => {
    const value = text;
    setText("");
    void send(value);
  };

  return (
    <section className="chat">
      <header className="panel-head">
        <h1>购物决策助手</h1>
        <p>
          {schema ? `当前品类:${schema.label} · ` : ""}
          多平台比价 · 按你的偏好排序 · 全程可追溯
        </p>
      </header>

      <div className="messages">
        {messages.length === 0 && (
          <div className="starters">
            <p>想买什么?点一下直接开始:</p>
            <div className="category-grid">
              {categories.map((category) => (
                <button key={category.key} onClick={() => void startCategory(category.key)}>
                  {category.label}
                </button>
              ))}
            </div>
            <p className="hint">也可以直接描述需求,例如"预算 800 的通勤降噪耳机"</p>
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id} className={`bubble ${message.role}`}>
            <div className="bubble-body">{message.content}</div>
            {message.options && (
              <div className="quick">
                {message.options.values.map((option) => (
                  <button
                    key={option}
                    disabled={busy}
                    onClick={() =>
                      void send(option, { slot: message.options!.slot, option })
                    }
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
            {message.categoryOptions && (
              <div className="quick category-quick">
                {message.categoryOptions.map((option) => (
                  <button
                    key={option.key}
                    disabled={busy}
                    onClick={() => void startCategory(option.key)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {progress && <div className="bubble assistant progress">{progress}</div>}
        <div ref={bottom} />
      </div>

      <div className="composer">
        <textarea
          value={text}
          placeholder={`补充需求,或直接说「太贵了」「不要这个牌子」、也可以换品类`}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <button className="primary" disabled={busy || !text.trim()} onClick={submit}>
          {busy ? "思考中…" : "发送"}
        </button>
      </div>
    </section>
  );
}