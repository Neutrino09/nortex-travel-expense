import { Check } from 'lucide-react'
import type { StageInfo } from '@/api/types'
import { Card } from '@/components/ui/card'

const STEPS = ['Travel request', 'Trip approval', 'Advance disbursement', 'Trip settlement', 'Finance review', 'Payout']

// Active step comes from the server (stage.step_index); nothing is derived here.
export function Stepper({ stage, complete }: { stage: StageInfo; complete?: boolean }) {
  const cur = stage.step_index
  return (
    <Card>
      <h3 className="mb-4 text-sm font-semibold">What happens after you submit</h3>
      <ol className="flex">
        {STEPS.map((label, i) => {
          const done = complete || i < cur
          const active = !complete && i === cur
          return (
            <li key={label} className="flex flex-1 flex-col items-center text-center">
              <div className="flex w-full items-center">
                <div className={`h-0.5 flex-1 ${i === 0 ? 'bg-transparent' : done || active ? 'bg-primary' : 'bg-zinc-200'}`} />
                <div className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                  done ? 'bg-primary text-white' : active ? 'border-2 border-primary text-primary' : 'border border-zinc-300 text-zinc-400'}`}>
                  {done ? <Check size={14} /> : i + 1}
                </div>
                <div className={`h-0.5 flex-1 ${i === STEPS.length - 1 ? 'bg-transparent' : done ? 'bg-primary' : 'bg-zinc-200'}`} />
              </div>
              <div className={`mt-1 px-1 text-xs ${active ? 'font-semibold text-primary' : 'text-zinc-500'}`}>{label}</div>
              <div className="h-4 text-[11px] font-medium text-primary">{active ? 'You are here' : ''}</div>
            </li>
          )
        })}
      </ol>
    </Card>
  )
}
