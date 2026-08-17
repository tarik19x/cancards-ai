"use client"

import { useEffect, useRef, useState } from "react"

const MAX = 3000        // gauge ceiling in dollars
const SWEEP = 270       // degrees of needle travel
const ARC_LEN = 358     // dash length at full sweep

type Props = {
  value: number | null
  streaming: boolean
}

export default function ValueGauge({ value, streaming }: Props) {
  const [pct, setPct] = useState(0)
  const [display, setDisplay] = useState(0)
  const raf = useRef<number>(0)

  useEffect(() => {
    // Idle sweep during generation — signals work in progress, not
    // actual progress. We can't know how far along the model is.
    if (streaming) {
      let t = 0
      const id = setInterval(() => {
        t += 0.06
        const p = 0.3 + Math.sin(t) * 0.22
        setPct(p)
        setDisplay(Math.round((p * MAX) / 50) * 50)
      }, 40)
      return () => clearInterval(id)
    }

    if (value === null) {
      setPct(0)
      setDisplay(0)
      return
    }

    // Settle on the real figure.
    const from = pct
    const to = Math.min(Math.max(value, 0) / MAX, 1)
    const start = performance.now()

    const step = (now: number) => {
      const k = Math.min((now - start) / 900, 1)
      const eased = 1 - Math.pow(1 - k, 3)
      const p = from + (to - from) * eased
      setPct(p)
      setDisplay(Math.round(p * MAX))
      if (k < 1) raf.current = requestAnimationFrame(step)
      else setDisplay(value)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
    // pct is intentionally omitted — including it restarts the tween
    // on every frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, streaming])

  return (
    <svg viewBox="0 0 200 160" className="w-full">
      <defs>
        <linearGradient id="gauge-arc" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="55%" stopColor="#e879c7" />
          <stop offset="100%" stopColor="#f0a58c" />
        </linearGradient>
        <filter id="gauge-glow">
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <circle
        cx="100" cy="100" r="76" fill="none" stroke="#1a1622"
        strokeWidth="13" strokeLinecap="round"
        strokeDasharray="358 120" transform="rotate(135 100 100)"
      />
      <circle
        cx="100" cy="100" r="76" fill="none" stroke="url(#gauge-arc)"
        strokeWidth="13" strokeLinecap="round"
        strokeDasharray={`${ARC_LEN * pct} 478`}
        transform="rotate(135 100 100)"
        filter="url(#gauge-glow)"
      />

      <g style={{ transformOrigin: "100px 100px", transform: `rotate(${SWEEP * pct - 135}deg)` }}>
        <path d="M100 100 L100 40" stroke="#f4f2fa" strokeWidth="2.5" strokeLinecap="round" />
        <circle cx="100" cy="100" r="5" fill="#f4f2fa" />
        <circle cx="100" cy="100" r="2" fill="#000" />
      </g>

      <text x="100" y="132" textAnchor="middle" className="fill-stone-50 text-[26px] font-light">
        ${display.toLocaleString("en-CA")}
      </text>
      <text x="100" y="146" textAnchor="middle" className="fill-stone-500 text-[7.5px] tracking-[1px]">
        NET PER YEAR
      </text>
    </svg>
  )
}