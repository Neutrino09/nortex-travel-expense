import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  useAddLine, useDeleteLine, useImportFiles, useImportSample, useMe, usePatchLine,
  useResubmitSettlement, useSettlement, useSubmitSettlement, useValidateSettlement,
} from '@/api/client'
import type { ClaimLineOut, ClaimLinePatch, EvidenceOut, Finding, LineHead, Section, SettlementOut } from '@/api/types'
import { AttendeeDialog } from '@/components/AttendeeDialog'
import { EvidenceList } from '@/components/EvidenceList'
import { EvidenceViewer } from '@/components/EvidenceViewer'
import { FindingBadge } from '@/components/FindingBadge'
import { MoneyCell, MoneyInput } from '@/components/MoneyCell'
import { Stepper } from '@/components/Stepper'
import { SummaryCard } from '@/components/SummaryCard'
import { Timeline } from '@/components/Timeline'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'
import { Table, Td, Th } from '@/components/ui/table'
import { formatDate } from '@/lib/format'
import { statusLabel } from '@/lib/helpers'

const SECTIONS: { id: Section; label: string; defaultHead: LineHead }[] = [
  { id: 'lodging', label: 'Lodging', defaultHead: 'lodging' },
  { id: 'transport', label: 'Travel & Transportation', defaultHead: 'cab' },
  { id: 'other', label: 'Other Expenses', defaultHead: 'meals' },
]
const HEADS: { id: LineHead; label: string; section: Section }[] = [
  { id: 'lodging', label: 'Lodging', section: 'lodging' },
  { id: 'cab', label: 'Cab', section: 'transport' },
  { id: 'air', label: 'Air', section: 'transport' },
  { id: 'meals', label: 'Meals', section: 'other' },
  { id: 'business_entertainment', label: 'Business entertainment', section: 'other' },
  { id: 'misc', label: 'Misc', section: 'other' },
]

// Text input that commits on blur; remounts when the server value changes.
function Txt({ value, onCommit, disabled, type, className, placeholder }: {
  value: string | null | undefined; onCommit: (v: string) => void; disabled?: boolean; type?: string; className?: string; placeholder?: string
}) {
  const v = value ?? ''
  return <Input key={v} type={type} defaultValue={v} disabled={disabled} className={className} placeholder={placeholder}
    onBlur={(e) => { if (e.target.value !== v) onCommit(e.target.value) }} />
}

interface RowProps {
  line: ClaimLineOut; findings: Finding[]; evidence: EvidenceOut[]; editable: boolean
  onPatch: (p: ClaimLinePatch) => void; onDelete: () => void; onAttendees: () => void; onOpenEvidence: (e: EvidenceOut) => void
}

