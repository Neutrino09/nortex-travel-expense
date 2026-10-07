import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAct, useFinanceQueue, useInbox, useMe, useRequest, useSettlement } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { Label, Textarea } from '@/components/ui/input'
import { toast } from '@/lib/toast'
import { RequestBody } from './RequestDetail'
import { SettlementBody, SettlementHeader } from './SettlementEditor'

function ActionBar({ entityType, entityId, verify }: { entityType: string; entityId: string; verify: boolean }) {
  const act = useAct()
  const navigate = useNavigate()
  const [dlg, setDlg] = useState<'return' | 'reject' | null>(null)
  const [remarks, setRemarks] = useState('')
  const done = () => { setDlg(null); toast(verify ? 'Verified' : 'Done', 'success'); navigate(verify ? '/finance' : '/approvals') }
  const run = (action: 'approve' | 'return' | 'reject') =>
    act.mutate({ entityType, entityId, body: { action, remarks: remarks.trim() || null } }, { onSuccess: done })
  return (
    <Card className="flex items-center gap-3">
      <span className="text-sm font-medium">Your action:</span>
      <Button onClick={() => run('approve')} disabled={act.isPending}>{verify ? 'Verify' : 'Approve'}</Button>
      <Button variant="outline" onClick={() => { setRemarks(''); setDlg('return') }}>Return</Button>
      <Button variant="destructive" onClick={() => { setRemarks(''); setDlg('reject') }}>Reject</Button>
      <Dialog open={!!dlg} onClose={() => setDlg(null)} title={dlg === 'return' ? 'Return for changes' : 'Reject'}>
        <div className="space-y-3">
          <div><Label>Remarks (required)</Label><Textarea rows={4} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDlg(null)}>Cancel</Button>
            <Button variant={dlg === 'reject' ? 'destructive' : 'default'} disabled={!remarks.trim() || act.isPending}
              onClick={() => run(dlg!)}>{dlg === 'return' ? 'Return' : 'Reject'}</Button>
          </div>
        </div>
      </Dialog>
    </Card>
  )
}

function useCanAct(entityType: string, entityId: string) {
  const inbox = useInbox()
  const queue = useFinanceQueue()
  const me = useMe()
  const inInbox = inbox.data?.some((i) => i.entity_type === entityType && i.entity_id === entityId)
  const inQueue = me.data?.app_role === 'admin' && queue.data?.settlements_to_verify.some((i) => i.entity_type === entityType && i.entity_id === entityId)
  return !!(inInbox || inQueue)
}

function SettlementReview({ id }: { id: number }) {
  const q = useSettlement(id)
  const can = useCanAct('settlement', String(id))
  return (
    <div className="space-y-4">
      {q.data && <SettlementHeader s={q.data} />}
      {can && <ActionBar entityType="settlement" entityId={String(id)} verify={q.data?.status === 'finance_review'} />}
      <SettlementBody sid={id} reviewMode />
    </div>
  )
}

function RequestReview({ id }: { id: string }) {
  const q = useRequest(id)
  const can = useCanAct('request', id)
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Travel request <Link className="text-primary hover:underline" to={`/requests/${id}`}>{id}</Link></h1>
      {can && <ActionBar entityType="request" entityId={id} verify={false} />}
      {q.data && <RequestBody r={q.data} />}
    </div>
  )
}

export default function ReviewItem() {
  const { entityType, entityId } = useParams()
  if (entityType === 'settlement') return <SettlementReview id={Number(entityId)} />
  return <RequestReview id={entityId ?? ''} />
}
