import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { patchJson, post, useRequest, useResubmitRequest, useSubmitRequest } from '@/api/client'
import type { CostHeadIn, Head, PaidBy, RequestIn, RequestOut, RequestValidateOut } from '@/api/types'
import { ChainPreview } from '@/components/ChainPreview'
import { FindingBadge } from '@/components/FindingBadge'
import { MoneyInput } from '@/components/MoneyCell'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Label, Select } from '@/components/ui/input'
import { Table, Td, Th } from '@/components/ui/table'
import { formatINR } from '@/lib/format'
import { statusLabel } from '@/lib/helpers'
import { toast } from '@/lib/toast'

const HEADS: Head[] = ['air_rail', 'lodging', 'conveyance', 'meals', 'other']
interface HeadRow { head: Head; basis: string; paise: number; borne_by: PaidBy }
interface Form {
  purpose: string; visiting_place: string; visiting_company: string; from_date: string; to_date: string
  destination_city: string; city_tier: number | null; category: 'domestic' | 'international'; mode: string
  advance_paise: number; heads: HeadRow[]
}
const empty = (): Form => ({
  purpose: '', visiting_place: '', visiting_company: '', from_date: '', to_date: '', destination_city: '',
  city_tier: null, category: 'domestic', mode: 'Flight', advance_paise: 0,
  heads: HEADS.map((h) => ({ head: h, basis: '', paise: 0, borne_by: 'Employee' })),
})
const fromRequest = (r: RequestOut): Form => ({
  purpose: r.purpose, visiting_place: r.visiting_place, visiting_company: r.visiting_company,
  from_date: r.from_date ?? '', to_date: r.to_date ?? '', destination_city: r.destination_city,
  city_tier: r.city_tier, category: r.category === 'international' ? 'international' : 'domestic', mode: r.mode,
  advance_paise: r.advance_requested_paise,
  heads: HEADS.map((h) => {
    const x = r.heads.find((y) => y.head === h)
    return { head: h, basis: x?.basis ?? '', paise: x?.estimate_paise ?? 0, borne_by: x?.borne_by ?? 'Employee' }
  }),
})
const toPayload = (f: Form): RequestIn => ({
  purpose: f.purpose, visiting_place: f.visiting_place, visiting_company: f.visiting_company,
  from_date: f.from_date || null, to_date: f.to_date || null, destination_city: f.destination_city,
  city_tier: f.city_tier, category: f.category, mode: f.mode, advance_requested_paise: f.advance_paise,
  heads: f.heads.filter((h) => h.paise > 0).map<CostHeadIn>((h) => ({ head: h.head, basis: h.basis, estimate_paise: h.paise, borne_by: h.borne_by })),
})

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><Label>{label}</Label>{children}</div>
}

