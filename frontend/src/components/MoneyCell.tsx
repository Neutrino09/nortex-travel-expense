import { useEffect, useState } from 'react'
import { formatINR, rupeesToPaise } from '@/lib/format'
import { Input } from '@/components/ui/input'

export function MoneyCell({ paise, className }: { paise: number; className?: string }) {
  return <span className={`tabular-nums ${className ?? ''}`}>{formatINR(paise)}</span>
}

// Rupee text input that commits integer paise on blur.
export function MoneyInput({ paise, onCommit, disabled, className, placeholder }: {
  paise: number; onCommit: (p: number) => void; disabled?: boolean; className?: string; placeholder?: string
}) {
  const fmt = (p: number) => (p / 100).toFixed(2)
  const [text, setText] = useState(fmt(paise))
  useEffect(() => setText(fmt(paise)), [paise])
  return (
    <Input className={`text-right tabular-nums ${className ?? ''}`} value={text} disabled={disabled} placeholder={placeholder}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => { const p = rupeesToPaise(text); setText(fmt(p)); if (p !== paise) onCommit(p) }} />
  )
}
