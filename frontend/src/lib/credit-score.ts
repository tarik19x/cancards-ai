// Self-reported estimate only — this is not a real credit score. A real
// score comes from Equifax/TransUnion pulling actual account history;
// nothing typed into a form can reproduce that honestly. Weights below
// loosely mirror the public FICO factor breakdown (payment history ~35%,
// utilization ~30%, history length ~15%, new credit ~10%, mix ~10%) for
// educational shape, not precision.

export type Utilization = "under10" | "10to30" | "30to50" | "50to75" | "over75"
export type HistoryLength = "under1" | "1to3" | "3to7" | "over7"
export type MissedPayments = "never" | "rarely" | "sometimes" | "often"

export type CreditProfile = {
  cardCount: number
  creditLimit: number
  utilization: Utilization
  historyLength: HistoryLength
  missedPayments: MissedPayments
  recentInquiries: 0 | 1 | 2 | 3
}

export type Factor = {
  key: string
  label: string
  score: number
  max: number
  advice: string
}

export type ScoreResult = {
  total: number // 0–100
  band: "Needs work" | "Fair" | "Good" | "Very good" | "Excellent"
  factors: Factor[] // sorted weakest first — that's the advice order
}

function scoreUtilization(u: Utilization): Factor {
  const table: Record<Utilization, [number, string]> = {
    under10: [30, "Utilization is already low — this isn't costing you anything."],
    "10to30": [24, "Under 30% is the usual target. Pushing toward 10% would help further."],
    "30to50": [15, "Balances above 30% of your limit start pulling the score down noticeably."],
    "50to75": [7, "This is a heavy load on your limit. Paying it down is the single fastest lever you have."],
    over75: [2, "Running this close to the limit is the biggest thing hurting you right now."],
  }
  const [score, advice] = table[u]
  return { key: "utilization", label: "Credit utilization", score, max: 30, advice }
}

function scoreHistory(h: HistoryLength): Factor {
  const table: Record<HistoryLength, [number, string]> = {
    under1: [3, "History is still short — this improves on its own with time, nothing to actively fix."],
    "1to3": [7, "Still building. Keep your oldest card open even if you stop using it."],
    "3to7": [11, "Solid length. Avoid closing your oldest account — that's the one doing the most work."],
    over7: [15, "Long history is working in your favour here."],
  }
  const [score, advice] = table[h]
  return { key: "history", label: "Length of credit history", score, max: 15, advice }
}

function scoreMissed(m: MissedPayments): Factor {
  const table: Record<MissedPayments, [number, string]> = {
    never: [35, "A clean payment record is the single heaviest factor — this is your strongest area."],
    rarely: [22, "One or two slips are recoverable, but even occasional late payments carry real weight."],
    sometimes: [10, "This is likely the main thing holding the score back. Autopay for at least the minimum removes the risk entirely."],
    often: [0, "This is the top priority. Everything else matters less until payments are consistently on time."],
  }
  const [score, advice] = table[m]
  return { key: "payments", label: "Payment history", score, max: 35, advice }
}

function scoreInquiries(n: 0 | 1 | 2 | 3): Factor {
  const table: Record<number, [number, string]> = {
    0: [10, "No recent applications — nothing dragging you down here."],
    1: [7, "One inquiry is minor and fades within a year."],
    2: [4, "A couple of recent applications add up. Space out any future ones."],
    3: [0, "Several applications in a short window reads as risk to lenders. Hold off on new applications for a while."],
  }
  const [score, advice] = table[n]
  return { key: "inquiries", label: "Recent applications", score, max: 10, advice }
}

function scoreMix(cardCount: number): Factor {
  let score: number
  let advice: string
  if (cardCount === 0) {
    score = 2
    advice = "No open cards means no history being built. A single no-fee card is the easiest starting point."
  } else if (cardCount === 1) {
    score = 6
    advice = "One card works, but a second with a different limit gives lenders more to evaluate."
  } else if (cardCount <= 4) {
    score = 10
    advice = "This is a healthy range — nothing to change here."
  } else if (cardCount === 5) {
    score = 7
    advice = "Getting a little wide. Not harmful, just more to manage."
  } else {
    score = 4
    advice = "This many open cards can look like risk, even with good management. Consider whether all of them are still earning their keep."
  }
  return { key: "mix", label: "Number of cards", score, max: 10, advice }
}

function bandFor(total: number): ScoreResult["band"] {
  if (total >= 90) return "Excellent"
  if (total >= 75) return "Very good"
  if (total >= 60) return "Good"
  if (total >= 40) return "Fair"
  return "Needs work"
}

export function scoreCredit(profile: CreditProfile): ScoreResult {
  const factors = [
    scoreMissed(profile.missedPayments),
    scoreUtilization(profile.utilization),
    scoreHistory(profile.historyLength),
    scoreInquiries(profile.recentInquiries),
    scoreMix(profile.cardCount),
  ]

  const total = Math.round(factors.reduce((sum, f) => sum + f.score, 0))

  // weakest ratio first — that's the order advice should be read in
  factors.sort((a, b) => a.score / a.max - b.score / b.max)

  return { total, band: bandFor(total), factors }
}