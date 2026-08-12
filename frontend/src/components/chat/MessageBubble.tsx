"use client"

import Link from "next/link"
import ReactMarkdown from "react-markdown"
import type { ChatMessage } from "@/types"

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-stone-800 px-4 py-2.5 font-display text-[1.0625rem] text-stone-200">
          {message.content}
        </div>
      </div>
    )
  }

  const res = message.response

  return (
    // No container on assistant turns — the answer sits on the page, the way
    // a document does. Only the user's words get a surface.
    <div className="space-y-5">
      <div
        className={`font-display text-[1.0625rem] leading-[1.75] ${
          message.error ? "text-red-400" : "text-stone-200"
        }`}
      >
        {/* Backend returns markdown; without a renderer the ** literals leak
            into the answer. Preflight strips list and emphasis styling, so
            each element is restyled here. */}
        <ReactMarkdown
          components={{
            p: ({ children }) => <p className="mb-4 last:mb-0">{children}</p>,
            strong: ({ children }) => (
              <strong className="font-semibold text-stone-50">{children}</strong>
            ),
            em: ({ children }) => <em className="italic">{children}</em>,
            ul: ({ children }) => <ul className="mb-4 space-y-1.5 pl-5 last:mb-0">{children}</ul>,
            ol: ({ children }) => <ol className="mb-4 space-y-1.5 pl-5 last:mb-0">{children}</ol>,
            li: ({ children }) => <li className="list-disc marker:text-stone-600">{children}</li>,
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>

      {res?.recommended_cards && res.recommended_cards.length > 0 && (
        <div className="space-y-2.5">
          <p className="g-label uppercase">Recommended</p>

          {res.recommended_cards.map((card, i) => (
            <div
              key={card.card_id}
              // Top pick gets the amber edge; the rest stay quiet so the
              // ranking reads without comparing numbers.
              className={`rounded-xl bg-stone-900/40 p-4 ${
                i === 0
                  ? "shadow-[inset_0_0_0_1px_#292524,inset_2px_0_0_#fbbf24]"
                  : "shadow-[inset_0_0_0_1px_#292524]"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#fbbf24] text-[0.6875rem] font-semibold text-[#1c1207]">
                      {i + 1}
                    </span>
                    <h3 className="truncate font-display text-[1.0625rem] text-stone-100">
                      {card.card_name}
                    </h3>
                  </div>
                  <p className="mt-1 pl-7 text-sm text-stone-500">
                    {card.annual_fee_cad === 0
                      ? "No annual fee"
                      : `$${card.annual_fee_cad}/yr`}
                  </p>
                </div>

                <Link
                  href={`/cards/${card.card_id}`}
                  className="shrink-0 rounded-lg px-2.5 py-1 text-sm text-stone-400 transition-colors hover:bg-stone-800/60 hover:text-stone-200"
                >
                  Details →
                </Link>
              </div>

              <p className="mt-3 font-display text-[0.9375rem] leading-relaxed text-stone-300">
                {card.why}
              </p>

              {card.key_benefits?.length > 0 && (
                <ul className="mt-3 space-y-1.5">
                  {card.key_benefits.map((benefit) => (
                    <li key={benefit} className="flex gap-2 text-sm text-stone-400">
                      <span className="text-amber-400">✓</span>
                      <span>{benefit}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}

      {res?.citations && res.citations.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm text-stone-600">Sources</span>
          {res.citations.map((cite, i) => (
            <span
              key={`${cite.card_id}-${cite.section}-${i}`}
              className="rounded-md bg-stone-800/60 px-2 py-0.5 text-[0.6875rem] text-stone-400"
            >
              {cite.card_name} · {cite.section}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}