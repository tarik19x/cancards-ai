"use client"

import { REQUIRED_FACTS, type CoachProfile } from "@/lib/coach-api"

// Shows which of the five facts the coach has, so the user can see the conversation is
// converging on a score rather than asking questions forever.
export default function FactProgress({ profile }: { profile: CoachProfile | null }) {
  const known = REQUIRED_FACTS.filter((f) => profile?.[f.key] != null).length

  return (
    <div className="flex items-center gap-3" aria-label={`${known} of ${REQUIRED_FACTS.length} facts gathered`}>
      <div className="flex gap-1">
        {REQUIRED_FACTS.map((f) => (
          <span
            key={f.key}
            title={f.label}
            className={
              profile?.[f.key] != null
                ? "h-1.5 w-6 rounded-full bg-gradient-to-r from-[#F0A58C] to-[#A78BFA]"
                : "h-1.5 w-6 rounded-full bg-[#1e1e24]"
            }
          />
        ))}
      </div>
      <span className="text-xs text-stone-600">
        {known} of {REQUIRED_FACTS.length}
      </span>
    </div>
  )
}
