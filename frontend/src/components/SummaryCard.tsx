import type { ChainStepOut, ExpectedPayout, SettlementSummary } from '@/api/types'
import { Card } from '@/components/ui/card'
import { formatDate, formatINR } from '@/lib/format'
import { ChainPreview } from './ChainPreview'

function Row({ label, value, strong, tone }: { label: string; value: number; strong?: boolean; tone?: string }) {
  return (
    <div className={`flex justify-between py-1 text-sm ${strong ? 'font-semibold' : ''} ${tone ?? ''}`}>
      <span>{label}</span><span className="tabular-nums">{formatINR(value)}</span>
    </div>
  )
}

export function PayoutLine({ p }: { p: ExpectedPayout | null }) {
  if (!p) return null
  const what = p.kind === 'recovery' ? 'Recovery' : 'Expected payout'
  return (
    <div className="rounded-md bg-green-50 p-2 text-sm text-green-900">
      {what}: <b>{formatINR(p.amount_paise)}</b> on <b>{formatDate(p.run_date)}</b>{p.estimated ? ' (estimated)' : ''}
    </div>
  )
}

export function SummaryCard({ summary, chain, payout, children }: {
  summary: SettlementSummary; chain: ChainStepOut[]; payout: ExpectedPayout | null; children?: React.ReactNode
}) {
  return (
    <Card className="space-y-3">
      <h3 className="text-sm font-semibold">Settlement summary</h3>
      <div className="divide-y divide-zinc-100">
        <Row label="Gross (employee-paid)" value={summary.gross_employee_paise} />
        <Row label="Company-paid (memo)" value={summary.company_memo_paise} tone="text-zinc-500" />
        <Row label="Disallowed" value={-summary.disallowed_paise} tone="text-red-700" />
        <Row label="Net claim" value={summary.net_paise} strong />
        <Row label="Advance received" value={summary.advance_paise} />
        {summary.recoverable_paise > 0
          ? <Row label="Recoverable from you" value={summary.recoverable_paise} strong tone="text-red-700" />
          : <Row label="Payable to you" value={summary.payable_paise} strong tone="text-green-700" />}
      </div>
      <PayoutLine p={payout} />
      <div>
        <div className="mb-1 text-xs font-medium uppercase text-zinc-500">Approval chain</div>
        <ChainPreview chain={chain} />
      </div>
      {children}
    </Card>
  )
}
