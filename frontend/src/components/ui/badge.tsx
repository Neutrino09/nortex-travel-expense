import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const badge = cva('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', {
  variants: {
    tone: {
      green: 'bg-green-100 text-green-800',
      red: 'bg-red-100 text-red-800',
      amber: 'bg-amber-100 text-amber-800',
      grey: 'bg-zinc-100 text-zinc-600',
      blue: 'bg-blue-100 text-blue-800',
    },
  },
  defaultVariants: { tone: 'grey' },
})

export function Badge({ className, tone, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />
}
