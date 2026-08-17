"use client"

import { usePanel } from "@/lib/panel-store"

function Metric({
  value,
  label,
  tone = "text-stone-200",
  glow,
}: {
  value: string
  label: string
  tone?: string
  glow?: boolean
}) {
  return (
    <div>
      <div
        className={`font-sans text-[1.75rem] font-medium leading-none ${tone}`}
        style={glow ? { textShadow: "0 0 18px rgba(251,191,36,0.3)" } : undefined}
      >
        {value}
      </div>
      <div className="mt-1.5 font-sans text-[13px] text-stone-500">{label}</div>
    </div>
  )
}

export default function MetricsStrip() {
  const { answer, isStreaming } = usePanel()

  // Nothing asked yet — render nothing. An empty panel shouldn't advertise
  // that it measured nothing.
  if (!answer && !isStreaming) return null

  // Dashes while streaming. A live-updating timer pulls attention to the wait.
  const dash = isStreaming || !answer

  return (
    <div className="mt-4">
      <h2 className="panel-title">How this answer was built</h2>
      <p className="panel-subtitle">Retrieval and generation stats</p>

      <div className="panel-card mt-3.5 px-[18px] py-4">
        <div className="grid grid-cols-3 gap-2.5">
          <Metric
            value={dash ? "—" : String(answer!.sources)}
            label="sources"
            tone="text-[#A78BFA]"
            glow={!dash}
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

      <p className="mt-3.5 font-sans text-[13px] leading-relaxed text-stone-500">
        Estimates use published earn rates.
      </p>
    </div>
  )
}