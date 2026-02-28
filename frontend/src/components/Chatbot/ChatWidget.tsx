import { useState } from "react";
import { sendChatMessage } from "../../services/chatApi";
import "./ChatWidget.css";

type Msg = { role: "user" | "bot"; text: string };

export default function ChatWidget() {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "bot", text: "Hi, I’m RootWatch Assistant. Ask about data center risk." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const onSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((m) => [...m, { role: "user", text }]);
    setInput("");
    setLoading(true);

    try {
      const reply = await sendChatMessage(text);
      setMessages((m) => [...m, { role: "bot", text: reply }]);
    } catch (e: any) {
      setMessages((m) => [...m, { role: "bot", text: e.message || "Error contacting chatbot." }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-widget">
      <h3>RootWatch Chat</h3>
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>{m.text}</div>
        ))}
      </div>
      <div className="chat-input-row">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          onKeyDown={(e) => e.key === "Enter" && onSend()}
        />
        <button onClick={onSend} disabled={loading}>
          {loading ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}