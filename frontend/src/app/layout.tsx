import type { Metadata } from "next"
import { Geist, Geist_Mono, Newsreader } from "next/font/google"
import AppShell from "@/components/layout/AppShell"
import { PanelProvider } from "@/lib/panel-store"
import "./globals.css"

// Kept for UI chrome that shouldn't be serif — inputs, small numeric labels.
const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] })
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] })

// Primary face. Set as the body default in globals.css so no column can
// silently fall back to sans.
const display = Newsreader({
  variable: "--font-display-src",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
})

export const metadata: Metadata = {
  title: "CanCards AI — Canadian credit card answers",
  description:
    "Ask about Canadian credit cards and get cited answers with the numbers worked out.",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${display.variable} bg-[#0c0a09] antialiased`}
      >
        {/* PanelProvider shares answer + spend data between
            the chat (middle) and the insight panel (right). */}
        <PanelProvider>
          <AppShell>{children}</AppShell>
        </PanelProvider>
      </body>
    </html>
  )
}