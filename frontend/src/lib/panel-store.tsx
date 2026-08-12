"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react"

// How much the user spends per month, in dollars.
export type SpendProfile = {
  groceries: number
  dining: number
  gas: number
  travel: number
  other: number
}

// Facts about the latest answer. Feeds the small numbers at the panel bottom.
export type AnswerMeta = {
  topCardId: string | null
  topCardName: string | null
  sources: number        // how many different cards were cited
  chunks: number | null  // how many chunks retrieval returned
  latencyMs: number | null
}

type PanelValue = {
  spend: SpendProfile | null
  saveSpend: (s: SpendProfile) => void
  clearSpend: () => void
  answer: AnswerMeta | null
  setAnswer: (a: AnswerMeta | null) => void
  isStreaming: boolean
  setIsStreaming: (b: boolean) => void
  panelOpen: boolean
  setPanelOpen: (b: boolean) => void
}

const STORAGE_KEY = "cancards.spend"

const PanelContext = createContext<PanelValue | null>(null)

export function PanelProvider({ children }: { children: ReactNode }) {
  const [spend, setSpend] = useState<SpendProfile | null>(null)
  const [answer, setAnswer] = useState<AnswerMeta | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [panelOpen, setPanelOpen] = useState(false)

  // Load saved spending after the page loads.
  // Must be in useEffect — localStorage does not exist on the server.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) setSpend(JSON.parse(raw))
    } catch {
      // bad data saved, just ignore it
    }
  }, [])

  const saveSpend = useCallback((s: SpendProfile) => {
    setSpend(s)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
  }, [])

  const clearSpend = useCallback(() => {
    setSpend(null)
    localStorage.removeItem(STORAGE_KEY)
  }, [])

  return (
    <PanelContext.Provider
      value={{
        spend, saveSpend, clearSpend,
        answer, setAnswer,
        isStreaming, setIsStreaming,
        panelOpen, setPanelOpen,
      }}
    >
      {children}
    </PanelContext.Provider>
  )
}

// Small helper so components do not repeat the null check.
export function usePanel() {
  const ctx = useContext(PanelContext)
  if (!ctx) throw new Error("usePanel must be used inside <PanelProvider>")
  return ctx
}