"use client"

import { useEffect, useState } from "react"
import ValueGauge from "@/components/panel/ValueGauge"
import { Pencil, X } from "lucide-react"
import { usePanel } from "@/lib/panel-store"
import {
  annualRewards, breakEvenSpend, money, netValue, parseEarnRates,
  type EarnRate,
} from "@/lib/value-calc"
import SpendBars from "@/components/panel/SpendBars"
import SpendForm from "@/components/panel/SpendForm"
import MetricsStrip from "@/components/panel/MetricsStrip"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"

export default function InsightPanel() {
  const { answer, spend, setPanelOpen, isStreaming } = usePanel()
  const [editing, setEditing] = useState(false)
  const [rates, setRates] = useState<EarnRate[]>([])
  const [fee, setFee] = useState(0)

  useEffect(() => {
    if (!answer?.topCardId) {
      setRates([])
      setFee(0)
      return
    }
    let cancelled = false

    fetch(`${BACKEND}/api/cards/${answer.topCardId}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((card) => {
        if (cancelled || !card) return
        setRates(parseEarnRates(card))
        setFee(Number(card.annual_fee_cad ?? 0))
      })
      .catch(() => {
        // card lookup failed — panel just hides the breakdown
      })

    return () => {
      cancelled = true
    }
  }, [answer?.topCardId])

  const hasRates = rates.length > 0
  const calc = spend && hasRates ? annualRewards(spend, rates) : null
  const net = calc ? netValue(calc.total, fee) : null
  const breakEven = hasRates ? breakEvenSpend(fee, rates) : null

  return (
    <div
      className="flex h-full flex-col overflow-y-auto py-5 pr-5"
      data-testid="insight-panel"
    >
      {editing ? (
        <div className="panel-card p-[18px]">
          <SpendForm onDone={() => setEditing(false)} />
        </div>
      ) : !answer ? (
        <>
          <h2 className="panel-title">Your numbers</h2>
          <p className="panel-subtitle">
            The value breakdown appears here once you ask something.
          </p>

          <div className="panel-card mt-3.5 p-[18px]">
            <div className="flex flex-col gap-4">
              {[52, 40, 46].map((w, i) => (
                <div key={i}>
                  <div className="h-2.5 rounded bg-[#221e1c]" style={{ width: `${w}%` }} />
                  <div className="mt-2.5 h-[9px] rounded bg-[#1a1715]" />
                </div>
              ))}
            </div>
          </div>
        </>
      ) : !hasRates ? (
        <>
          <h2 className="panel-title">Top match</h2>
          <p className="panel-subtitle">{answer.topCardName}</p>

          <div className="panel-card mt-3.5 p-[18px]">
            <p className="font-sans text-sm leading-relaxed text-stone-400">
              No reward-rate data for this card yet, so the value breakdown
              is unavailable.
            </p>
          </div>
        </>
      ) : !spend ? (
        <>
          <h2 className="panel-title">What this card earns</h2>
          <p className="panel-subtitle">{answer.topCardName}</p>

          <div className="panel-card relative mt-3.5 p-[18px]">
            <button
              onClick={() => setPanelOpen(false)}
              aria-label="Hide panel"
              className="absolute right-3.5 top-3.5 text-stone-600 transition-colors hover:text-stone-300"
            >
              <X className="h-[18px] w-[18px]" strokeWidth={1.5} />
            </button>

            <h3 className="font-sans text-[15px] font-medium text-stone-200">
              Earn rates
            </h3>

            <div className="mt-3.5 flex flex-col gap-3.5">
              {rates.slice(0, 5).map((r) => (
                <div key={r.category}>
                  <div className="mb-1.5 flex items-baseline justify-between font-sans text-sm">
                    <span className="capitalize text-stone-300">{r.category}</span>
                    <span className="text-stone-50">{r.percent}%</span>
                  </div>
                  <div className="h-[9px] overflow-hidden rounded-full bg-[#221e1c]">
                    <div
                      className="bar-fill h-[9px] rounded-full bg-gradient-to-r from-[#F0A58C] to-[#A78BFA] shadow-[0_0_12px_rgba(167,139,250,0.4)]"
                      style={{
                        width: `${(r.percent / Math.max(...rates.map((x) => x.percent))) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {breakEven !== null && (
              <p className="mt-4 border-t border-[#221e1c] pt-3.5 font-sans text-sm leading-relaxed text-stone-400">
                Breaks even on the {money(fee)} fee at {money(breakEven)} of
                yearly spend.
              </p>
            )}
          </div>

          <div className="mt-3.5 rounded-2xl bg-gradient-to-br from-[#A78BFA]/[0.11] to-[#F0A58C]/[0.04] p-4 shadow-[inset_0_0_0_1px_rgba(167,139,250,0.22)]">
            <h3 className="font-sans text-[15px] font-medium text-stone-50">
              See your real number
            </h3>
            <p className="mt-1.5 font-sans text-sm leading-relaxed text-stone-400">
              Tell us what you actually spend and we&apos;ll work out what this
              card returns you.
            </p>
            <button
              onClick={() => setEditing(true)}
              className="cta-glow mt-3.5 inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-4 py-2.5 font-sans text-sm font-semibold text-black"
            >
              <Pencil className="h-[15px] w-[15px]" strokeWidth={2} />
              Add your spending
            </button>
          </div>
        </>
      ) : (
        <>
          <h2 className="panel-title">What this card earns you</h2>
          <p className="panel-subtitle">Based on your monthly spending</p>

          <div className="panel-card relative mt-3.5 px-[18px] py-5">
            <button
              onClick={() => setPanelOpen(false)}
              aria-label="Hide panel"
              className="absolute right-3.5 top-3.5 text-stone-600 transition-colors hover:text-stone-300"
            >
              <X className="h-[18px] w-[18px]" strokeWidth={1.5} />
            </button>

            <div className="border-b border-[#221e1c] pb-[18px] text-center">
              <ValueGauge value={net} streaming={isStreaming} />
              <p className="mt-1 font-sans text-sm text-stone-400">
                after the {money(fee)} fee
              </p>
            </div>

            <div className="pt-4">
              <h3 className="font-sans text-[15px] font-medium text-stone-200">
                Where it comes from
              </h3>
              <div className="mt-3.5">
                <SpendBars rows={calc!.rows} amounts={spend} />
              </div>
            </div>
          </div>

          <div className="mt-3.5 rounded-2xl bg-gradient-to-br from-[#A78BFA]/[0.11] to-[#F0A58C]/[0.04] p-4 shadow-[inset_0_0_0_1px_rgba(167,139,250,0.22)]">
            <h3 className="font-sans text-[15px] font-medium text-stone-50">
              Get a sharper number
            </h3>
            <p className="mt-1.5 font-sans text-sm leading-relaxed text-stone-400">
              Update what you spend and we&apos;ll recalculate against all 50
              cards.
            </p>
            <button
              onClick={() => setEditing(true)}
              className="cta-glow mt-3.5 inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-4 py-2.5 font-sans text-sm font-semibold text-black"
            >
              <Pencil className="h-[15px] w-[15px]" strokeWidth={2} />
              Edit spend
            </button>
          </div>
        </>
      )}

      <MetricsStrip />
    </div>
  )
}