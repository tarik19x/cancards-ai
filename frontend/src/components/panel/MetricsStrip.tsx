"use client"

import { usePanel } from "@/lib/panel-store"

// One number with a label under it.
function Metric({
  value,
  label,
  tone = "text-stone-200",
}: {
  value: string
  label: string
  tone?: string
}) {
  return (
    <div>
      <div className={`font-display text-[17px] leading-tight tracking-tight ${tone}`}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-stone-500">{label}</div>
    </div>
  )
}

export default function MetricsStrip() {
  const { answer, isStreaming } = usePanel()

  // Nothing asked yet — show nothing.
  if (!answer && !isStreaming) return null

  // While the answer is coming in, show dashes. A live timer pulls the eye.
  const dash = isStreaming || !answer

  return (
    <div className="mt-auto border-t border-[#1f1b19] pt-4">
      <p className="g-label">Behind this answer</p>
      <div className="mt-2.5 grid grid-cols-3 gap-2">
        <Metric
          value={dash ? "—" : String(answer!.sources)}
          label="sources"
          tone="text-amber-400"
        />
        <Metric
          value={dash || answer!.chunks === null ? "—" : String(answer!.chunks)}
          label="chunks"
        />
        <Metric
          value={
            dash || answer!.latencyMs === null
              ? "—"
              : `${(answer!.latencyMs / 1000).toFixed(1)}s`
          }
          label="response"
        />
      </div>
    </div>
  )
}