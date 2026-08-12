// Throwaway test. Delete when done.
// We copy the two functions' logic by importing the real file.

const spend = { groceries: 850, dining: 300, gas: 200, travel: 150, other: 400 }

// A card with a cap — BMO Cashback World Elite, simplified
const bmo = {
  annual_fee_cad: 120,
  rewards_detail: {
    grocery_stores: { rate: 5, unit: "percent_cashback", monthly_cap_cad: 500 },
    gas_ev_charging: { rate: 2, unit: "percent_cashback", monthly_cap_cad: 400 },
    everything_else: { rate: 1, unit: "percent_cashback" },
  },
}

// A points card — Amex Cobalt
const cobalt = {
  annual_fee_cad: 155.88,
  estimated_point_value_cents: 1.0,
  rewards_detail: {
    eat_and_drink: { rate: 5, unit: "points_per_dollar" },
    travel_transit_gas: { rate: 2, unit: "points_per_dollar" },
    everything_else: { rate: 1, unit: "points_per_dollar" },
  },
}

const { parseEarnRates, annualRewards, netValue } =
  await import("./src/lib/value-calc.ts")

for (const [name, card] of [["BMO", bmo], ["Cobalt", cobalt]]) {
  const rates = parseEarnRates(card)
  const { rows, total } = annualRewards(spend, rates)
  console.log(`\n=== ${name} ===`)
  rows.forEach((r) => console.log(`  ${r.label}: $${r.dollars.toFixed(0)} (${r.percent}%)`))
  console.log(`  earned: $${total.toFixed(0)}`)
  console.log(`  net:    $${netValue(total, card.annual_fee_cad).toFixed(0)}`)
}