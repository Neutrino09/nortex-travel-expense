import type { TimelineEvent } from '@/api/types'
import { Card } from '@/components/ui/card'
import { relativeTime, statusLabel } from '@/lib/helpers'
import { formatDate } from '@/lib/format'

export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <Card>
      <h3 className="mb-3 text-sm font-semibold">Timeline</h3>
      {events.length === 0 && <p className="text-sm text-zinc-500">No activity yet.</p>}
      <ol className="space-y-3 border-l border-zinc-200 pl-4">
        {events.map((e) => (
          <li key={e.id} className="relative">
            <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-primary" />
            <div className="text-sm">
              <span className="font-medium">{e.actor_name}</span> {statusLabel(e.action).toLowerCase()}
              {e.to_status && <span className="text-zinc-500"> → {statusLabel(e.to_status)}</span>}
            </div>
            {e.remarks && <div className="text-sm italic text-zinc-600">“{e.remarks}”</div>}
            <div className="text-xs text-zinc-400" title={formatDate(e.at)}>{relativeTime(e.at)} · {formatDate(e.at)} · {e.entity_id}</div>
          </li>
        ))}
      </ol>
    </Card>
  )
}
