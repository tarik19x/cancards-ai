interface ScenarioButtonsProps {
  onSelect: (question: string) => void
  disabled?: boolean
}

const SCENARIOS = [
  "Which card has no foreign transaction fee?",
  "Best no-fee card for everyday cashback?",
  "Best card for dining and groceries?",
  "Compare cards for someone who travels frequently",
  "Which card is best for Aeroplan points?",
]

export default function ScenarioButtons({ onSelect, disabled }: ScenarioButtonsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {SCENARIOS.map((q) => (
        <button
          key={q}
          onClick={() => onSelect(q)}
          disabled={disabled}
          className="rounded-full border border-teal-200 bg-teal-50 px-3 py-1 text-xs font-medium text-teal-700 transition-colors hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  )
}
