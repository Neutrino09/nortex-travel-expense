import { cn } from '@/lib/utils'

export function Tabs({ tabs, value, onChange }: {
  tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void
}) {
  return (
    <div className="mb-4 flex gap-1 border-b border-border">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={cn('-mb-px border-b-2 px-4 py-2 text-sm font-medium',
            value === t.id ? 'border-primary text-primary' : 'border-transparent text-zinc-500 hover:text-zinc-900')}>
          {t.label}
        </button>
      ))}
    </div>
  )
}
