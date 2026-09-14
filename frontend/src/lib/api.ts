import type { Card } from "@/types"

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"

// Both readers run in client components, so Next's `next: { revalidate }` never
// applied — it only works server-side. Dropped rather than left in place looking
// like caching that isn't happening. Move a caller to a server component to get
// it back.

// ─── Cards ───────────────────────────────────────────────────────────────────

export async function fetchCards(signal?: AbortSignal): Promise<Card[]> {
  const res = await fetch(`${BACKEND}/api/cards`, { signal })
  if (!res.ok) throw new Error(`Failed to fetch cards (${res.status})`)
  return res.json() as Promise<Card[]>
}

export async function fetchCard(cardId: string, signal?: AbortSignal): Promise<Card> {
  const res = await fetch(`${BACKEND}/api/cards/${cardId}`, { signal })
  if (!res.ok) throw new Error(`Card "${cardId}" not found (${res.status})`)
  return res.json() as Promise<Card>
}
