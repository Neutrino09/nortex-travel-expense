import { Navigate, Route, Routes } from 'react-router-dom'
import { useMe } from '@/api/client'
import Login from '@/pages/Login'

// Phase 1 skeleton: routes are wired in phase 2 (Agent C builds the screens in CLAUDE.md §12).
export default function App() {
  const me = useMe()
  if (me.isLoading) return <div className="p-8 text-muted-foreground">Loading…</div>
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="*" element={me.data ? <div className="p-8">Signed in as {me.data.name}</div> : <Navigate to="/login" replace />} />
    </Routes>
  )
}
