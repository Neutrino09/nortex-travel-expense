import type { ChainStepOut } from '@/api/types'

const tone: Record<string, string> = {
  approved: 'bg-green-100 text-green-800', pending: 'bg-amber-100 text-amber-800',
  returned: 'bg-red-100 text-red-800', rejected: 'bg-red-100 text-red-800', waiting: 'bg-zinc-100 text-zinc-600',
}

export function ChainPreview({ chain }: { chain: ChainStepOut[] }) {
  if (!chain.length) return <p className="text-xs text-zinc-500">No approvers yet.</p>
  return (
    <ol className="space-y-1.5 text-sm">
      {chain.map((s, i) => (
        <li key={`${s.seq}-${i}`}>
          <div className="flex items-center gap-2">
            <span className="w-14 rounded bg-zinc-100 px-1.5 py-0.5 text-center text-xs font-medium">{s.level}</span>
            <span>{s.approver_name}</span>
            {s.status && <span className={`rounded-full px-2 py-0.5 text-[11px] ${tone[s.status]}`}>{s.status}</span>}
          </div>
          {s.note && <div className="ml-16 text-xs text-zinc-500">{s.note}</div>}
          {s.remarks && <div className="ml-16 text-xs italic text-zinc-600">“{s.remarks}”</div>}
        </li>
      ))}
    </ol>
  )
}