// New / edit travel request. The draft is saved (debounced) and the SERVER validates it:
// cap, tier, day count, total and chain all come back from /requests/{id}/validate.
export default function RequestForm() {
  const params = useParams()
  const navigate = useNavigate()
  const existing = useRequest(params.id)
  const [form, setForm] = useState<Form>(empty())
  const [id, setId] = useState<string | undefined>(params.id)
  const idRef = useRef<string | undefined>(params.id)
  const [v, setV] = useState<RequestValidateOut | null>(null)
  const loaded = useRef(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const submit = useSubmitRequest(id ?? '')
  const resubmit = useResubmitRequest(id ?? '')

  useEffect(() => {
    if (existing.data && !loaded.current) { loaded.current = true; setForm(fromRequest(existing.data)); validateNow(existing.data.id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing.data])
  useEffect(() => () => clearTimeout(timer.current), [])

  async function validateNow(rid: string) {
    try { setV(await post<RequestValidateOut>(`/requests/${rid}/validate`)) } catch (e) { toast((e as Error).message) }
  }
  async function save(f: Form) {
    try {
      let rid = idRef.current
      if (!rid) {
        const r = await post<RequestOut>('/requests', toPayload(f))
        rid = r.id; idRef.current = rid; setId(rid)
      } else {
        await patchJson<RequestOut>(`/requests/${rid}`, toPayload(f))
      }
      await validateNow(rid)
    } catch (e) { toast((e as Error).message) }
  }
  function change(patch: Partial<Form>) {
    const next = { ...form, ...patch }
    setForm(next)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => save(next), 400)
  }
  const setHead = (i: number, p: Partial<HeadRow>) => change({ heads: form.heads.map((h, j) => (j === i ? { ...h, ...p } : h)) })

  const blockers = v?.findings.filter((f) => f.severity === 'BLOCK') ?? []
  const status = existing.data?.status
  const isReturned = status === 'returned'
  const doSubmit = () => (isReturned ? resubmit : submit).mutate(undefined, { onSuccess: () => navigate(`/requests/${id}`) })
  const needsTier = !!form.destination_city && v !== null && v.city_tier === null

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{params.id ? `Edit travel request ${params.id}` : 'New travel request'}</h1>
      {existing.data && !['draft', 'returned'].includes(existing.data.status) && (
        <Card className="text-sm text-amber-800">This request is {statusLabel(existing.data.status)} and can no longer be edited.</Card>
      )}
      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <Card className="grid gap-3 md:grid-cols-2">
            <Field label="From date"><Input type="date" value={form.from_date} onChange={(e) => change({ from_date: e.target.value })} /></Field>
            <Field label={`To date${v?.days ? ` — ${v.days} day(s)` : ''}`}><Input type="date" value={form.to_date} onChange={(e) => change({ to_date: e.target.value })} /></Field>
            <Field label="Destination city"><Input value={form.destination_city} onChange={(e) => change({ destination_city: e.target.value, city_tier: null })} /></Field>
            <Field label="City tier">
              {needsTier ? (
                <Select value={form.city_tier ?? ''} onChange={(e) => change({ city_tier: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">Select Tier 2 or 3…</option><option value="2">Tier 2</option><option value="3">Tier 3</option>
                </Select>
              ) : <Input disabled value={v?.city_tier ? `Tier ${v.city_tier} (automatic)` : '—'} />}
            </Field>
            <Field label="Purpose"><Input value={form.purpose} onChange={(e) => change({ purpose: e.target.value })} /></Field>
            <Field label="Visiting company"><Input value={form.visiting_company} onChange={(e) => change({ visiting_company: e.target.value })} /></Field>
            <Field label="Visiting place"><Input value={form.visiting_place} onChange={(e) => change({ visiting_place: e.target.value })} /></Field>
            <Field label="Mode of travel">
              <Select value={form.mode} onChange={(e) => change({ mode: e.target.value })}>
                {['Flight', 'Train', 'Road', 'Other'].map((m) => <option key={m}>{m}</option>)}
              </Select>
            </Field>
            <Field label="Category">
              <Select value={form.category} onChange={(e) => change({ category: e.target.value as 'domestic' | 'international' })}>
                <option value="domestic">Domestic</option><option value="international">International</option>
              </Select>
            </Field>
          </Card>
          <Card>
            <h3 className="mb-2 text-sm font-semibold">Estimated costs</h3>
            <Table>
              <thead><tr><Th>Head</Th><Th>Basis</Th><Th>Borne by</Th><Th className="text-right">Estimate (₹)</Th></tr></thead>
              <tbody>
                {form.heads.map((h, i) => (
                  <tr key={h.head}>
                    <Td>{statusLabel(h.head)}</Td>
                    <Td><Input value={h.basis} onChange={(e) => setHead(i, { basis: e.target.value })} /></Td>
                    <Td className="w-32"><Select value={h.borne_by} onChange={(e) => setHead(i, { borne_by: e.target.value as PaidBy })}><option>Employee</option><option>Company</option></Select></Td>
                    <Td className="w-40"><MoneyInput paise={h.paise} onCommit={(p) => setHead(i, { paise: p })} /></Td>
                  </tr>
                ))}
                <tr className="font-semibold"><Td colSpan={3}>Total estimate (computed)</Td><Td className="text-right tabular-nums">{formatINR(v?.estimate_total_paise ?? 0)}</Td></tr>
              </tbody>
            </Table>
          </Card>
          <Card className="max-w-sm">
            <Label>Advance requested (₹)</Label>
            <MoneyInput paise={form.advance_paise} onCommit={(p) => change({ advance_paise: p })} />
            <p className="mt-1 text-xs text-zinc-500">Cap: {formatINR(v?.advance_cap_paise ?? 0)} (60% of employee-borne costs)</p>
          </Card>
        </div>
        <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <Card className="space-y-2">
            <h3 className="text-sm font-semibold">Checks</h3>
            {v?.findings.length === 0 && <p className="text-sm text-green-700">No issues.</p>}
            {v?.findings.map((f, i) => <FindingBadge key={i} f={f} />)}
            {!v && <p className="text-sm text-zinc-500">Fill in the form — it is checked on the server as you type.</p>}
          </Card>
          <Card className="space-y-2">
            <h3 className="text-sm font-semibold">Approval chain</h3>
            <ChainPreview chain={v?.chain_preview ?? []} />
            <Button className="w-full" disabled={!id || !v || blockers.length > 0 || submit.isPending || resubmit.isPending}
              title={blockers.length ? blockers.map((b) => `• ${b.message}`).join('\n') : undefined}
              onClick={doSubmit}>{isReturned ? 'Resubmit' : 'Submit request'}</Button>
          </Card>
        </div>
      </div>
    </div>
  )
}
