// Money is integer paise everywhere. Never use floats for money.
export function formatINR(paise: number): string {
  const sign = paise < 0 ? '-' : ''
  const abs = Math.abs(paise)
  const rupees = Math.floor(abs / 100)
  const ps = String(abs % 100).padStart(2, '0')
  return `${sign}₹${rupees.toLocaleString('en-IN')}.${ps}`
}

// ISO date (YYYY-MM-DD) or datetime -> "16 Jun 2026"
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

// Rupee text input ("1,234.5") -> paise integer, without float maths.
export function rupeesToPaise(input: string): number {
  const clean = input.replace(/[,₹\s]/g, '')
  if (!/^\d*\.?\d{0,2}$/.test(clean) || clean === '' || clean === '.') return 0
  const [r, p = ''] = clean.split('.')
  return Number(r || '0') * 100 + Number(p.padEnd(2, '0'))
}
