"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  MessageSquare,
  CreditCard,
  Columns2,
  Compass,
  Settings,
} from "lucide-react"

// Each destination owns a colour — wayfinding, not the product's voice.
// The content area (chat, buttons, price) stays lavender regardless of
// which section you're in.
const LINKS = [
  { href: "/", label: "Ask", icon: MessageSquare, hex: "#A78BFA", tint: "rgba(167,139,250," },
  { href: "/cards", label: "Cards", icon: CreditCard, hex: "#F0A58C", tint: "rgba(240,165,140," },
  { href: "/compare", label: "Compare", icon: Columns2, hex: "#7DD3FC", tint: "rgba(125,211,252," },
  { href: "/coach", label: "Coach", icon: Compass, hex: "#6EE7B7", tint: "rgba(110,231,183," },
]

export default function SideRail() {
  const pathname = usePathname()

  function isActive(href: string) {
    return href === "/" ? pathname === "/" : pathname.startsWith(href)
  }

  return (
    <aside
      data-testid="side-rail"
      className="flex w-[84px] shrink-0 flex-col items-center gap-3 py-5"
    >
      <Link href="/" className="group mb-2 flex flex-col items-center gap-1.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] text-xs font-semibold text-black">
          C
        </span>
        <span className="text-[13px] text-stone-500 transition-colors group-hover:text-stone-300">
          CanCards
        </span>
      </Link>

      {LINKS.map(({ href, label, icon: Icon, hex, tint }) => {
        const active = isActive(href)
        return (
          <Link
            key={href}
            href={href}
            data-testid={`nav-${label.toLowerCase()}`}
            aria-current={active ? "page" : undefined}
            className="group flex w-16 flex-col items-center gap-1.5 rounded-xl py-2.5 transition-colors"
            style={active ? { backgroundColor: `${tint}0.12)` } : undefined}
          >
            <Icon
              className="h-[21px] w-[21px] transition-colors"
              style={{ color: active ? hex : "#3f3b4d" }}
              strokeWidth={1.6}
            />
            <span
              className="text-[13px] transition-colors"
              style={{ color: active ? "#f4f2fa" : "#5b5470" }}
            >
              {label}
            </span>
          </Link>
        )
      })}

      <Link
        href="/settings"
        data-testid="nav-settings"
        className="mt-auto flex flex-col items-center gap-1.5"
      >
        <Settings
          className="h-[21px] w-[21px]"
          style={{ color: pathname.startsWith("/settings") ? "#A78BFA" : "#332e42" }}
          strokeWidth={1.6}
        />
        <span
          className="text-[13px]"
          style={{ color: pathname.startsWith("/settings") ? "#f4f2fa" : "#332e42" }}
        >
          Settings
        </span>
      </Link>
    </aside>
  )
}