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

// Every destination in the app. Add new pages here.
const LINKS = [
  { href: "/", label: "Ask", icon: MessageSquare },
  { href: "/cards", label: "Cards", icon: CreditCard },
  { href: "/compare", label: "Compare", icon: Columns2 },
  { href: "/coach", label: "Coach", icon: Compass },
]

export default function SideRail() {
  const pathname = usePathname()

  // "/" must match exactly, other links match their section.
  function isActive(href: string) {
    return href === "/" ? pathname === "/" : pathname.startsWith(href)
  }

  return (
    <aside
      data-testid="side-rail"
      className="flex w-[70px] shrink-0 flex-col items-center gap-4 border-r border-stone-900 py-4"
    >
      {/* logo */}
      <Link href="/" className="flex flex-col items-center gap-1 pb-1">
        <span className="flex h-[19px] w-[19px] items-center justify-center rounded-[5px] border border-amber-500 text-[10px] text-amber-500">
          C
        </span>
        <span className="text-[11px] text-stone-400">CanCards</span>
      </Link>

      {/* main links */}
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = isActive(href)
        return (
          <Link
            key={href}
            href={href}
            data-testid={`nav-${label.toLowerCase()}`}
            aria-current={active ? "page" : undefined}
            className={[
              "flex w-full flex-col items-center gap-1 border-l-2 py-1.5 transition-colors",
              active
                ? "border-l-amber-500"
                : "border-l-transparent hover:border-l-stone-700",
            ].join(" ")}
          >
            <Icon
              className={active ? "h-[18px] w-[18px] text-amber-400" : "h-[18px] w-[18px] text-stone-500"}
              strokeWidth={1.75}
            />
            <span className={active ? "text-[11px] text-stone-50" : "text-[11px] text-stone-400"}>
              {label}
            </span>
          </Link>
        )
      })}

      {/* settings sits at the bottom */}
      <Link
        href="/settings"
        data-testid="nav-settings"
        className="mt-auto flex flex-col items-center gap-1"
      >
        <Settings
          className={
            pathname.startsWith("/settings")
              ? "h-[18px] w-[18px] text-amber-400"
              : "h-[18px] w-[18px] text-stone-600"
          }
          strokeWidth={1.75}
        />
        <span className="text-[11px] text-stone-600">Settings</span>
      </Link>
    </aside>
  )
}