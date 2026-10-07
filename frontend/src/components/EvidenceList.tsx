import type { EvidenceOut, Triage } from '@/api/types'
import { Badge } from '@/components/ui/badge'

export function TriageBadge({ t }: { t: Triage | null }) {
  if (t === 'used') return <Badge tone="green">Used</Badge>
  if (t === 'excluded') return <Badge tone="red">Excluded</Badge>
  return <Badge tone="grey">Ignored</Badge>
}

export function EvidenceList({ items, onOpen }: { items: EvidenceOut[]; onOpen: (e: EvidenceOut) => void }) {
  if (!items.length) return <p className="text-sm text-zinc-500">No documents imported yet.</p>
  return (
    <ul className="divide-y divide-zinc-100">
      {items.map((e) => (
        <li key={e.id} className={`flex cursor-pointer items-start gap-3 py-2 hover:bg-zinc-50 ${e.parent_evidence_id ? 'pl-6' : ''}`} onClick={() => onOpen(e)}>
          <TriageBadge t={e.triage} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{e.filename} <span className="text-xs font-normal text-zinc-400">#{e.id}{e.doc_type ? ` · ${e.doc_type}` : ''}</span></div>
            <div className="text-xs text-zinc-600">{e.triage_reason}{e.policy_ref ? <span className="text-zinc-400"> ({e.policy_ref})</span> : null}</div>
          </div>
        </li>
      ))}
    </ul>
  )
}
