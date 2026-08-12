"use client"

import { useState, type KeyboardEvent } from "react"
import { Plus, Paperclip, ArrowUp } from "lucide-react"

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export default function ChatInput({ onSend, disabled, placeholder }: Props) {
  const [value, setValue] = useState("")

  function handleSend() {
    if (!value.trim() || disabled) return
    onSend(value.trim())
    setValue("")
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    // Edge is an inset ring + drop shadow instead of a border. A border can't
    // animate alongside the shadow on hover/focus without a visible jump.
    <div
      className="rounded-[20px] bg-[#131110] p-3.5
        shadow-[0_4px_20px_rgba(0,0,0,0.35),inset_0_0_0_1px_#292524]
        transition-shadow duration-200
        hover:shadow-[0_4px_20px_rgba(0,0,0,0.35),inset_0_0_0_1px_#44403c]
        focus-within:shadow-[0_4px_24px_rgba(0,0,0,0.5),inset_0_0_0_1px_#57534e]
        hover:focus-within:shadow-[0_4px_24px_rgba(0,0,0,0.5),inset_0_0_0_1px_#57534e]"
    >
      {/* two-line min-height so the box doesn't grow on the first keystroke */}
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={2}
        placeholder={placeholder ?? "How can I help with your cards today?"}
        className="min-h-[3.25rem] w-full resize-none bg-transparent pl-1.5 pt-1.5
          font-display text-base leading-relaxed text-stone-100 outline-none
          placeholder:text-stone-500"
      />

      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Add"
            className="flex h-8 w-8 items-center justify-center rounded-lg
              text-stone-400 transition-colors hover:bg-stone-800/60 hover:text-stone-200"
          >
            <Plus className="h-5 w-5" strokeWidth={1.5} />
          </button>
          {/* TODO: wire to a hidden file input when uploads land */}
          <button
            type="button"
            aria-label="Attach file"
            className="flex h-8 w-8 items-center justify-center rounded-lg
              text-stone-400 transition-colors hover:bg-stone-800/60 hover:text-stone-200"
          >
            <Paperclip className="h-[18px] w-[18px]" strokeWidth={1.5} />
          </button>
        </div>

        <button
          type="button"
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          aria-label="Send"
          className="flex h-8 w-8 items-center justify-center rounded-[10px]
            bg-[#fbbf24] text-[#1c1207] transition-opacity disabled:opacity-30"
        >
          <ArrowUp className="h-4 w-4" strokeWidth={2.25} />
        </button>
      </div>
    </div>
  )
}