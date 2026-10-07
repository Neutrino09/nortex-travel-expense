import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useDisburseAdvance, useFinanceQueue, useMarkPaid } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Table, Td } from '@/components/ui/table'
import { Tabs } from '@/components/ui/tabs'
import { formatDate, formatINR } from '@/lib/format'
import { daysSince, statusLabel } from '@/lib/helpers'

export default function Finance() {
  const q = useFinanceQueue()
  const disburse = useDisburseAdvance()
  const markPaid = useMarkPaid()
  const [tab, setTab] = useState('advances')
  const d = q.data
  const byRun = new Map<string, NonNullable<typeof d>['payments']>()
  d?.payments.forEach((p) => byRun.set(p.run_date, [...(byRun.get(p.run_date) ?? []), p]))
  const runs = [...byRun.entries()].sort(([a], [b]) => a.localeCompare(b))
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">Finance</h1>
      {q.isLoading && <p className="text-zinc-500">Loading…</p>}
      {q.error && <p className="text-red-600">{q.error.message}</p>}
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: 'advances', label: `Advances to disburse (${d?.advances_to_disburse.length ?? 0})` },
        { id: 'verify', label: `Claims to verify (${d?.settlements_to_verify.length ?? 0})` },
        { id: 'runs', label: 'Payment runs' },
      ]} />
      {tab === 'advances' && (
        <Card>
          {d?.advances_to_disburse.length === 0 && <p className="text-sm text-zinc-500">No advances waiting.</p>}
          <Table><tbody>
            {d?.advances_to_disburse.map((r) => (
              <tr key={r.id}>
                <Td><Link className="text-primary hover:underline" to={`/requests/${r.id}`}>{r.id}</Link></Td>
                <Td>{r.emp_name}</Td><Td>{r.purpose}</Td>
                <Td className="text-right tabular-nums">{formatINR(r.advance_requested_paise)}</Td>
                <Td className="text-right">
                  <Button disabled={disburse.isPending} onClick={() => disburse.mutate({ requestId: r.id, body: { amount_paise: r.advance_requested_paise } })}>Disburse</Button>
                </Td>
              </tr>
            ))}
          </tbody></Table>
        </Card>
      )}
      {tab === 'verify' && (
        <Card>
          {d?.settlements_to_verify.length === 0 && <p className="text-sm text-zinc-500">No claims waiting for verification.</p>}
          <Table><tbody>
            {d?.settlements_to_verify.map((i) => (
              <tr key={i.entity_id}>
                <Td>{i.request_id}</Td><Td>{i.emp_name}</Td>
                <Td className="text-right tabular-nums">{formatINR(i.amount_paise)}</Td>
                <Td>{daysSince(i.waiting_since)}d waiting</Td>
                <Td>{i.flags_count > 0 && <Badge tone="amber">{i.flags_count} flags</Badge>}</Td>
                <Td className="text-right"><Link to={`/approvals/${i.entity_type}/${i.entity_id}`}><Button>Review &amp; verify</Button></Link></Td>
              </tr>
            ))}
          </tbody></Table>
        </Card>
      )}
      {tab === 'runs' && (
        <div className="space-y-4">
          {runs.length === 0 && <Card className="text-sm text-zinc-500">No payments yet.</Card>}
          {runs.map(([date, ps]) => (
            <Card key={date}>
              <h3 className="mb-2 text-sm font-semibold">Payment run {formatDate(date)}</h3>
              <Table><tbody>
                {ps.map((p) => (
                  <tr key={p.id}>
                    <Td>{p.request_id}</Td><Td>{p.emp_name}</Td>
                    <Td><Badge tone={p.kind === 'payout' ? 'green' : 'amber'}>{p.kind}</Badge></Td>
                    <Td className="text-right tabular-nums">{formatINR(p.amount_paise)}</Td>
                    <Td>{statusLabel(p.status)}{p.paid_at ? ` · ${formatDate(p.paid_at)}` : ''}</Td>
                    <Td className="text-right">{p.status === 'scheduled' && <Button disabled={markPaid.isPending} onClick={() => markPaid.mutate(p.id)}>Mark paid</Button>}</Td>
                  </tr>
                ))}
              </tbody></Table>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
