/**
 * AIChatBox — multi-turn AI chat with full conversation history.
 *
 * Improvements over original:
 *   - Full conversation history sent on every request (multi-turn memory)
 *   - Timestamps on messages
 *   - Clear history button
 *   - Context-aware: sends column list so AI knows the dataset shape
 */
import React, { useState, useRef, useEffect } from "react";
import { Send, Loader2, MessageSquare, Bot, User, Zap, Trash2 } from "lucide-react";
import { aiNLClean } from "../services/api";

const SUGGESTED_QUESTIONS = [
  "Remove duplicate rows",
  "Fill missing values with median",
  "Trim whitespace from all text columns",
  "Normalize text capitalisation",
  "Drop columns with more than 50% missing",
  "Show me rows where age is over 100",
];

function timestamp() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function AIChatBox({ sessionId, columns = [], onApplied }) {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hi! Tell me what to do with your data — or pick a quick command below.", ts: timestamp() },
  ]);
  const [input,   setInput]   = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef             = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend(overrideText) {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;

    const userMsg = { role: "user", text, ts: timestamp() };
    setMessages(m => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      // Build full conversation history to give the AI multi-turn context
      const history = [...messages, userMsg]
        .filter(m => m.role !== "system")
        .map(m => ({ role: m.role, content: m.text }));

      const result = await aiNLClean(sessionId, text, history);
      const action = result.parsed_action?.action ?? "unknown";
      const reply  = `✓ Applied "${action.replace(/_/g, " ")}" — ${result.rows?.toLocaleString()} rows remaining.`;

      setMessages(m => [...m, { role: "assistant", text: reply, success: true, ts: timestamp() }]);
      onApplied?.(result);
    } catch (err) {
      const detail = err?.response?.data?.detail ?? "Command failed. Try rephrasing.";
      setMessages(m => [...m, { role: "assistant", text: `✗ ${detail}`, error: true, ts: timestamp() }]);
    } finally {
      setLoading(false);
    }
  }

  function clearHistory() {
    setMessages([{ role: "assistant", text: "History cleared. What would you like to do?", ts: timestamp() }]);
  }

  return (
    <div className="chat-wrap">
      <div className="chat-header">
        <MessageSquare size={14} color="var(--accent)" />
        <span className="chat-title">AI Chat Cleaning</span>
        <span className="chat-cols">{columns.length} columns</span>
        <button className="chat-clear" onClick={clearHistory} title="Clear history">
          <Trash2 size={11} />
        </button>
      </div>

      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg--${m.role}`}>
            <div className="chat-avatar">
              {m.role === "assistant"
                ? <Bot size={12} color="var(--accent)" />
                : <User size={12} color="var(--text-2)" />}
            </div>
            <div className="chat-bubble">
              <p className={`chat-text${m.error ? " chat-error" : ""}${m.success ? " chat-success" : ""}`}>
                {m.text}
              </p>
              <span className="chat-ts">{m.ts}</span>
            </div>
          </div>
        ))}
        {loading && (
          <div className="chat-msg chat-msg--assistant">
            <div className="chat-avatar"><Bot size={12} color="var(--accent)" /></div>
            <div className="chat-bubble chat-typing">
              <span /><span /><span />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="chat-suggestions">
        <div className="chat-suggestions-label"><Zap size={10} color="var(--accent)" /> Quick commands</div>
        <div className="chat-suggestions-list">
          {SUGGESTED_QUESTIONS.map(q => (
            <button key={q} className="chat-suggestion-btn"
              onClick={() => handleSend(q)} disabled={loading}>{q}</button>
          ))}
        </div>
      </div>

      <div className="chat-input-row">
        <input className="chat-input" value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Type a cleaning command…" disabled={loading} />
        <button className="chat-send" onClick={() => handleSend()}
          disabled={loading || !input.trim()}>
          {loading ? <Loader2 size={13} className="spin" /> : <Send size={13} />}
        </button>
      </div>

      <style>{`
        .chat-wrap{background:var(--surface-1);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;max-height:480px}
        .chat-header{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid var(--border);flex-shrink:0}
        .chat-title{font-size:13px;font-weight:700;color:var(--text-0);flex:1}
        .chat-cols{font-size:10px;color:var(--text-3);background:var(--surface-2);padding:2px 6px;border-radius:99px}
        .chat-clear{background:none;border:none;cursor:pointer;color:var(--text-3);padding:3px;border-radius:4px;display:flex}
        .chat-clear:hover{color:#ef4444}
        .chat-messages{flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:8px;min-height:80px}
        .chat-msg{display:flex;gap:7px;align-items:flex-start}
        .chat-msg--user{flex-direction:row-reverse}
        .chat-avatar{width:20px;height:20px;border-radius:50%;background:var(--surface-2);display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:2px}
        .chat-bubble{display:flex;flex-direction:column;gap:2px;max-width:85%}
        .chat-msg--user .chat-bubble{align-items:flex-end}
        .chat-text{font-size:12px;color:var(--text-1);background:var(--surface-2);border-radius:8px;padding:7px 10px;margin:0;white-space:pre-line}
        .chat-msg--user .chat-text{background:var(--accent);color:#fff}
        .chat-error{color:#ef4444!important;background:rgba(239,68,68,.1)!important}
        .chat-success{color:#22c55e!important}
        .chat-ts{font-size:9px;color:var(--text-3);padding:0 4px}
        .chat-typing{display:flex;align-items:center;gap:3px;padding:10px;background:var(--surface-2);border-radius:8px}
        .chat-typing span{width:5px;height:5px;border-radius:50%;background:var(--text-3);animation:bounce .9s infinite}
        .chat-typing span:nth-child(2){animation-delay:.15s}
        .chat-typing span:nth-child(3){animation-delay:.3s}
        @keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-4px)}}
        .chat-suggestions{padding:6px 10px;border-top:1px solid var(--border);flex-shrink:0}
        .chat-suggestions-label{display:flex;align-items:center;gap:4px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);margin-bottom:5px}
        .chat-suggestions-list{display:flex;flex-wrap:wrap;gap:4px}
        .chat-suggestion-btn{font-size:10px;padding:3px 8px;border-radius:99px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-1);cursor:pointer;white-space:nowrap}
        .chat-suggestion-btn:hover:not(:disabled){background:var(--accent);color:#fff;border-color:var(--accent)}
        .chat-suggestion-btn:disabled{opacity:.4;cursor:not-allowed}
        .chat-input-row{display:flex;gap:6px;padding:8px 12px;border-top:1px solid var(--border);flex-shrink:0}
        .chat-input{flex:1;padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-0);font-size:12px;outline:none}
        .chat-input:focus{border-color:var(--accent)}
        .chat-send{width:30px;height:30px;border-radius:6px;border:none;background:var(--accent);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}
        .chat-send:disabled{opacity:.45;cursor:not-allowed}
        @keyframes spin{to{transform:rotate(360deg)}}.spin{animation:spin .7s linear infinite}
      `}</style>
    </div>
  );
}
