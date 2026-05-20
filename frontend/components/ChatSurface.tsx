'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { streamQuery } from '@/lib/api-client';
import type { ChatMessage } from '@/lib/types';
import { MessageBubble } from './MessageBubble';
import { SampleQuestions } from './SampleQuestions';

/**
 * The interactive chat surface: question input, the conversation transcript,
 * and the live tool-trace rendering. Consumes the agent `/query` SSE stream
 * through {@link streamQuery}.
 */
export function ChatSurface() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const patchMessage = useCallback(
    (id: string, patch: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) => {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m)),
      );
    },
    [],
  );

  const runQuery = useCallback(
    async (question: string) => {
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        text: question,
        steps: [],
        status: 'complete',
      };
      const assistantId = crypto.randomUUID();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        text: '',
        steps: [],
        status: 'streaming',
        question,
      };
      setMessages((prev) => [...prev, userMessage, assistantMessage]);
      setIsStreaming(true);

      await streamQuery(question, {
        onStep: (step) => patchMessage(assistantId, (m) => ({ steps: [...m.steps, step] })),
        onDelta: (text) => patchMessage(assistantId, (m) => ({ text: m.text + text })),
        onFinal: (response) =>
          patchMessage(assistantId, {
            text: response.answer,
            trace: response.trace,
            steps: response.trace.steps,
          }),
        onError: (error) => patchMessage(assistantId, { status: 'error', error }),
        onDone: () =>
          patchMessage(assistantId, (m) => ({ status: m.status === 'error' ? 'error' : 'complete' })),
      });

      setIsStreaming(false);
    },
    [patchMessage],
  );

  const submit = useCallback(() => {
    const question = input.trim();
    if (!question || isStreaming) return;
    setInput('');
    void runQuery(question);
  }, [input, isStreaming, runQuery]);

  const handleSample = useCallback((question: string) => {
    setInput(question);
    textareaRef.current?.focus();
  }, []);

  const handleRetry = useCallback(
    (question: string) => {
      if (isStreaming) return;
      void runQuery(question);
    },
    [isStreaming, runQuery],
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
        event.preventDefault();
        submit();
      }
    },
    [submit],
  );

  const canSubmit = input.trim().length > 0 && !isStreaming;
  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        {isEmpty ? (
          <div className="mx-auto max-w-2xl px-4 py-10">
            <h2 className="text-lg font-medium text-slate-200">Ask an aviation operations question</h2>
            <p className="mt-1 text-sm text-slate-400">
              The agent queries historical flight data, live weather and NOTAMs, and the FAA
              Aeronautical Information Manual — then shows its work. Try one of these:
            </p>
            <div className="mt-4">
              <SampleQuestions onSelect={handleSample} disabled={isStreaming} />
            </div>
          </div>
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-4 px-4 py-6">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} onRetry={handleRetry} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="border-t border-slate-800 bg-slate-950/80 px-4 py-3 backdrop-blur">
        <div className="mx-auto max-w-2xl">
          <div className="flex items-end gap-2 rounded-xl border border-slate-700 bg-slate-900 p-2 focus-within:border-accent/60">
            <label htmlFor="question-input" className="sr-only">
              Ask an aviation operations question
            </label>
            <textarea
              id="question-input"
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              placeholder="Ask about flight delays, weather, NOTAMs, or FAA procedures…"
              className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-slate-100 placeholder:text-slate-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isStreaming ? 'Running…' : 'Ask'}
            </button>
          </div>
          <p className="mt-1.5 px-1 text-xs text-slate-600">
            Public data only · not for operational decisions · Enter to send, Shift+Enter for a new line
          </p>
        </div>
      </div>
    </div>
  );
}
