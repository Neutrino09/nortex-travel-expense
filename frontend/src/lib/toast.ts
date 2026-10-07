// Tiny toast store: any code (e.g. the global mutation error handler) can call toast().
export interface ToastMsg { id: number; text: string; tone: 'error' | 'success' }
let items: ToastMsg[] = []
let nextId = 1
const listeners = new Set<() => void>()
export const subscribeToasts = (l: () => void) => { listeners.add(l); return () => { listeners.delete(l) } }
export const getToasts = () => items
function emit() { items = [...items]; listeners.forEach((l) => l()) }
export function toast(text: string, tone: ToastMsg['tone'] = 'error') {
  const id = nextId++
  items = [...items, { id, text, tone }]
  emit()
  setTimeout(() => { items = items.filter((t) => t.id !== id); emit() }, 5000)
}
