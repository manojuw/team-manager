"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useProject } from "@/hooks/use-project";
import { ai } from "@/lib/api";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Send, Bot, User, Loader2, MessageSquare, Sparkles } from "lucide-react";

interface Message {
  role: string;
  content: string;
}

interface StoredChat {
  messages: Message[];
  savedAt: number;
}

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

function getChatKey(projectId: string) {
  return `chat-history-${projectId}`;
}

function loadChat(projectId: string): Message[] {
  try {
    const raw = localStorage.getItem(getChatKey(projectId));
    if (!raw) return [];
    const stored: StoredChat = JSON.parse(raw);
    if (Date.now() - stored.savedAt > SEVEN_DAYS_MS) {
      localStorage.removeItem(getChatKey(projectId));
      return [];
    }
    return stored.messages || [];
  } catch {
    return [];
  }
}

function saveChat(projectId: string, messages: Message[]) {
  try {
    const stored: StoredChat = { messages, savedAt: Date.now() };
    localStorage.setItem(getChatKey(projectId), JSON.stringify(stored));
  } catch {
  }
}

function renderAIContent(content: string) {
  const lines = content.split("\n");
  return lines.map((line, i) => {
    if (line.startsWith("- ") || line.startsWith("• ")) {
      const text = line.replace(/^[-•]\s*/, "");
      return (
        <li key={i} className="ml-4 list-disc">
          {renderInline(text)}
        </li>
      );
    }
    if (line.trim() === "") {
      return <br key={i} />;
    }
    return (
      <p key={i} className="mb-1">
        {renderInline(line)}
      </p>
    );
  });
}

function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

export default function AskPage() {
  const { currentProject } = useProject();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (currentProject) {
      const saved = loadChat(currentProject.id);
      setMessages(saved);
    } else {
      setMessages([]);
    }
  }, [currentProject?.id]);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  function persistMessages(newMessages: Message[]) {
    if (currentProject) {
      saveChat(currentProject.id, newMessages);
    }
  }

  async function handleSend() {
    if (!currentProject || !input.trim() || loading) return;
    const question = input.trim();
    setInput("");

    const userMessage: Message = { role: "user", content: question };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    persistMessages(updatedMessages);
    setLoading(true);

    try {
      const data = await ai.ask({
        project_id: currentProject.id,
        question,
        chat_history: updatedMessages,
      });
      const answer = data.answer || data.response || data.content || "No response received.";
      const withAnswer = [...updatedMessages, { role: "assistant", content: answer }];
      setMessages(withAnswer);
      persistMessages(withAnswer);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to get response");
      const withError = [...updatedMessages, { role: "assistant", content: "Sorry, I encountered an error. Please try again." }];
      setMessages(withError);
      persistMessages(withError);
    } finally {
      setLoading(false);
    }
  }

  async function handleSummarize() {
    if (!currentProject || summarizing) return;
    setSummarizing(true);
    try {
      const data = await ai.summarize(currentProject.id);
      const summary = data.summary || data.content || data.answer || "No summary available.";
      const updated = [...messages, { role: "assistant", content: summary }];
      setMessages(updated);
      persistMessages(updated);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to summarize");
    } finally {
      setSummarizing(false);
    }
  }

  function handleClearChat() {
    setMessages([]);
    if (currentProject) {
      localStorage.removeItem(getChatKey(currentProject.id));
    }
  }

  if (!currentProject) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Ask Questions</h1>
          <p className="text-muted-foreground">Ask AI about your Teams conversations</p>
        </div>
        <Separator />
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <MessageSquare className="size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-semibold">No project selected</h3>
          <p className="text-muted-foreground mt-1">
            Please select a project first from the Projects page
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col" style={{ height: "calc(100vh - 120px)" }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Ask Questions</h1>
          <p className="text-muted-foreground">
            Ask AI about{" "}
            <span className="font-medium text-foreground">{currentProject.name}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleSummarize} disabled={summarizing}>
            {summarizing ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Summarizing…
              </>
            ) : (
              <>
                <Sparkles className="size-4" />
                Summarize Knowledge Base
              </>
            )}
          </Button>
          {messages.length > 0 && (
            <Button variant="outline" size="sm" onClick={handleClearChat}>
              Clear Chat
            </Button>
          )}
        </div>
      </div>

      <Card className="flex-1 flex flex-col min-h-0">
        <CardContent className="flex-1 flex flex-col p-0 min-h-0">
          <div
            ref={scrollContainerRef}
            className="flex-1 overflow-y-auto p-6"
          >
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <Sparkles className="size-12 text-muted-foreground mb-4" />
                <h3 className="text-lg font-semibold">Ask anything about your Teams conversations</h3>
                <p className="text-muted-foreground mt-1 max-w-md">
                  Use natural language to search, summarize, and analyze your synced Microsoft Teams data.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex gap-3 ${message.role === "user" ? "flex-row-reverse" : "flex-row"}`}
                  >
                    <Avatar className="shrink-0 mt-1">
                      <AvatarFallback>
                        {message.role === "user" ? (
                          <User className="size-4" />
                        ) : (
                          <Bot className="size-4" />
                        )}
                      </AvatarFallback>
                    </Avatar>
                    <div
                      className={`rounded-lg px-4 py-3 text-sm break-words ${
                        message.role === "user"
                          ? "bg-primary text-primary-foreground max-w-[80%]"
                          : "bg-muted flex-1 min-w-0"
                      }`}
                    >
                      {message.role === "assistant" ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                          {renderAIContent(message.content)}
                        </div>
                      ) : (
                        message.content
                      )}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex gap-3">
                    <Avatar className="shrink-0 mt-1">
                      <AvatarFallback>
                        <Bot className="size-4" />
                      </AvatarFallback>
                    </Avatar>
                    <div className="rounded-lg px-4 py-3 bg-muted">
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="size-4 animate-spin" />
                        Thinking…
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          <div className="border-t p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex gap-2"
            >
              <Input
                placeholder="Ask a question…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
              />
              <Button type="submit" disabled={loading || !input.trim()}>
                {loading ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Send className="size-4" />
                )}
              </Button>
            </form>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
