"use client"

import { useEffect } from "react"
import { PanelRight, X } from "lucide-react"
import { usePanel } from "@/lib/panel-store"
import InsightPanel from "@/components/panel/InsightPanel"

export default function RightColumn() {
  const { answer, panelOpen, setPanelOpen } = usePanel()

  // Open the panel by itself the first time an answer comes in.
  useEffect(() => {
    if (answer) setPanelOpen(true)
  }, [answer, setPanelOpen])

  // Closed: a thin strip with one button to open it.
  if (!panelOpen) {
    return (
      <div className="hidden w-12 shrink-0 flex-col items-center border-l border-stone-900 py-4 lg:flex">
        <button
          onClick={() => setPanelOpen(true)}
          aria-label="Show the numbers"
          className="text-stone-600 transition-colors hover:text-stone-300"
        >
          <PanelRight className="h-[18px] w-[18px]" strokeWidth={1.75} />
        </button>
      </div>
    )
  }

  // Open: the full panel with a close button on top.
  return (
    <div className="hidden w-[230px] shrink-0 flex-col border-l border-stone-900 lg:flex">
      <div className="flex justify-end px-3 pt-3">
        <button
          onClick={() => setPanelOpen(false)}
          aria-label="Hide the numbers"
          className="text-stone-600 transition-colors hover:text-stone-300"
        >
          <X className="h-4 w-4" strokeWidth={1.75} />
        </button>
      </div>
      <div className="min-h-0 flex-1">
        <InsightPanel />
      </div>
    </div>
  )
}