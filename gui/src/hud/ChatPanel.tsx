import { useState, useEffect, useRef, useCallback } from "react";
import { useGameStore } from "../store/gameStore";
import { useAuthStore } from "../store/authStore";
import { api } from "../api/client";
import type { ChatMessage } from "../api/types";

/** Dedupe key for a chat message */
function msgKey(m: ChatMessage): string {
  return `${m.tick}:${m.user_id}:${m.message}`;
}

export default function ChatPanel() {
  const teamChat = useGameStore((s) => s.teamChat);
  const token = useAuthStore((s) => s.token);
  const userId = useAuthStore((s) => s.userId);

  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [lastSeenCount, setLastSeenCount] = useState(0);
  const [panelW, setPanelW] = useState(240);
  const [panelH, setPanelH] = useState(200);

  // Accumulate messages locally so they don't vanish when the server window moves
  const [allMessages, setAllMessages] = useState<ChatMessage[]>([]);
  const seenKeys = useRef(new Set<string>());

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Resize drag state
  const resizing = useRef(false);
  const startX = useRef(0);
  const startY = useRef(0);
  const startW = useRef(panelW);
  const startH = useRef(panelH);

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizing.current = true;
    startX.current = e.clientX;
    startY.current = e.clientY;
    startW.current = panelW;
    startH.current = panelH;
    const onMove = (ev: MouseEvent) => {
      if (!resizing.current) return;
      const dx = ev.clientX - startX.current;
      const dy = startY.current - ev.clientY; // dragging up = bigger
      setPanelW(Math.max(200, Math.min(500, startW.current + dx)));
      setPanelH(Math.max(150, Math.min(600, startH.current + dy)));
    };
    const onUp = () => {
      resizing.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, [panelW, panelH]);

  // Merge incoming server messages into local buffer
  useEffect(() => {
    const reversed = [...teamChat].reverse(); // server sends newest-first
    let added = false;
    for (const msg of reversed) {
      const key = msgKey(msg);
      if (!seenKeys.current.has(key)) {
        seenKeys.current.add(key);
        setAllMessages((prev) => [...prev, msg]);
        added = true;
      }
    }
    if (added) {
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      });
    }
  }, [teamChat]);

  // Mark messages as seen when expanded
  useEffect(() => {
    if (expanded) {
      setLastSeenCount(allMessages.length);
    }
  }, [expanded, allMessages.length]);

  // Focus input and scroll to bottom when expanding
  useEffect(() => {
    if (expanded) {
      inputRef.current?.focus();
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "instant" });
      });
    }
  }, [expanded]);

  const unreadCount = expanded ? 0 : Math.max(0, allMessages.length - lastSeenCount);

  async function handleSend() {
    if (!token || !input.trim() || sending) return;
    setSending(true);
    try {
      await api.sendChat(token, input.trim());
      setInput("");
      inputRef.current?.focus();
    } catch {
      // silently fail
    } finally {
      setSending(false);
    }
  }

  // Enter opens chat when collapsed, Esc closes it
  const handleGlobalKey = useCallback((e: KeyboardEvent) => {
    // Don't capture if user is typing in another input
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;

    if (e.key === "Enter" && !expanded) {
      e.preventDefault();
      setExpanded(true);
    }
  }, [expanded]);

  useEffect(() => {
    window.addEventListener("keydown", handleGlobalKey);
    return () => window.removeEventListener("keydown", handleGlobalKey);
  }, [handleGlobalKey]);

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="bg-space-panel/80 border border-space-border rounded backdrop-blur-sm
                   px-3 py-1 text-xs text-text-secondary hover:text-text-primary transition
                   flex items-center gap-1.5"
      >
        CHAT
        {unreadCount > 0 && (
          <span className="bg-friendly text-space-bg text-[9px] font-bold rounded-full px-1.5 min-w-[16px] text-center">
            {unreadCount}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="bg-space-panel/80 border border-space-border rounded backdrop-blur-sm flex flex-col relative"
         style={{ width: panelW, height: panelH }}>
      {/* Resize handle (top-right corner — drag up/right to grow) */}
      <div
        onMouseDown={onResizeStart}
        className="absolute top-0 right-0 w-3 h-3 cursor-ne-resize z-10"
        title="Drag to resize"
      >
        <svg viewBox="0 0 10 10" className="w-full h-full text-text-secondary/40 hover:text-text-secondary">
          <path d="M10 0L0 10M10 4L4 10M10 8L8 10" stroke="currentColor" strokeWidth="1.5" fill="none" />
        </svg>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-space-border flex-shrink-0">
        <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">
          Chat
        </span>
        <button
          onClick={() => setExpanded(false)}
          className="text-[10px] text-text-secondary hover:text-text-primary transition px-1"
        >
          _
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-2 py-1 min-h-0">
        {allMessages.length === 0 && (
          <div className="text-[10px] text-text-secondary italic py-2">No messages yet</div>
        )}
        {allMessages.map((msg, i) => (
          <div key={`${msg.tick}-${msg.user_id}-${i}`} className="text-[10px] leading-snug py-px">
            <span className={msg.user_id === userId ? "text-friendly" : "text-solarion"}>
              {msg.username}
            </span>
            <span className="text-text-primary"> {msg.message}</span>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-space-border flex-shrink-0 px-1 py-1">
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleSend();
            } else if (e.key === "Escape") {
              e.preventDefault();
              setExpanded(false);
            }
          }}
          placeholder="Type a message..."
          maxLength={200}
          className="w-full bg-space-bg/60 border border-space-border rounded px-2 py-0.5
                     text-[10px] text-text-primary placeholder-text-secondary/50
                     focus:outline-none focus:border-friendly/50"
        />
      </div>
    </div>
  );
}
