"use client";

import { Loader2, MessageSquarePlus, Send } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Citations } from "@/components/chat/citations";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { chatApi } from "@/lib/endpoints";
import type { ChatMessage, ChatSession } from "@/lib/types";
import { cn } from "@/lib/utils";

function ChatInner() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load session list once.
  useEffect(() => {
    chatApi
      .listSessions()
      .then(setSessions)
      .finally(() => setLoadingSessions(false));
  }, []);

  // Load messages when the active session changes.
  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    chatApi.getSession(activeId).then((s) => setMessages(s.messages));
  }, [activeId]);

  // Auto-scroll to the newest message.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function newChat() {
    try {
      const s = await chatApi.createSession();
      setSessions((prev) => [s, ...prev]);
      setActiveId(s.id);
      setMessages([]);
    } catch {
      toast.error("Could not start a chat");
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question) return;

    // Ensure there's a session (create one on first message).
    let sessionId = activeId;
    if (!sessionId) {
      try {
        const s = await chatApi.createSession();
        setSessions((prev) => [s, ...prev]);
        setActiveId(s.id);
        sessionId = s.id;
      } catch {
        toast.error("Could not start a chat");
        return;
      }
    }

    setInput("");
    setSending(true);
    // Optimistically show the user's turn immediately.
    const optimistic: ChatMessage = {
      id: `tmp-${Date.now()}`,
      role: "user",
      content: question,
      citations: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const answer = await chatApi.ask(sessionId!, question);
      setMessages((prev) => [...prev, answer]);
      // Refresh sidebar (first question becomes the title).
      chatApi.listSessions().then(setSessions);
    } catch {
      toast.error("Could not get an answer");
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      {/* Sessions sidebar */}
      <div className="hidden w-64 shrink-0 flex-col gap-2 md:flex">
        <Button onClick={newChat} variant="outline" className="w-full justify-start">
          <MessageSquarePlus className="h-4 w-4" /> New chat
        </Button>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {loadingSessions ? (
            [...Array(4)].map((_, i) => <Skeleton key={i} className="h-9 w-full" />)
          ) : sessions.length === 0 ? (
            <p className="px-2 py-4 text-xs text-muted-foreground">No chats yet.</p>
          ) : (
            sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveId(s.id)}
                className={cn(
                  "w-full truncate rounded-md px-3 py-2 text-left text-sm transition-colors",
                  activeId === s.id ? "bg-primary/10 text-primary" : "hover:bg-accent"
                )}
              >
                {s.title}
              </button>
            ))
          )}
        </div>
      </div>

      {/* Chat area */}
      <Card className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
              <p className="text-lg font-medium text-foreground">Ask about your meetings</p>
              <p className="mt-1 max-w-sm text-sm">
                e.g. &quot;What did we decide about the release?&quot; or &quot;Who owns the
                backend?&quot; Answers cite the exact meeting and moment.
              </p>
            </div>
          ) : (
            messages.map((m) => (
              <div
                key={m.id}
                className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
              >
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg px-4 py-3 text-sm",
                    m.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground"
                  )}
                >
                  <p className="whitespace-pre-wrap">{m.content}</p>
                  {m.role === "assistant" && m.citations && <Citations citations={m.citations} />}
                </div>
              </div>
            ))
          )}
          {sending && (
            <div className="flex justify-start">
              <div className="rounded-lg bg-muted px-4 py-3">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={send} className="flex gap-2 border-t p-4">
          <Input
            placeholder="Ask a question…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending}
          />
          <Button type="submit" size="icon" disabled={sending || !input.trim()}>
            <Send className="h-4 w-4" />
          </Button>
        </form>
      </Card>
    </div>
  );
}

export default function ChatPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <ChatInner />
    </Suspense>
  );
}
