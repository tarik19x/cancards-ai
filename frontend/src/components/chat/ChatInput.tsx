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
    <div
      className="rounded-[20px] bg-[#0d0d10] p-3.5
        shadow-[0_4px_20px_rgba(0,0,0,0.5),inset_0_0_0_1px_#1e1e24]
        transition-shadow duration-200
        hover:shadow-[0_4px_20px_rgba(0,0,0,0.5),inset_0_0_0_1px_#2a2a32]
        focus-within:shadow-[0_4px_24px_rgba(167,139,250,0.08),inset_0_0_0_1px_#A78BFA]
        hover:focus-within:shadow-[0_4px_24px_rgba(167,139,250,0.08),inset_0_0_0_1px_#A78BFA]"
    >
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={2}
        placeholder={placeholder ?? "How can I help with your cards today?"}
        className="min-h-[3.25rem] w-full resize-none bg-transparent pl-1.5 pt-1.5
          text-base text-stone-100 outline-none placeholder:text-stone-600"
      />

      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Add"
            className="flex h-8 w-8 items-center justify-center rounded-lg
              text-stone-500 transition-colors hover:bg-stone-800/60 hover:text-stone-200"
          >
            <Plus className="h-5 w-5" strokeWidth={1.5} />
          </button>
          <button
            type="button"
            aria-label="Attach file"
            className="flex h-8 w-8 items-center justify-center rounded-lg
              text-stone-500 transition-colors hover:bg-stone-800/60 hover:text-stone-200"
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
            bg-gradient-to-br from-[#F0A58C] to-[#A78BFA] text-black
            transition-opacity disabled:opacity-30"
        >
          <ArrowUp className="h-4 w-4" strokeWidth={2.25} />
        </button>
      </div>
    </div>
  )
}