function LineRow({ line, findings, evidence, editable, onPatch, onDelete, onAttendees, onOpenEvidence }: RowProps) {
  const ev = evidence.find((e) => e.id === line.evidence_id)
  const memo = line.paid_by === 'Company'
  const shown = findings.filter((f) => f.severity === 'BLOCK' || f.severity === 'WARN')
  return (
    <>
      <tr className={memo ? 'bg-zinc-50 text-zinc-500' : ''}>
        <Td className="w-32"><Txt type="date" value={line.date} disabled={!editable} onCommit={(v) => onPatch({ date: v || null })} /></Td>
        <Td className="w-20"><Txt type="time" value={line.time} disabled={!editable} onCommit={(v) => onPatch({ time: v || null })} /></Td>
        <Td className="min-w-52 space-y-1">
          <Txt value={line.description} disabled={!editable} placeholder="Description" onCommit={(v) => onPatch({ description: v })} />
          {line.head === 'cab' && (
            <div className="flex gap-1">
              <Txt value={line.from_place} disabled={!editable} placeholder="From" onCommit={(v) => onPatch({ from_place: v })} />
              <Txt value={line.to_place} disabled={!editable} placeholder="To" onCommit={(v) => onPatch({ to_place: v })} />
            </div>
          )}
          {line.head === 'lodging' && (
            <div className="flex gap-1">
              <Txt value={line.merchant} disabled={!editable} placeholder="Hotel" onCommit={(v) => onPatch({ merchant: v })} />
              <Input key={line.nights ?? 0} type="number" className="w-20" placeholder="Nights" disabled={!editable} defaultValue={line.nights ?? ''}
                onBlur={(e) => { const n = e.target.value === '' ? null : Number(e.target.value); if (n !== line.nights) onPatch({ nights: n }) }} />
            </div>
          )}
          {line.head === 'business_entertainment' && (
            <button className="text-xs text-primary hover:underline" onClick={onAttendees}>
              {line.attendees.length ? `${line.attendees.length} attendee(s) — ${editable ? 'edit' : 'view'}` : editable ? '+ Add attendees' : 'No attendees'}
            </button>
          )}
        </Td>
        <Td className="w-36">
          <Select className="min-w-40" value={line.head} disabled={!editable}
            onChange={(e) => { const h = HEADS.find((x) => x.id === e.target.value)!; onPatch({ head: h.id, section: h.section }) }}>
            {HEADS.map((h) => <option key={h.id} value={h.id}>{h.label}</option>)}
          </Select>
        </Td>
        <Td className="w-28">
          <Select className="min-w-28" value={line.paid_by} disabled={!editable} onChange={(e) => onPatch({ paid_by: e.target.value as 'Employee' | 'Company' })}>
            <option>Employee</option><option>Company</option>
          </Select>
        </Td>
        <Td className="w-40 space-y-1 text-right">
          {editable ? (
            <>
              <MoneyInput paise={line.base_paise} onCommit={(p) => onPatch({ base_paise: p })} placeholder="Base" />
              <MoneyInput paise={line.tax_paise} onCommit={(p) => onPatch({ tax_paise: p })} placeholder="Tax" className="text-xs" />
              <div className="text-[11px] text-zinc-400">base / tax</div>
            </>
          ) : null}
          <MoneyCell paise={line.amount_paise} className="font-medium" />
        </Td>
        <Td className="w-32 text-right">
          {line.disallowed_paise > 0
            ? <span className="cursor-help text-zinc-400 line-through" title={`${line.disallow_reason ?? ''}${line.policy_ref ? ` (${line.policy_ref})` : ''}`}><MoneyCell paise={line.disallowed_paise} /></span>
            : <span className="text-zinc-300">—</span>}
        </Td>
        <Td className="w-36">
          {editable ? (
            <Select value={line.evidence_id ?? ''} onChange={(e) => onPatch({ evidence_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">— none —</option>
              {evidence.map((e) => <option key={e.id} value={e.id}>#{e.id} {e.filename}</option>)}
            </Select>
          ) : null}
          {ev ? <button className="text-xs text-primary hover:underline" onClick={() => onOpenEvidence(ev)}>#{ev.id} {ev.filename}</button>
            : <span className="text-xs text-red-600">No proof</span>}
        </Td>
        <Td className="w-8">{editable && <button className="text-zinc-400 hover:text-red-600" title="Delete line" onClick={onDelete}>✕</button>}</Td>
      </tr>
      {shown.length > 0 && (
        <tr><Td colSpan={9} className="space-y-1 bg-white py-1.5">{shown.map((f, i) => <FindingBadge key={i} f={f} />)}</Td></tr>
      )}
    </>
  )
}

export interface EditorProps { reviewMode?: boolean; sid?: number }

export function SettlementBody({ sid, reviewMode }: { sid: number; reviewMode?: boolean }) {
  const me = useMe()
  const q = useSettlement(sid)
  const s = q.data
  const validate = useValidateSettlement(sid)
  const addLine = useAddLine(sid)
  const patchLine = usePatchLine(sid)
  const delLine = useDeleteLine(sid)
  const importSample = useImportSample(sid)
  const importFiles = useImportFiles(sid)
  const submit = useSubmitSettlement(sid)
  const resubmit = useResubmitSettlement(sid)
  const [viewer, setViewer] = useState<EvidenceOut | null>(null)
  const [attLine, setAttLine] = useState<ClaimLineOut | null>(null)
  const [drag, setDrag] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const editable = !reviewMode && !!s && me.data?.emp_code === s.emp_code && (s.status === 'draft' || s.status === 'returned')

  // Debounced (400 ms) server-side validation after every edit.
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const { mutate: runValidate } = validate
  const scheduleValidate = useCallback(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => runValidate(), 400)
  }, [runValidate])
  useEffect(() => () => clearTimeout(timer.current), [])
  const firstLoad = useRef(true)
  useEffect(() => {
    if (s && editable && firstLoad.current) { firstLoad.current = false; scheduleValidate() }
  }, [s, editable, scheduleValidate])

  const v = validate.data
  const findings = v?.findings ?? s?.findings ?? []
  const summary = v?.summary ?? s?.summary
  const chain = (v?.chain_preview ?? s?.chain) ?? []
  const payout = v?.expected_payout ?? s?.expected_payout ?? null
  const rules = v?.rules_checked ?? s?.rules_checked ?? 0
  const blockers = findings.filter((f) => f.severity === 'BLOCK')

  const returnedRemark = useMemo(() => {
    if (!s || s.status !== 'returned') return null
    return [...s.timeline].reverse().find((e) => e.to_status === 'returned')
  }, [s])

  if (q.isLoading) return <p className="text-zinc-500">Loading…</p>
  if (q.error || !s || !summary) return <p className="text-red-600">{q.error?.message ?? 'Not found'}</p>

  const after = { onSuccess: scheduleValidate }
  const upload = (files: FileList | File[]) => { const a = Array.from(files); if (a.length) importFiles.mutate(a, after) }
  const addIn = (section: Section, head: LineHead) =>
    addLine.mutate({ section, head, paid_by: 'Employee', base_paise: 0, tax_paise: 0, description: '' }, after)
  const doSubmit = () => (s.status === 'returned' ? resubmit : submit).mutate(undefined)
  const globalFindings = findings.filter((f) => f.line_id == null && f.severity !== 'INFO')

  return (
    <div className="space-y-4">
      <Stepper stage={s.trip.stage} complete={s.trip.settlement_status === 'paid'} />
      {returnedRemark && (
        <Card className="border-amber-300 bg-amber-50 text-sm">
          <b>Returned for changes.</b> {returnedRemark.remarks ? `“${returnedRemark.remarks}”` : ''} Fix the items below and resubmit.
        </Card>
      )}
      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-4">
          {editable && (
            <Card className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">Import evidence</h3>
                <Button onClick={() => importSample.mutate(undefined, after)} disabled={importSample.isPending}>
                  {importSample.isPending ? 'Loading…' : 'Load sample inbox'}
                </Button>
              </div>
              <div
                className={`cursor-pointer rounded-lg border-2 border-dashed p-5 text-center text-sm text-zinc-500 ${drag ? 'border-primary bg-green-50' : 'border-zinc-300'}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}>
                {importFiles.isPending ? 'Importing…' : 'Drop .eml, .png or .jpg files here, or click to browse'}
                <input ref={fileRef} type="file" multiple accept=".eml,.png,.jpg,.jpeg" className="hidden"
                  onChange={(e) => { if (e.target.files) upload(e.target.files); e.target.value = '' }} />
              </div>
            </Card>
          )}
          <Card>
            <h3 className="mb-2 text-sm font-semibold">Documents ({s.evidence.length})</h3>
            <EvidenceList items={s.evidence} onOpen={setViewer} />
          </Card>

          {globalFindings.length > 0 && (
            <Card className="space-y-1">{globalFindings.map((f, i) => <FindingBadge key={i} f={f} />)}</Card>
          )}

          {SECTIONS.map((sec) => {
            const lines = s.lines.filter((l) => l.section === sec.id)
            return (
              <Card key={sec.id}>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold">{sec.label}</h3>
                  {editable && <Button variant="outline" onClick={() => addIn(sec.id, sec.defaultHead)}>+ Add line</Button>}
                </div>
                <Table className="min-w-[1200px]">
                  <thead><tr>
                    <Th>Date</Th><Th>Time</Th><Th>Description / From → To / Hotel</Th><Th>Head</Th><Th>Paid by</Th>
                    <Th className="text-right">Amount</Th><Th className="text-right">Disallowed</Th><Th>Proof ref</Th><Th />
                  </tr></thead>
                  <tbody>
                    {lines.length === 0 && <tr><Td colSpan={9} className="text-zinc-400">No lines.</Td></tr>}
                    {lines.map((l) => (
                      <LineRow key={l.id} line={l} editable={editable} evidence={s.evidence}
                        findings={findings.filter((f) => f.line_id === l.id)}
                        onPatch={(p) => patchLine.mutate({ lineId: l.id, patch: p }, after)}
                        onDelete={() => delLine.mutate(l.id, after)}
                        onAttendees={() => setAttLine(l)} onOpenEvidence={setViewer} />
                    ))}
                  </tbody>
                </Table>
              </Card>
            )
          })}
          {reviewMode && <Timeline events={s.timeline} />}
        </div>

        <div className="order-first 2xl:order-none 2xl:sticky 2xl:top-4 2xl:self-start">
          <div className="space-y-4">
            <SummaryCard summary={summary} chain={chain} payout={payout}>
              {editable && (
                <>
                  <Button className="w-full" disabled={blockers.length > 0 || submit.isPending || resubmit.isPending}
                    title={blockers.length ? `Fix before submitting:\n${blockers.map((b) => `• ${b.message}`).join('\n')}` : undefined}
                    onClick={doSubmit}>
                    {s.status === 'returned' ? 'Resubmit' : 'Submit for approval'}
                  </Button>
                  {blockers.length > 0 && <p className="text-xs text-red-700">{blockers.length} blocking issue(s) must be fixed first.</p>}
                </>
              )}
              {s.payments.map((p) => (
                <div key={p.id} className="text-xs text-zinc-600">{p.kind} {statusLabel(p.status)} · run {formatDate(p.run_date)}</div>
              ))}
            </SummaryCard>
            <p className="text-center text-xs text-zinc-500">Checked live against {rules} policy rules</p>
          </div>
        </div>
      </div>
      {!reviewMode && <Timeline events={s.timeline} />}
      <EvidenceViewer evidence={viewer} onClose={() => setViewer(null)} />
      <AttendeeDialog line={attLine} onClose={() => setAttLine(null)}
        onSave={(attendees, prior) => {
          if (!editable) { setAttLine(null); return }
          patchLine.mutate({ lineId: attLine!.id, patch: { attendees, prior_approval_ref: prior } }, after)
          setAttLine(null)
        }} />
    </div>
  )
}

export function SettlementHeader({ s }: { s: SettlementOut }) {
  const t = s.trip
  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">Trip settlement <Link to={`/requests/${t.id}`} className="text-primary hover:underline">{t.id}</Link></h1>
        <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs">{statusLabel(s.status)} · rev {s.revision}</span>
      </div>
      <p className="text-sm text-zinc-600">{t.emp_name} · {t.purpose} · {t.destination_city} · {formatDate(t.from_date)} – {formatDate(t.to_date)}</p>
    </div>
  )
}

export default function SettlementEditor() {
  const { id } = useParams()
  const sid = Number(id)
  const q = useSettlement(sid)
  return (
    <div className="space-y-4">
      {q.data && <SettlementHeader s={q.data} />}
      <SettlementBody sid={sid} />
    </div>
  )
}
