import { Link, useNavigate, useParams } from 'react-router-dom'
import { useCreateSettlement, useMe, useRequest, useResubmitRequest } from '@/api/client'
import type { RequestOut } from '@/api/types'
import { ChainPreview } from '@/components/ChainPreview'
import { Stepper } from '@/components/Stepper'
import { Timeline } from '@/components/Timeline'
import { PayoutLine } from '@/components/SummaryCard'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, Td, Th } from '@/components/ui/table'
import { formatDate, formatINR } from '@/lib/format'
import { statusLabel } from '@/lib/helpers'

export function RequestBody({ r }: { r: RequestOut }) {
  const navigate = useNavigate()
  const me = useMe()
  const createSettlement = useCreateSettlement()
  const resubmit = useResubmitRequest(r.id)
  const mine = me.data?.emp_code === r.emp_code
  const canSettle = mine && (r.status === 'approved' || r.status === 'advance_paid')
  const returned = [...r.timeline].reverse().find((e) => e.to_status === 'returned')
  return (
    <div className="space-y-4">
      <Stepper stage={r.stage} complete={r.settlement_status === 'paid'} />
      {r.legacy_flags.length > 0 && (
        <Card className="border-amber-300 bg-amber-50">
          <h3 className="mb-1 text-sm font-semibold text-amber-900">Migrated from email — issues found</h3>
          <ul className="list-disc pl-5 text-sm text-amber-900">{r.legacy_flags.map((f, i) => <li key={i}>{f}</li>)}</ul>
        </Card>
      )}
      {r.status === 'returned' && (
        <Card className="border-amber-300 bg-amber-50 text-sm"><b>Returned.</b> {returned?.remarks ? `“${returned.remarks}”` : ''}</Card>
      )}
      <div className="grid gap-4 md:grid-cols-[1fr_320px]">
        <Card className="space-y-3">
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div><span className="text-zinc-500">Employee</span><div>{r.emp_name}</div></div>
            <div><span className="text-zinc-500">Status</span><div>{statusLabel(r.status)} · rev {r.revision}</div></div>
            <div><span className="text-zinc-500">Destination</span><div>{r.destination_city}{r.city_tier ? ` (Tier ${r.city_tier})` : ''} · {r.category}</div></div>
            <div><span className="text-zinc-500">Dates</span><div>{formatDate(r.from_date)} – {formatDate(r.to_date)}{r.days ? ` (${r.days} days)` : ''}</div></div>
            <div><span className="text-zinc-500">Purpose</span><div>{r.purpose}</div></div>
            <div><span className="text-zinc-500">Visiting</span><div>{r.visiting_company} {r.visiting_place}</div></div>
            <div><span className="text-zinc-500">Mode</span><div>{r.mode}</div></div>
          </div>
          <Table>
            <thead><tr><Th>Head</Th><Th>Basis</Th><Th>Borne by</Th><Th className="text-right">Estimate</Th></tr></thead>
            <tbody>
              {r.heads.map((h) => <tr key={h.id}><Td>{statusLabel(h.head)}</Td><Td>{h.basis}</Td><Td>{h.borne_by}</Td><Td className="text-right tabular-nums">{formatINR(h.estimate_paise)}</Td></tr>)}
              <tr className="font-semibold"><Td colSpan={3}>Total estimate</Td><Td className="text-right tabular-nums">{formatINR(r.estimate_total_paise)}</Td></tr>
            </tbody>
          </Table>
        </Card>
        <div className="space-y-4">
          <Card className="space-y-2 text-sm">
            <h3 className="font-semibold">Advance</h3>
            <div>Requested: {formatINR(r.advance_requested_paise)} <span className="text-zinc-400">(cap {formatINR(r.advance_cap_paise)})</span></div>
            {r.advance
              ? <div className="text-green-700">Disbursed {formatINR(r.advance.amount_paise)} · {r.advance.reference} · {formatDate(r.advance.disbursed_at)} by {r.advance.disbursed_by_name}</div>
              : <div className="text-zinc-500">Not disbursed yet.</div>}
            <PayoutLine p={r.expected_payout} />
          </Card>
          <Card><h3 className="mb-2 text-sm font-semibold">Approval chain</h3><ChainPreview chain={r.chain} /></Card>
          <div className="flex flex-col gap-2">
            {mine && (r.status === 'draft' || r.status === 'returned') && (
              <>
                <Link to={`/requests/${r.id}/edit`}><Button variant="outline" className="w-full">Edit request</Button></Link>
                {r.status === 'returned' && <Button disabled={resubmit.isPending} onClick={() => resubmit.mutate()}>Resubmit</Button>}
              </>
            )}
            {canSettle && !r.settlement_id && (
              <Button disabled={createSettlement.isPending}
                onClick={() => createSettlement.mutate({ request_id: r.id }, { onSuccess: (s) => navigate(`/settlements/${s.id}`) })}>Start settlement</Button>
            )}
            {r.settlement_id && <Link to={`/settlements/${r.settlement_id}`}><Button className="w-full">Open settlement</Button></Link>}
          </div>
        </div>
      </div>
      <Timeline events={r.timeline} />
    </div>
  )
}

export default function RequestDetail() {
  const { id } = useParams()
  const q = useRequest(id)
  if (q.isLoading) return <p className="text-zinc-500">Loading…</p>
  if (q.error || !q.data) return <p className="text-red-600">{q.error?.message ?? 'Not found'}</p>
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Travel request {q.data.id}</h1>
      <RequestBody r={q.data} />
    </div>
  )
}
