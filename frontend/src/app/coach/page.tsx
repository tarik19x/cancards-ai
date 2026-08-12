import Link from "next/link"

export default function CoachPage() {
  return (
    <div className="mx-auto flex h-full w-full max-w-2xl flex-col justify-center px-4">
      <p className="g-label">Credit coach</p>
      <h1 className="mt-1 font-display text-3xl text-stone-50">
        Answer a few questions, get one recommendation
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-stone-400">
        Walks through spending, fee comfort, and travel habits, then narrows
        50 cards down to one. Not wired up yet.
      </p>
      <Link
        href="/"
        className="mt-6 inline-block w-fit rounded-lg bg-[#fbbf24] px-4 py-2 text-sm text-[#1c1207]"
      >
        Ask a question instead
      </Link>
    </div>
  )
}