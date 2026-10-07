import { Link, useNavigate } from 'react-router-dom'
import { useRequests } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { PayoutLine } from '@/components/SummaryCard'
import { formatDate, formatINR } from '@/lib/format'
import { daysSince, statusLabel } from '@/lib/helpers'

// "Where's my money" — one card per travel request.
export default function Dashboard() {
  const reqs = useRequests()
  const navigate = useNavigate()
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <Button onClick={() => navigate('/requests/new')}>New travel request</Button>
      </div>
      {reqs.isLoading && <p className="text-zinc-500">Loading…</p>}
      {reqs.error && <p className="text-red-600">{reqs.error.message}</p>}
      {reqs.data?.length === 0 && <Card>No travel requests yet.</Card>}
      <div className="grid gap-4 md:grid-cols-2">
        {reqs.data?.map((r) => (
          <Card key={r.id} className="space-y-2">
            <div className="flex items-center justify-between">
              <Link to={`/requests/${r.id}`} className="font-semibold text-primary hover:underline">{r.id}</Link>
              <Badge tone="green">{r.stage.step_label}</Badge>
            </div>
            <div className="text-sm">{r.purpose || '—'} · {r.destination_city}</div>
            <div className="text-xs text-zinc-500">{formatDate(r.from_date)} – {formatDate(r.to_date)} · Estimate {formatINR(r.estimate_total_paise)} · {statusLabel(r.status)}</div>
            {r.stage.waiting_on_name && (
              <div className="text-sm text-amber-700">Waiting on {r.stage.waiting_on_name} since {daysSince(r.stage.waiting_since)} days</div>
            )}
            <PayoutLine p={r.expected_payout} />
            <div className="flex gap-2 pt-1">
              <Link to={`/requests/${r.id}`}><Button variant="outline">Request</Button></Link>
              {r.settlement_id && <Link to={`/settlements/${r.settlement_id}`}><Button variant="outline">Settlement</Button></Link>}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
