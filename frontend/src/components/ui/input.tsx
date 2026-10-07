import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const base = 'w-full rounded-md border border-border bg-white px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:bg-zinc-50 disabled:text-zinc-500'

export function Input({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(base, className)} {...p} />
}
export function Textarea({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(base, className)} {...p} />
}
export function Select({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(base, className)} {...p} />
}
export function Label({ children, className }: { children: React.ReactNode; className?: string }) {
  return <label className={cn('mb-1 block text-xs font-medium text-zinc-600', className)}>{children}</label>
}
