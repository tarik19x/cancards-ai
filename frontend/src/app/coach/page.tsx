"use client"

import { Fragment, useEffect, useRef } from "react"
import Link from "next/link"
import { useCoachChat } from "@/hooks/useCoachChat"
import MessageBubble from "@/components/chat/MessageBubble"
import ChatInput from "@/components/chat/ChatInput"
import ThinkingIndicator from "@/components/chat/ThinkingIndicator"
import FactProgress from "@/components/coach/FactProgress"
import CoachScoreCard from "@/components/coach/CoachScoreCard"

// Sent as the user's first message so the conversation opens with a real turn, and the
// transcript reads naturally: they asked, the coach answered with its first question.
const OPENING_MESSAGE = "Hi, I'd like to check my credit health."

export default function CoachPage() {
  const {
    messages,
    profile,
    score,
    scoreIndex,
    isLoading,
    isThinking,
    isRestoring,
    sendMessage,
    restart,
  } = useCoachChat()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Smooth scrolling on every arriving word would lag behind the text; follow it instantly
    // while a reply is being written and glide only once it is done.
    bottomRef.current?.scrollIntoView({ behavior: isLoading ? "auto" : "smooth" })
  }, [messages, isLoading, score])

  // Conversations saved before the card position was recorded have no index; their score
  // came from the last coach message, so the card goes there.
  // Saved conversations from before the index existed have none, and a reply the user
  // walked away from mid-stream was never saved, so its index points past the end.
  // Either way the card goes after the last message rather than disappearing.
  const cardAfter =
    scoreIndex !== null && scoreIndex < messages.length ? scoreIndex : messages.length - 1

  // Blank rather than a flash of the intro while a saved conversation loads.
  if (isRestoring) return <div className="h-full" />

  // ── Intro ──
  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center overflow-y-auto px-4">
        <div className="w-full max-w-xl text-center">
          <p className="g-label uppercase">Credit coach</p>
          <h1 className="mt-2 text-balance font-display text-3xl leading-snug text-stone-50 sm:text-4xl">
            Chat with the coach to understand{" "}
            <span className="bg-gradient-to-r from-[#F0A58C] to-[#A78BFA] bg-clip-text text-transparent">
              and improve your credit score
            </span>
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-stone-400">
            Five quick questions, asked one at a time in plain conversation. You&apos;ll get an
            estimate of where you stand, what&apos;s pulling it down, and what to fix first.
          </p>
          <button
            onClick={() => sendMessage(OPENING_MESSAGE)}
            disabled={isLoading}
            data-testid="start-coach-chat"
            className="cta-glow mt-7 inline-flex items-center gap-2 rounded-xl bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-6 py-3 text-sm font-semibold text-black disabled:opacity-40"
          >
            Let&apos;s chat →
          </button>
          <p className="mt-4 text-xs text-stone-600">
            Prefer tapping through?{" "}
            <Link href="/coach/quiz" className="text-[#A78BFA] underline underline-offset-2">
              Take the quick quiz
            </Link>
            . Nothing here is a real credit score; for that, check Equifax or TransUnion.
          </p>
        </div>
      </div>
    )
  }

  // ── Conversation ──
  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col px-4">
      <div className="flex items-center justify-between py-3">
        <FactProgress profile={profile} />
        <button onClick={restart} className="text-xs text-stone-600 hover:text-stone-400">
          Start over
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="space-y-4 pb-4">
          {messages.map((msg, i) => (
            <Fragment key={msg.id}>
              <MessageBubble message={msg} />
              {score && i === cardAfter && <CoachScoreCard score={score} />}
            </Fragment>
          ))}

          {isThinking && <ThinkingIndicator label="The coach is thinking" />}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="pb-4 pt-2">
        {score && (
          <div className="mb-2 flex items-center justify-between gap-3 text-xs">
            <span className="text-stone-600">Ask me anything about improving your score.</span>
            <Link href="/" className="text-[#A78BFA] underline underline-offset-2">
              Which card fits? &rarr;
            </Link>
          </div>
        )}
        <ChatInput
          onSend={sendMessage}
          disabled={isLoading}
          placeholder={score ? "Ask a follow-up question" : "Type your answer"}
        />
      </div>
    </div>
  )
}
