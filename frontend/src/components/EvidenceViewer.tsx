import { useQuery } from '@tanstack/react-query'
import { evidenceFileUrl } from '@/api/client'
import type { EvidenceOut } from '@/api/types'
import { Dialog } from '@/components/ui/dialog'
import { TriageBadge } from './EvidenceList'

// Click-through viewer: image evidence renders as <img>, email evidence as plain text.
export function EvidenceViewer({ evidence, onClose }: { evidence: EvidenceOut | null; onClose: () => void }) {
  const isEmail = evidence?.kind === 'email'
  const text = useQuery({
    queryKey: ['evidence-text', evidence?.id],
    enabled: !!evidence && isEmail,
    queryFn: async () => {
      const r = await fetch(evidenceFileUrl(evidence!.id), { credentials: 'same-origin' })
      if (!r.ok) throw new Error('Could not load document')
      return r.text()
    },
  })
  return (
    <Dialog open={!!evidence} onClose={onClose} title={evidence?.filename ?? ''} wide>
      {evidence && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            <TriageBadge t={evidence.triage} />
            <span className="text-zinc-600">{evidence.triage_reason}</span>
            {evidence.policy_ref && <span className="text-zinc-400">({evidence.policy_ref})</span>}
          </div>
          {isEmail ? (
            <pre className="whitespace-pre-wrap rounded-md bg-zinc-50 p-3 text-xs">{text.isLoading ? 'Loading…' : text.error ? text.error.message : text.data}</pre>
          ) : (
            <img src={evidenceFileUrl(evidence.id)} alt={evidence.filename} className="max-h-[70vh] w-full object-contain" />
          )}
        </div>
      )}
    </Dialog>
  )
}
