// Light/dark toggle: a `dark` class on <html>, remembered in localStorage (index.html applies it before paint).
const KEY = 'theme'

export function isDark(): boolean {
  return document.documentElement.classList.contains('dark')
}

export function setDark(dark: boolean) {
  document.documentElement.classList.toggle('dark', dark)
  try { localStorage.setItem(KEY, dark ? 'dark' : 'light') } catch { /* storage blocked: still works for this visit */ }
}
