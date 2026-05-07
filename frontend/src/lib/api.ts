import type { Card, AnswerResponse } from "@/types"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"

// ─── Cards ───────────────────────────────────────────────────────────────────

export async function fetchCards(): Promise<Card[]> {
  const res = await fetch(`${BACKEND}/api/cards`, {
    next: { revalidate: 3600 }, // cache for 1 hour
  })
  if (!res.ok) throw new Error(`Failed to fetch cards (${res.status})`)
  return res.json() as Promise<Card[]>
}

export async function fetchCard(cardId: string): Promise<Card> {
  const res = await fetch(`${BACKEND}/api/cards/${cardId}`, {
    next: { revalidate: 3600 },
  })
  if (!res.ok) throw new Error(`Card "${cardId}" not found (${res.status})`)
  return res.json() as Promise<Card>
}

// ─── Ask ─────────────────────────────────────────────────────────────────────

export async function askQuestion(question: string): Promise<AnswerResponse> {
  const res = await fetch(`${BACKEND}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`Ask failed (${res.status}): ${detail}`)
  }
  return res.json() as Promise<AnswerResponse>
}
