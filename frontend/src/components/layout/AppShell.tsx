import SideRail from "@/components/layout/SideRail"
import RightColumn from "@/components/panel/RightColumn"

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      <SideRail />

      {/* middle column. min-w-0 stops long text from stretching the layout. */}
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {children}
      </main>

      <RightColumn />
    </div>
  )
}