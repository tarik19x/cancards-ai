"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type { ChatMessage } from "@/types"
import {
  fetchThread,
  streamCoachMessage,
  type CoachProfile,
  type CoachScore,
} from "@/lib/coach-api"

// Only the thread id is kept in the browser. The conversation itself lives on the
// server (Postgres), so a refresh reloads it from there rather than from local copies.
const THREAD_KEY = "cancards.coach.thread"

function readSavedThread(): string | null {
  try {
    return localStorage.getItem(THREAD_KEY)
  } catch {
    return null // storage blocked (private window): start fresh, nothing to restore
  }
}

function saveThread(id: string | null) {
  try {
    if (id) localStorage.setItem(THREAD_KEY, id)
    else localStorage.removeItem(THREAD_KEY)
  } catch {
    // Not fatal: the conversation still works, it just cannot survive a refresh.
  }
}

function toMessage(role: "user" | "assistant", content: string, error = false): ChatMessage {
  return { id: crypto.randomUUID(), role, content, timestamp: new Date(), error }
}

export function useCoachChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [profile, setProfile] = useState<CoachProfile | null>(null)
  const [score, setScore] = useState<CoachScore | null>(null)
  // Index of the coach message that delivered the estimate; the card is drawn after it,
  // so follow-up answers appear below the card instead of pushing it down.
  const [scoreIndex, setScoreIndex] = useState<number | null>(null)
  // isLoading: a request is in flight (input locked). isThinking: still no words to show yet,
  // which is when the "thinking" dots belong; once the reply starts arriving they go away.
  const [isLoading, setIsLoading] = useState(false)
  const [isThinking, setIsThinking] = useState(false)
  const [isRestoring, setIsRestoring] = useState(true)

  const threadRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  useEffect(() => () => abortRef.current?.abort(), [])

  // Pick up a saved conversation. Must be an effect: localStorage does not exist on the server.
  // Both branches go through a promise so that state is only set from a callback, never
  // synchronously in the effect body (which would cost an extra render on every visit).
  useEffect(() => {
    const controller = new AbortController()
    const saved = readSavedThread()
    const load = saved ? fetchThread(saved, controller.signal) : Promise.resolve(null)

    load
      .then((thread) => {
        if (!thread) {
          if (saved) saveThread(null) // the server no longer knows this id
          return
        }
        threadRef.current = thread.thread_id
        setMessages(thread.messages.map((m) => toMessage(m.role, m.content)))
        setProfile(thread.profile)
        setScore(thread.score)
        setScoreIndex(thread.score_message_index)
      })
      .catch(() => {
        // Server unreachable: show the intro; the saved id is kept for the next visit.
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsRestoring(false)
      })
    return () => controller.abort()
  }, [])

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || isLoading) return

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setMessages((prev) => [...prev, toMessage("user", trimmed)])
      setIsLoading(true)
      setIsThinking(true)
      // The reply bubble is created by the first chunk, not before: an empty bubble would
      // sit beside the thinking dots for the seconds it takes Claude to start.
      let replyId: string | null = null
      const onToken = (chunk: string) => {
        if (replyId === null) {
          const bubble = toMessage("assistant", chunk)
          replyId = bubble.id
          setMessages((prev) => [...prev, bubble])
          setIsThinking(false)
        } else {
          const id = replyId
          setMessages((prev) =>
            prev.map((m) => (m.id === id ? { ...m, content: m.content + chunk } : m)),
          )
        }
      }
      try {
        const turn = await streamCoachMessage(
          trimmed,
          threadRef.current,
          onToken,
          controller.signal,
        )
        threadRef.current = turn.thread_id
        saveThread(turn.thread_id)
        // The server's finished text is the one that was saved, so it has the last word.
        const id = replyId
        if (id === null) {
          setMessages((prev) => [...prev, toMessage("assistant", turn.reply_markdown)])
        } else {
          setMessages((prev) =>
            prev.map((m) => (m.id === id ? { ...m, content: turn.reply_markdown } : m)),
          )
        }
        setProfile(turn.profile)
        setScore(turn.score)
        setScoreIndex(turn.score_message_index)
      } catch (err) {
        if (controller.signal.aborted) return
        const detail = err instanceof Error ? err.message : "Something went wrong."
        setMessages((prev) => [
          ...prev,
          toMessage("assistant", `${detail}. Please try sending that again.`, true),
        ])
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false)
          setIsThinking(false)
        }
      }
    },
    [isLoading],
  )

  const restart = useCallback(() => {
    abortRef.current?.abort()
    threadRef.current = null
    saveThread(null)
    setMessages([])
    setProfile(null)
    setScore(null)
    setScoreIndex(null)
    setIsLoading(false)
    setIsThinking(false)
  }, [])

  return {
    messages,
    profile,
    score,
    scoreIndex,
    isLoading,
    isThinking,
    isRestoring,
    sendMessage,
    restart,
  }
}
