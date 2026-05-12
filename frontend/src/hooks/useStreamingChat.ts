"use client"

import { useState, useCallback } from "react"
import type { ChatMessage, AnswerResponse } from "@/types"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"
const CARDS_DELIMITER = "===CARDS==="

export function useStreamingChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(async (question: string) => {
    const trimmed = question.trim()
    if (!trimmed || isLoading) return

    // Add user message
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmed,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)
    setError(null)

    // Placeholder assistant message that we'll mutate as tokens arrive
    const assistantId = crypto.randomUUID()
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", timestamp: new Date() },
    ])

    try {
      const res = await fetch(`${BACKEND}/api/ask/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed }),
      })

      if (!res.ok) throw new Error(`Request failed: ${res.status} ${res.statusText}`)
      if (!res.body) throw new Error("Response body is null — streaming not supported")

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let accumulated = ""    // Full text from backend (includes delimiters and JSON)
      let buffer = ""         // Partial line buffer — SSE events can split across chunks

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""   // Keep partial line for the next iteration

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          const jsonStr = line.slice("data: ".length).trim()
          if (!jsonStr) continue

          try {
            const event = JSON.parse(jsonStr)

            if (event.type === "token") {
              accumulated += event.content
              // Show only the text portion — never the delimiter or JSON
              const displayText = accumulated.includes(CARDS_DELIMITER)
                ? accumulated.split(CARDS_DELIMITER)[0]
                : accumulated
              setMessages((prev) =>
                prev.map((msg) => (msg.id === assistantId ? { ...msg, content: displayText } : msg))
              )
            } else if (event.type === "done" && event.response) {
              const response = event.response as AnswerResponse
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantId
                    ? {
                        ...msg,
                        content: response.answer_markdown,
                        response,
                        timestamp: new Date(response.timestamp),
                      }
                    : msg
                )
              )
            } else if (event.type === "error") {
              throw new Error(event.message)
            }
          } catch {
            // Malformed events at chunk boundaries — skip and continue
          }
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong."
      setError(msg)
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, content: `Error: ${msg}`, error: true } : m))
      )
    } finally {
      setIsLoading(false)
    }
  }, [isLoading])

  const clearMessages = useCallback(() => {
    setMessages([])
    setError(null)
  }, [])

  return { messages, isLoading, error, sendMessage, clearMessages }
}
