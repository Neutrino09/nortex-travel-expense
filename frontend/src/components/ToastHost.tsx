import { useSyncExternalStore } from 'react'
import { getToasts, subscribeToasts } from '@/lib/toast'

export default function ToastHost() {
  const items = useSyncExternalStore(subscribeToasts, getToasts)
  return (
    <div className="fixed bottom-4 right-4 z-[60] space-y-2">
      {items.map((t) => (
        <div key={t.id} className={`max-w-sm rounded-md px-4 py-2 text-sm text-white shadow-lg ${t.tone === 'error' ? 'bg-red-600' : 'bg-green-700'}`}>
          {t.text}
        </div>
      ))}
    </div>
  )
}
