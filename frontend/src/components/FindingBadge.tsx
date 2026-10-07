import { Badge } from '@/components/ui/badge'
import type { Finding } from '@/api/types'

const tone = { BLOCK: 'red', WARN: 'amber', DISALLOW: 'grey', INFO: 'blue' } as const

export function FindingBadge({ f }: { f: Finding }) {
  return (
    <div className={`flex items-start gap-2 text-xs ${f.severity === 'BLOCK' ? 'text-red-700' : f.severity === 'WARN' ? 'text-amber-700' : 'text-zinc-600'}`}>
      <Badge tone={tone[f.severity]}>{f.severity}</Badge>
      <span>{f.message}{f.policy_ref ? <span className="text-zinc-400"> ({f.policy_ref})</span> : null}</span>
    </div>
  )
}
