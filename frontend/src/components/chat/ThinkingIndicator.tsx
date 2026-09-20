"use client"

export default function ThinkingIndicator({
  stage,
  label: customLabel,
}: {
  stage?: "retrieving" | "writing"
  // The coach has no retrieval stage, so it passes its own wording instead.
  label?: string
}) {
  // Both stages are real: retrieval runs before the first token, generation after.
  const label =
    customLabel ?? (stage === "retrieving" ? "Searching relevant cards" : "Writing the answer")

  return (
    <div className="flex items-center gap-2.5 py-1">
      <span
        aria-hidden
        className="h-3 w-3 animate-spin rounded-full border-[1.5px] border-stone-700 border-t-stone-400"
      />
      <span className="font-display text-sm text-stone-500">{label}</span>
    </div>
  )
}
