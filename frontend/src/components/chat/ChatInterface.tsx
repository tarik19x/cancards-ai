"use client"

import { useEffect, useRef } from "react"
import { useStreamingChat } from "@/hooks/useStreamingChat"
import MessageBubble from "@/components/chat/MessageBubble"
import ChatInput from "@/components/chat/ChatInput"
import ThinkingIndicator from "@/components/chat/ThinkingIndicator"

const SUGGESTIONS = ["No FX fee cards", "Best for groceries", "New to Canada"]

export default function ChatInterface() {
  const { messages, isLoading, sendMessage, clearMessages } = useStreamingChat()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isLoading])

  const isEmpty = messages.length === 0

  if (isEmpty) {
    return (
      // Anchored ~20vh from the top rather than vertically centered —
      // centering sinks the hero on short viewports.
      <div className="flex h-full flex-col items-center overflow-y-auto px-4 pt-[12vh] md:pt-[20vh]">
        <div className="flex w-full max-w-2xl flex-col gap-5">
          <h1
            className="text-balance text-center font-display text-stone-100"
            style={{
              fontSize: "clamp(2.125rem, 1.4rem + 2.2vw, 2.75rem)",
              lineHeight: 1.5,
            }}
          >
            Which card is <span className="text-[#fbbf24]">worth it</span> for you?
          </h1>

          <ChatInput onSend={sendMessage} disabled={isLoading} />

          <div className="flex flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((text) => (
              <button
                key={text}
                onClick={() => sendMessage(text)}
                disabled={isLoading}
                data-testid="suggestion-chip"
                className="g-chip disabled:opacity-40"
              >
                {text}
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    // Same 672px column as the empty state so the layout doesn't shift
    // sideways on the first message.
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col px-4">
      <div className="flex items-center justify-end py-2">
        <button
          onClick={clearMessages}
          className="text-xs text-stone-600 hover:text-stone-400"
        >
          Clear
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="space-y-4 pb-4">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {isLoading && (
            <ThinkingIndicator
              stage={
                // The placeholder is empty until Claude's first token lands,
                // which is exactly when retrieval finished.
                messages[messages.length - 1]?.content ? "writing" : "retrieving"
              }
            />
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="pb-4 pt-2">
        <ChatInput onSend={sendMessage} disabled={isLoading} placeholder="Reply…" />
      </div>
    </div>
  )
}