import { useState } from 'react'
import type { Attendee, ClaimLineOut } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Input, Label } from '@/components/ui/input'

// Business-entertainment attendees (policy §3.5) + prior approval reference.
export function AttendeeDialog({ line, onClose, onSave }: {
  line: ClaimLineOut | null; onClose: () => void
  onSave: (attendees: Attendee[], priorRef: string | null) => void
}) {
  return (
    <Dialog open={!!line} onClose={onClose} title="Attendees (business entertainment)">
      {line && <Body key={line.id} line={line} onSave={onSave} />}
    </Dialog>
  )
}

function Body({ line, onSave }: { line: ClaimLineOut; onSave: (a: Attendee[], p: string | null) => void }) {
  const [rows, setRows] = useState<Attendee[]>(line.attendees.length ? line.attendees : [{ name: '', organisation: '' }])
  const [ref, setRef] = useState(line.prior_approval_ref ?? '')
  const upd = (i: number, k: keyof Attendee, v: string) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[1fr_1fr_auto] gap-2">
        <Label>Name</Label><Label>Organisation</Label><span />
        {rows.map((r, i) => (
          <div key={i} className="contents">
            <Input value={r.name} onChange={(e) => upd(i, 'name', e.target.value)} />
            <Input value={r.organisation} onChange={(e) => upd(i, 'organisation', e.target.value)} />
            <button className="text-zinc-400 hover:text-red-600" onClick={() => setRows(rows.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
      </div>
      <Button variant="outline" onClick={() => setRows([...rows, { name: '', organisation: '' }])}>+ Add attendee</Button>
      <div><Label>HoD prior approval reference (optional)</Label><Input value={ref} onChange={(e) => setRef(e.target.value)} /></div>
      <div className="flex justify-end">
        <Button onClick={() => onSave(rows.filter((r) => r.name.trim() || r.organisation.trim()), ref.trim() || null)}>Save</Button>
      </div>
    </div>
  )
}
