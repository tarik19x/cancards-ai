"use client"

import { useState, type KeyboardEvent } from "react"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

interface Props {
  onSend: (message: string) => void
  disabled?: boolean
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState("")

  function handleSend() {
    if (!value.trim() || disabled) return
    onSend(value.trim())
    setValue("")
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex gap-2">
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about Canadian credit cards..."
        disabled={disabled}
        className="flex-1 rounded-full border-slate-200 bg-white px-4 focus-visible:ring-teal-500"
      />
      <Button
        onClick={handleSend}
        disabled={disabled || !value.trim()}
        className="rounded-full bg-teal-600 px-5 hover:bg-teal-700"
      >
        {disabled ? (
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white" />
          </span>
        ) : (
          "Send"
        )}
      </Button>
    </div>
  )
}
