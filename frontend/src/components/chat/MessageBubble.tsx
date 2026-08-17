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
    <div className="space-y-5">
      <div
        className={`text-[0.9375rem] leading-[1.75] ${
          message.error ? "text-red-400" : "text-stone-200"
        }`}
      >
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
            <Link
              key={card.card_id}
              href={`/cards/${card.card_id}`}
              className={
                i === 0
                  ? "group relative block overflow-hidden rounded-xl p-4 shadow-[inset_0_0_0_1px_#292524,inset_2px_0_0_#A78BFA] transition-shadow duration-300 hover:shadow-[inset_0_0_0_1px_#3a3448,inset_2px_0_0_#A78BFA]"
                  : "group relative block overflow-hidden rounded-xl p-4 shadow-[inset_0_0_0_1px_#292524] transition-shadow duration-300 hover:shadow-[inset_0_0_0_1px_#2e2a38]"
              }
              style={{
                background:
                  i === 0
                    ? "radial-gradient(120% 100% at 0% 0%, rgba(240,165,140,0.13) 0%, transparent 55%), radial-gradient(120% 100% at 100% 100%, rgba(167,139,250,0.16) 0%, transparent 55%), #0d0d10"
                    : "radial-gradient(120% 100% at 0% 0%, rgba(240,165,140,0.07) 0%, transparent 55%), radial-gradient(120% 100% at 100% 100%, rgba(167,139,250,0.08) 0%, transparent 55%), #0d0d10",
              }}
            >
              <div className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                style={{
                  background:
                    i === 0
                      ? "radial-gradient(120% 100% at 0% 0%, rgba(240,165,140,0.2) 0%, transparent 55%), radial-gradient(120% 100% at 100% 100%, rgba(167,139,250,0.24) 0%, transparent 55%)"
                      : "radial-gradient(120% 100% at 0% 0%, rgba(240,165,140,0.12) 0%, transparent 55%), radial-gradient(120% 100% at 100% 100%, rgba(167,139,250,0.14) 0%, transparent 55%)",
                }}
              />

              <div className="relative">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] font-sans text-[0.6875rem] font-semibold text-black">
                        {i + 1}
                      </span>
                      <h3 className="truncate text-[1.0625rem] text-stone-100">
                        {card.card_name}
                      </h3>
                    </div>
                    <p className="mt-1 pl-7 text-sm text-stone-500">
                      {card.annual_fee_cad === 0 ? "No annual fee" : `$${card.annual_fee_cad}/yr`}
                    </p>
                  </div>

                  <span className="shrink-0 text-sm text-stone-400 transition-colors group-hover:text-[#C4B5FD]">
                    Details →
                  </span>
                </div>

                <p className="mt-3 text-[0.9375rem] leading-relaxed text-stone-300">
                  {card.why}
                </p>

                {card.key_benefits?.length > 0 && (
                  <ul className="mt-3 space-y-1.5">
                    {card.key_benefits.map((benefit) => (
                      <li key={benefit} className="flex gap-2 text-sm text-stone-400">
                        <span className="text-[#A78BFA]">✓</span>
                        <span>{benefit}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Link>
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