"use client"

import { useEffect, useRef } from "react"
import { useChat } from "@/hooks/useChat"
import MessageBubble from "@/components/chat/MessageBubble"
import ScenarioButtons from "@/components/chat/ScenarioButtons"
import ChatInput from "@/components/chat/ChatInput"

export default function ChatInterface() {
  const { messages, isLoading, sendMessage, clearMessages } = useChat()
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isLoading])

  const isEmpty = messages.length === 0

  return (
    <div className="flex h-[calc(100vh-10rem)] flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Ask about Canadian credit cards
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Get cited answers comparing {" "}
            <span className="font-medium text-teal-700">25+ Canadian cards</span>
            , tailored to your situation.
          </p>
        </div>
        {!isEmpty && (
          <button
            onClick={clearMessages}
            className="text-xs text-slate-400 underline hover:text-slate-600"
          >
            Clear
          </button>
        )}
      </div>

      {/* Scenario buttons — only shown when chat is empty */}
      {isEmpty && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-slate-400">Try asking:</p>
          <ScenarioButtons onSelect={sendMessage} disabled={isLoading} />
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-slate-100 bg-slate-50 p-4">
        {isEmpty ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-center text-sm text-slate-400">
              Your conversation will appear here.
              <br />
              Try one of the prompts above or type your own question.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}

            {/* Typing indicator */}
            {isLoading && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-tl-sm border border-slate-100 bg-white px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-1.5">
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:-0.3s]" />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300 [animation-delay:-0.15s]" />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-300" />
                  </div>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <ChatInput onSend={sendMessage} disabled={isLoading} />
    </div>
  )
}
