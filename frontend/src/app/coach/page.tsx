"use client"

import { useState } from "react"
import Link from "next/link"
import { scoreCredit, type CreditProfile } from "@/lib/credit-score"
import ScoreGauge from "@/components/coach/ScoreGauge"

// Choice-driven steps share one shape. cardCount and creditLimit are
// numeric and handled separately since they take typed input, not pills.
type ChoiceStep = {
  key: "utilization" | "historyLength" | "missedPayments" | "recentInquiries"
  question: string
  helper: string
  options: { value: string; label: string }[]
}

const CHOICE_STEPS: ChoiceStep[] = [
  {
    key: "utilization",
    question: "How much of your available credit do you typically carry?",
    helper: "Compare your usual balance to your total limit, not what you pay off each month.",
    options: [
      { value: "under10", label: "Under 10%" },
      { value: "10to30", label: "10–30%" },
      { value: "30to50", label: "30–50%" },
      { value: "50to75", label: "50–75%" },
      { value: "over75", label: "Over 75%" },
    ],
  },
  {
    key: "historyLength",
    question: "How long have you had your oldest credit card?",
    helper: "The account you opened first, even if you barely use it now.",
    options: [
      { value: "under1", label: "Under 1 year" },
      { value: "1to3", label: "1–3 years" },
      { value: "3to7", label: "3–7 years" },
      { value: "over7", label: "7+ years" },
    ],
  },
  {
    key: "missedPayments",
    question: "In the last two years, have you missed a payment?",
    helper: "Even one missed payment counts — be honest, this is what it's actually for.",
    options: [
      { value: "never", label: "Never" },
      { value: "rarely", label: "Once or twice" },
      { value: "sometimes", label: "A few times" },
      { value: "often", label: "Often" },
    ],
  },
  {
    key: "recentInquiries",
    question: "How many new cards or loans have you applied for in the last 12 months?",
    helper: "Each application shows up as a hard inquiry on your file.",
    options: [
      { value: "0", label: "None" },
      { value: "1", label: "One" },
      { value: "2", label: "Two" },
      { value: "3", label: "Three or more" },
    ],
  },
]

// step 0 = card count, step 1 = credit limit, steps 2-5 = CHOICE_STEPS
const TOTAL_STEPS = 2 + CHOICE_STEPS.length

type Answers = Partial<CreditProfile>

