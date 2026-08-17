"use client"

import { useEffect } from "react"
import { PanelRight } from "lucide-react"
import { usePanel } from "@/lib/panel-store"
import InsightPanel from "@/components/panel/InsightPanel"

export default function RightColumn() {
  const { answer, isStreaming, panelOpen, setPanelOpen } = usePanel()

  useEffect(() => {
    if (answer || isStreaming) setPanelOpen(true)
  }, [answer, isStreaming, setPanelOpen])

  if (!panelOpen) {
    return (
      <div className="hidden w-14 shrink-0 flex-col items-center border-l border-stone-900 py-5 xl:flex">
        <button
          onClick={() => setPanelOpen(true)}
          aria-label="Show the numbers"
          className="rounded-lg p-1.5 text-stone-600 transition-colors hover:bg-stone-900/60 hover:text-stone-300"
        >
          <PanelRight className="h-[22px] w-[22px]" strokeWidth={1.5} />
        </button>
        {answer && (
          <span className="mt-3 h-1.5 w-1.5 rounded-full bg-[#A78BFA]/70" />
        )}
      </div>
    )
  }

  return (
    <div className="hidden w-[368px] shrink-0 animate-[panel-in_260ms_cubic-bezier(0.16,1,0.3,1)] flex-col pl-[22px] xl:flex">
      <div className="min-h-0 flex-1">
        <InsightPanel />
      </div>
    </div>
  )
}