import { Link } from 'react-router-dom'
import { useInbox } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Table, Td, Th } from '@/components/ui/table'
import { formatDate, formatINR } from '@/lib/format'
import { daysSince } from '@/lib/helpers'

export default function ApprovalsInbox() {
  const inbox = useInbox()
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Approvals inbox</h1>
      {inbox.isLoading && <p className="text-zinc-500">Loading…</p>}
      {inbox.error && <p className="text-red-600">{inbox.error.message}</p>}
      <Card>
        {inbox.data?.length === 0 && <p className="text-sm text-zinc-500">Nothing is waiting on you.</p>}
        {!!inbox.data?.length && (
          <Table>
            <thead><tr><Th>TRQ</Th><Th>Type</Th><Th>Employee</Th><Th className="text-right">Amount</Th><Th>Level</Th><Th>Waiting since</Th><Th>Flags</Th></tr></thead>
            <tbody>
              {inbox.data.map((i) => (
                <tr key={`${i.entity_type}-${i.entity_id}`}>
                  <Td><Link className="text-primary hover:underline" to={`/approvals/${i.entity_type}/${i.entity_id}`}>{i.request_id}</Link> <span className="text-xs text-zinc-400">rev {i.revision}</span></Td>
                  <Td>{i.entity_type === 'request' ? 'Travel request' : 'Settlement'}</Td>
                  <Td>{i.emp_name}</Td>
                  <Td className="text-right tabular-nums">{formatINR(i.amount_paise)}</Td>
                  <Td>{i.level}</Td>
                  <Td>{formatDate(i.waiting_since)} ({daysSince(i.waiting_since)}d)</Td>
                  <Td>{i.flags_count > 0 ? <Badge tone="amber">{i.flags_count}</Badge> : <span className="text-zinc-300">0</span>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  )
}
