"use client"

import ScoreGauge from "@/components/coach/ScoreGauge"
import type { CoachScore } from "@/lib/coach-api"

// The number comes from the server's deterministic scorer, never from the language
// model, so this always agrees with the quiz for the same answers.
export default function CoachScoreCard({ score }: { score: CoachScore }) {
  // A factor at full marks needs no fixing; without this filter a perfect score still
  // gets a "Fix these first" box listing its strengths.
  const weakest = score.factors.filter((f) => f.score < f.max).slice(0, 2)

  return (
    <div className="space-y-4">
      <div className="panel-card flex flex-col items-center p-5 text-center">
        <ScoreGauge score={score.total} band={score.band} />
        <p className="mt-2 text-xs text-stone-600">
          Estimated from what you told me. Not a real bureau score.
        </p>
      </div>

      <div className="panel-card p-[18px]">
        <h2 className="font-sans text-[15px] font-medium text-stone-100">
          What&apos;s shaping the estimate
        </h2>
        <div className="mt-3.5 flex flex-col gap-3.5">
          {score.factors.map((f) => {
            const ratio = f.score / f.max
            const color = ratio >= 0.75 ? "#6EE7B7" : ratio >= 0.4 ? "#F0A58C" : "#FB7185"
            return (
              <div key={f.key}>
                <div className="mb-1.5 flex justify-between font-sans text-sm">
                  <span className="text-stone-300">{f.label}</span>
                  <span className="text-stone-500">
                    {f.score}/{f.max}
                  </span>
                </div>
                <div className="h-[7px] overflow-hidden rounded-full bg-[#1e1e24]">
                  <div
                    className="bar-fill h-[7px] rounded-full"
                    style={{ width: `${ratio * 100}%`, background: color }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {weakest.length > 0 && (
        <div className="rounded-2xl bg-gradient-to-br from-[#A78BFA]/[0.11] to-[#F0A58C]/[0.04] p-4 shadow-[inset_0_0_0_1px_rgba(167,139,250,0.22)]">
          <h2 className="font-sans text-[15px] font-medium text-stone-50">Fix these first</h2>
          <div className="mt-3 flex flex-col gap-3">
            {weakest.map((f) => (
              <p key={f.key} className="text-sm leading-relaxed text-stone-300">
                <span className="font-medium text-stone-100">{f.label}.</span> {f.advice}
              </p>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs leading-relaxed text-stone-600">
        For your real score, check{" "}
        <a
          href="https://www.equifax.ca"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#A78BFA] underline underline-offset-2"
        >
          Equifax
        </a>{" "}
        or{" "}
        <a
          href="https://www.transunion.ca"
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#A78BFA] underline underline-offset-2"
        >
          TransUnion
        </a>{" "}
        for free.
      </p>
    </div>
  )
}
