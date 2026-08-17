import CardGrid from "@/components/cards/CardGrid"

export const metadata = {
  title: "Browse Cards — CanCards AI",
  description: "Browse and filter all Canadian credit cards in our database.",
}

export default function CardsPage() {
  return (
    <div className="h-full overflow-x-hidden overflow-y-auto">
      <div className="mx-auto max-w-[820px] px-7 py-8">
        <h1 className="font-display text-[28px] text-stone-100">Browse cards</h1>
        <p className="mt-1.5 text-sm text-stone-400">
          Explore all credit cards in our database. Click any card to see full details.
        </p>
        <div className="mt-6">
          <CardGrid />
        </div>
      </div>
    </div>
  )
}