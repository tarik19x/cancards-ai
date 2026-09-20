const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"

// Mirrors backend/app/models.py. Kept next to the client rather than in types/index.ts
// because nothing outside the coach uses these.

export type CoachProfile = {
  card_count: number | null
  utilization: string | null
  history_length: string | null
  missed_payments: string | null
  recent_inquiries: number | null
  total_credit_limit_cad: number | null
  annual_income_cad: number | null
}

export type CoachFactor = {
  key: string
  label: string
  score: number
  max: number
  advice: string
}

export type CoachScore = {
  total: number
  band: string
  factors: CoachFactor[] // weakest first: that is the order advice should be read in
}

export type CoachTurn = {
  thread_id: string
  reply_markdown: string
  profile: CoachProfile
  missing_fields: string[]
  gave_score: boolean
  score: CoachScore | null
  score_message_index: number | null // where the score card belongs in the message list
  turn_count: number
}

export type CoachThread = {
  thread_id: string
  messages: { role: "user" | "assistant"; content: string }[]
  profile: CoachProfile
  missing_fields: string[]
  score: CoachScore | null
  score_message_index: number | null
  turn_count: number
}

// The five facts the estimate cannot be computed without, in the order the coach asks.
export const REQUIRED_FACTS: { key: keyof CoachProfile; label: string }[] = [
  { key: "card_count", label: "Cards" },
  { key: "utilization", label: "Balance" },
  { key: "history_length", label: "History" },
  { key: "missed_payments", label: "Payments" },
  { key: "recent_inquiries", label: "Applications" },
]

type StreamEvent =
  | { type: "token"; content: string }
  | ({ type: "done" } & CoachTurn)
  | { type: "error"; message?: string }

// Sends one message and reads the reply as it is written. onToken gets each chunk of the reply
// text the moment it arrives; the returned turn is the final structured result (facts, score).
// Same event shape as the Ask page's stream, read the same way: a line that is not a complete
// event is kept for the next chunk, because an event can be split across two network reads.
export async function streamCoachMessage(
  message: string,
  threadId: string | null,
  onToken: (chunk: string) => void,
  signal?: AbortSignal,
): Promise<CoachTurn> {
  const res = await fetch(`${BACKEND}/api/coach/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  })
  if (!res.ok) throw new Error(`The coach could not answer (${res.status})`)
  if (!res.body) throw new Error("The coach could not answer (streaming is not supported here)")

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let pending = ""
  let finished: CoachTurn | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    pending += decoder.decode(value, { stream: true })
    const lines = pending.split("\n")
    pending = lines.pop() ?? ""

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue
      let event: StreamEvent
      try {
        event = JSON.parse(line.slice("data: ".length)) as StreamEvent
      } catch {
        continue // a malformed line is skippable; an "error" event below must not be
      }
      if (event.type === "token") onToken(event.content)
      else if (event.type === "done") finished = event
      else if (event.type === "error") throw new Error(event.message ?? "The coach hit an error")
    }
  }
  if (!finished) throw new Error("The reply ended early")
  return finished
}

// Returns null for an unknown thread, so a stale id in the browser starts fresh
// instead of showing an error.
export async function fetchThread(
  threadId: string,
  signal?: AbortSignal,
): Promise<CoachThread | null> {
  const res = await fetch(`${BACKEND}/api/coach/thread/${encodeURIComponent(threadId)}`, { signal })
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`Could not load the conversation (${res.status})`)
  return res.json() as Promise<CoachThread>
}
