"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import RecommendationCard from "@/components/chat/RecommendationCard"
import type { ChatMessage } from "@/types"

interface Props {
  message: ChatMessage
}

export default function MessageBubble({ message }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-tr-sm bg-teal-600 px-4 py-2.5 text-sm text-white">
          {message.content}
        </div>
      </div>
    )
  }

  // Assistant message
  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[95%] space-y-3">
        {/* Answer text */}
        <div
          className={[
            "rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed",
            message.error
              ? "bg-red-50 text-red-700"
              : "bg-white shadow-sm border border-slate-100 text-slate-700",
          ].join(" ")}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              strong: ({ children }) => (
                <strong className="font-semibold text-slate-900">{children}</strong>
              ),
              ul: ({ children }) => (
                <ul className="mb-2 ml-4 list-disc space-y-0.5">{children}</ul>
              ),
              li: ({ children }) => <li>{children}</li>,
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>

        {/* Card recommendations */}
        {message.response && message.response.recommended_cards.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Recommended Cards
            </p>
            {message.response.recommended_cards.map((card, i) => (
              <RecommendationCard key={card.card_id} card={card} rank={i + 1} />
            ))}
          </div>
        )}

        {/* Citations */}
        {message.response && message.response.citations.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-slate-400">Sources:</span>
            {message.response.citations.map((c, i) => (
              <span
                key={`${c.card_id}-${i}`}
                className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500"
              >
                {c.card_name} · {c.section}
              </span>
            ))}
          </div>
        )}

        {/* Confidence note */}
        {message.response?.confidence_notes && (
          <p className="text-xs italic text-slate-400">
            {message.response.confidence_notes}
          </p>
        )}
      </div>
    </div>
  )
}
