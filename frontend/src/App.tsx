import { useEffect } from "react";
import { ChatPanel } from "./features/chat/ChatPanel";
import { BoardPanel } from "./features/board/BoardPanel";
import { useStore } from "./lib/store";

/** 双栏布局:左对话、右决策看板,二者双向联动。 */
export function App() {
  const init = useStore((state) => state.init);

  useEffect(() => {
    void init();
  }, [init]);

  return (
    <main className="layout">
      <ChatPanel />
      <BoardPanel />
    </main>
  );
}