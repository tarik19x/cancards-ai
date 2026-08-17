"use client"

import { useEffect, useRef, useState } from "react"

const SWEEP = 270
const ARC_LEN = 358

type Props = {
  score: number // 0–100
  band: string
}

export default function ScoreGauge({ score, band }: Props) {
  const [pct, setPct] = useState(0)
  const [display, setDisplay] = useState(0)
  const raf = useRef<number>(0)

  useEffect(() => {
    const to = Math.min(Math.max(score, 0), 100) / 100
    const start = performance.now()

    const step = (now: number) => {
      const k = Math.min((now - start) / 900, 1)
      const eased = 1 - Math.pow(1 - k, 3)
      setPct(to * eased)
      setDisplay(Math.round(to * eased * 100))
      if (k < 1) raf.current = requestAnimationFrame(step)
      else setDisplay(score)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [score])

  const bandColor =
    score >= 75 ? "#6EE7B7" : score >= 40 ? "#F0A58C" : "#FB7185"

  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 200 160" className="w-full max-w-[220px]">
        <defs>
          <linearGradient id="score-arc" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#FB7185" />
            <stop offset="50%" stopColor="#F0A58C" />
            <stop offset="100%" stopColor="#6EE7B7" />
          </linearGradient>
          <filter id="score-glow">
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
          cx="100" cy="100" r="76" fill="none" stroke="url(#score-arc)"
          strokeWidth="13" strokeLinecap="round"
          strokeDasharray={`${ARC_LEN * pct} 478`}
          transform="rotate(135 100 100)"
          filter="url(#score-glow)"
        />

        <g style={{ transformOrigin: "100px 100px", transform: `rotate(${SWEEP * pct - 135}deg)` }}>
          <path d="M100 100 L100 40" stroke="#f4f2fa" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="100" cy="100" r="5" fill="#f4f2fa" />
          <circle cx="100" cy="100" r="2" fill="#000" />
        </g>

        <text x="100" y="128" textAnchor="middle" className="fill-stone-50 text-[30px] font-light">
          {display}
        </text>
        <text x="100" y="146" textAnchor="middle" className="fill-stone-500 text-[7.5px] tracking-[1px]">
          ESTIMATED SCORE
        </text>
      </svg>

      <span
        className="mt-1 rounded-full px-3 py-1 text-xs font-medium"
        style={{ color: bandColor, background: `${bandColor}1A`, boxShadow: `inset 0 0 0 1px ${bandColor}40` }}
      >
        {band}
      </span>
    </div>
  )
}