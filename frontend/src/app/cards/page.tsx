import CardGrid from "@/components/cards/CardGrid"

export const metadata = {
  title: "Browse Cards — CanCards AI",
  description: "Browse and filter all Canadian credit cards in our database.",
}

export default function CardsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Browse Cards</h1>
        <p className="mt-1 text-sm text-slate-500">
          Explore all credit cards in our database. Click any card to see full details.
        </p>
      </div>
      <CardGrid />
    </div>
  )
}
