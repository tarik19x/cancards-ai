"use client"

import Link from "next/link"
import ReactMarkdown from "react-markdown"
import type { ChatMessage } from "@/types"

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl bg-stone-800 px-4 py-2.5 text-[0.9375rem] text-stone-200">
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
        className={`text-[0.9375rem] leading-[1.75] ${
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
              className={
                i === 0
                  ? "rounded-xl bg-[#0d0d10] py-4 pl-4 pr-4 shadow-[inset_2px_0_0_#A78BFA]"
                  : "rounded-xl bg-[#0d0d10] p-4 shadow-[inset_0_0_0_1px_#1e1e24]"
              }
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-[1.0625rem] text-stone-100">
                    {card.card_name}
                  </h3>
                  <p className="mt-1 text-sm text-stone-500">
                    {card.annual_fee_cad === 0 ? "No annual fee" : `$${card.annual_fee_cad}/yr`}
                    {" · "}
                    {card.why.split(".")[0]}
                  </p>
                </div>
                <span className={i === 0 ? "shrink-0 text-[15px] text-[#A78BFA]" : "shrink-0 text-[15px] text-stone-500"}>
                  ${/* net value goes here once wired to the calculator */ ""}
                </span>
              </div>
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
              className="rounded-md bg-stone-800/60 px-2 py-0.5 text-xs text-stone-400 transition-colors hover:bg-stone-800"
            >
              {cite.card_name} · {cite.section}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}