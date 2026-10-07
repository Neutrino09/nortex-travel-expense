import { Link } from 'react-router-dom'
import { useRequests } from '@/api/client'
import { Card } from '@/components/ui/card'
import { Table, Td, Th } from '@/components/ui/table'
import { formatDate, formatINR } from '@/lib/format'
import { statusLabel } from '@/lib/helpers'

export default function Claims() {
  const reqs = useRequests()
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Claims</h1>
      {reqs.isLoading && <p className="text-zinc-500">Loading…</p>}
      {reqs.error && <p className="text-red-600">{reqs.error.message}</p>}
      <Card>
        <Table>
          <thead><tr><Th>TRQ</Th><Th>Employee</Th><Th>Trip</Th><Th>Request</Th><Th>Settlement</Th><Th>Stage</Th><Th className="text-right">Estimate</Th></tr></thead>
          <tbody>
            {reqs.data?.map((r) => (
              <tr key={r.id}>
                <Td><Link className="text-primary hover:underline" to={`/requests/${r.id}`}>{r.id}</Link></Td>
                <Td>{r.emp_name}</Td>
                <Td>{r.destination_city} · {formatDate(r.from_date)}</Td>
                <Td>{statusLabel(r.status)}</Td>
                <Td>{r.settlement_id ? <Link className="text-primary hover:underline" to={`/settlements/${r.settlement_id}`}>{statusLabel(r.settlement_status ?? '')}</Link> : '—'}</Td>
                <Td>{r.stage.step_label}</Td>
                <Td className="text-right tabular-nums">{formatINR(r.estimate_total_paise)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </div>
  )
}