export default function CoachPage() {
  const [stage, setStage] = useState<"intro" | "quiz" | "results">("intro")
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<Answers>({})

  function next() {
    if (step < TOTAL_STEPS - 1) setStep(step + 1)
    else setStage("results")
  }

  function back() {
    if (step > 0) setStep(step - 1)
    else setStage("intro")
  }

  function restart() {
    setAnswers({})
    setStep(0)
    setStage("intro")
  }

  const complete = answers as CreditProfile
  const result =
    stage === "results" &&
    typeof complete.cardCount === "number" &&
    typeof complete.creditLimit === "number" &&
    complete.utilization &&
    complete.historyLength &&
    complete.missedPayments &&
    typeof complete.recentInquiries === "number"
      ? scoreCredit(complete)
      : null

    // ── Intro ──
  if (stage === "intro") {
    return (
      <div className="flex h-full flex-col items-center justify-center overflow-y-auto px-4">
        <div className="w-full max-w-xl text-center">
          <p className="g-label uppercase">Credit coach</p>
          <h1 className="mt-2 font-display text-3xl leading-snug text-stone-50 sm:text-4xl">
            Most people can name their bank balance to the dollar.
            <br />
            <span className="bg-gradient-to-r from-[#F0A58C] to-[#A78BFA] bg-clip-text text-transparent">
              Almost nobody can explain their credit score.
            </span>
          </h1>
          <p className="mt-4 text-sm leading-relaxed text-stone-400">
            Six quick questions about your cards, limits, and payment habits.
            We&apos;ll estimate where you stand, show you exactly what&apos;s
            pulling the number down, and what to fix first. A card
            recommendation comes at the end, if it&apos;s actually useful.
          </p>
          <button
            onClick={() => setStage("quiz")}
            className="cta-glow mt-7 inline-flex items-center gap-2 rounded-xl bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-6 py-3 text-sm font-semibold text-black"
          >
            Check my credit health →
          </button>
          <p className="mt-4 text-xs text-stone-600">
            Nothing here is a real credit score. For that, check{" "}
            <a href="https://www.equifax.ca" target="_blank" rel="noopener noreferrer" className="text-[#A78BFA] underline underline-offset-2">Equifax</a>{" "}
            or{" "}
            <a href="https://www.transunion.ca" target="_blank" rel="noopener noreferrer" className="text-[#A78BFA] underline underline-offset-2">TransUnion</a>{" "}
            for free.
          </p>
        </div>
      </div>
    )
  }

  // ── Quiz ──
  if (stage === "quiz") {
    const choiceIndex = step - 2

    return (
      <div className="mx-auto flex h-full w-full max-w-xl flex-col justify-center overflow-y-auto px-4">
        {/* progress */}
        <div className="mb-8 flex gap-1.5">
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <div
              key={i}
              className={
                i <= step
                  ? "h-1 flex-1 rounded-full bg-gradient-to-r from-[#F0A58C] to-[#A78BFA]"
                  : "h-1 flex-1 rounded-full bg-[#1e1e24]"
              }
            />
          ))}
        </div>

        {step === 0 && (
          <NumberStep
            question="How many credit cards do you currently have open?"
            helper="Include cards you rarely use."
            value={answers.cardCount}
            onChange={(n) => setAnswers({ ...answers, cardCount: n })}
            onNext={next}
          />
        )}

        {step === 1 && (
          <NumberStep
            question="What's your combined credit limit across all cards?"
            helper="A rough total is fine — add up the limits on your statements."
            prefix="$"
            value={answers.creditLimit}
            onChange={(n) => setAnswers({ ...answers, creditLimit: n })}
            onNext={next}
          />
        )}

        {choiceIndex >= 0 && choiceIndex < CHOICE_STEPS.length && (
          <ChoiceStepView
            step={CHOICE_STEPS[choiceIndex]}
            value={answers[CHOICE_STEPS[choiceIndex].key] as string | number | undefined}
            onSelect={(value) => {
              const key = CHOICE_STEPS[choiceIndex].key
              const parsed = key === "recentInquiries" ? Number(value) : value
              setAnswers({ ...answers, [key]: parsed })
              next()
            }}
          />
        )}

        <button
          onClick={back}
          className="mt-6 self-start text-sm text-stone-600 transition-colors hover:text-stone-400"
        >
          ← Back
        </button>
      </div>
    )
  }

  // ── Results ──
  if (!result) {
    // shouldn't happen via the normal flow, but guards against a direct
    // stage jump with incomplete answers
    return (
      <div className="flex h-full items-center justify-center px-4">
        <p className="text-sm text-stone-500">Something's missing — let's start over.</p>
        <button onClick={restart} className="ml-2 text-sm text-[#A78BFA] underline">
          Restart
        </button>
      </div>
    )
  }

  const weakest = result.factors.slice(0, 2)

  return (
    <div className="h-full overflow-x-hidden overflow-y-auto">
      <div className="mx-auto max-w-xl space-y-6 px-4 py-10">
        <div className="flex flex-col items-center text-center">
          <p className="g-label uppercase">Your results</p>
          <div className="mt-4">
            <ScoreGauge score={result.total} band={result.band} />
          </div>
          <p className="mt-2 text-xs text-stone-600">
            Estimated from what you entered — not a real bureau score.
          </p>
        </div>

        <div className="panel-card grid grid-cols-2 gap-4 p-4 text-center">
          <div>
            <p className="text-xs text-stone-500">Cards open</p>
            <p className="mt-1 text-lg text-stone-100">{complete.cardCount}</p>
          </div>
          <div>
            <p className="text-xs text-stone-500">Total limit</p>
            <p className="mt-1 text-lg text-stone-100">
              ${complete.creditLimit.toLocaleString("en-CA")}
            </p>
          </div>
        </div>

        <div className="panel-card p-[18px]">
          <h2 className="font-sans text-[15px] font-medium text-stone-100">
            What's shaping the estimate
          </h2>
          <div className="mt-3.5 flex flex-col gap-3.5">
            {result.factors.map((f) => {
              const ratio = f.score / f.max
              const color = ratio >= 0.75 ? "#6EE7B7" : ratio >= 0.4 ? "#F0A58C" : "#FB7185"
              return (
                <div key={f.key}>
                  <div className="mb-1.5 flex justify-between font-sans text-sm">
                    <span className="text-stone-300">{f.label}</span>
                    <span className="text-stone-500">{f.score}/{f.max}</span>
                  </div>
                  <div className="h-[7px] overflow-hidden rounded-full bg-[#1e1e24]">
                    <div
                      className="bar-fill h-[7px] rounded-full"
                      style={{ width: `${ratio * 100}%`, background: color }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="rounded-2xl bg-gradient-to-br from-[#A78BFA]/[0.11] to-[#F0A58C]/[0.04] p-4 shadow-[inset_0_0_0_1px_rgba(167,139,250,0.22)]">
          <h2 className="font-sans text-[15px] font-medium text-stone-50">
            Fix these first
          </h2>
          <div className="mt-3 flex flex-col gap-3">
            {weakest.map((f) => (
              <p key={f.key} className="text-sm leading-relaxed text-stone-300">
                <span className="font-medium text-stone-100">{f.label}.</span>{" "}
                {f.advice}
              </p>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 pt-2">
          <button onClick={restart} className="text-sm text-stone-600 hover:text-stone-400">
            Retake
          </button>
          <Link
            href="/"
            className="cta-glow inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-4 py-2.5 text-sm font-semibold text-black"
          >
            Ask which card fits →
          </Link>
        </div>
      </div>
    </div>
  )
}

function NumberStep({
  question,
  helper,
  prefix,
  value,
  onChange,
  onNext,
}: {
  question: string
  helper: string
  prefix?: string
  value?: number
  onChange: (n: number) => void
  onNext: () => void
}) {
  return (
    <div>
      <h2 className="font-display text-2xl text-stone-50">{question}</h2>
      <p className="mt-2 text-sm text-stone-500">{helper}</p>

      <div className="mt-5 flex items-center gap-2 rounded-xl bg-[#0d0d10] px-4 py-3 shadow-[inset_0_0_0_1px_#1e1e24] focus-within:shadow-[inset_0_0_0_1px_#A78BFA]">
        {prefix && <span className="text-stone-500">{prefix}</span>}
        <input
          inputMode="numeric"
          value={value ?? ""}
          onChange={(e) => {
            const n = Number(e.target.value.replace(/[^0-9]/g, ""))
            onChange(isNaN(n) ? 0 : n)
          }}
          placeholder="0"
          className="w-full bg-transparent text-lg text-stone-100 outline-none placeholder:text-stone-700"
        />
      </div>

      <button
        onClick={onNext}
        disabled={value === undefined}
        className="cta-glow mt-5 rounded-xl bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] px-5 py-2.5 text-sm font-semibold text-black disabled:opacity-30"
      >
        Continue
      </button>
    </div>
  )
}

function ChoiceStepView({
  step,
  value,
  onSelect,
}: {
  step: ChoiceStep
  value?: string | number
  onSelect: (value: string) => void
}) {
  return (
    <div>
      <h2 className="font-display text-2xl text-stone-50">{step.question}</h2>
      <p className="mt-2 text-sm text-stone-500">{step.helper}</p>

      <div className="mt-5 flex flex-col gap-2">
        {step.options.map((opt) => {
          const active = String(value) === opt.value
          return (
            <button
              key={opt.value}
              onClick={() => onSelect(opt.value)}
              className={
                active
                  ? "rounded-xl bg-[#A78BFA] px-4 py-3 text-left text-sm font-semibold text-black"
                  : "rounded-xl px-4 py-3 text-left text-sm text-stone-300 shadow-[inset_0_0_0_1px_#1e1e24] transition-colors hover:shadow-[inset_0_0_0_1px_#A78BFA]"
              }
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}