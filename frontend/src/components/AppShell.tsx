import { LayoutDashboard, FileText, CheckSquare, Landmark } from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useInbox, useLogout, useMe } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import ToastHost from './ToastHost'

const link = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${isActive ? 'bg-green-50 text-primary' : 'text-zinc-600 hover:bg-zinc-100'}`

function ApprovalsLink() {
  const inbox = useInbox()
  const n = inbox.data?.length ?? 0
  return (
    <NavLink to="/approvals" className={link}>
      <CheckSquare size={16} /> Approvals
      {n > 0 && <span className="ml-auto rounded-full bg-primary px-2 text-xs text-white">{n}</span>}
    </NavLink>
  )
}

const roleLabel = { employee: 'Employee', manager: 'Manager', admin: 'Admin · Finance' } as const

export default function AppShell() {
  const me = useMe()
  const logout = useLogout()
  const navigate = useNavigate()
  const reviewing = /^\/(approvals|finance)/.test(useLocation().pathname)  // someone else's items
  const u = me.data
  if (!u) return null
  const initials = u.name.split(' ').map((p) => p[0]).slice(0, 2).join('')
  return (
    <div className="flex min-h-screen">
      <aside className="w-56 shrink-0 border-r border-border bg-white p-4">
        <div className="mb-6 text-lg font-bold text-primary">Nortex Travel</div>
        <nav className="space-y-1">
          <NavLink to="/" end className={link}><LayoutDashboard size={16} /> Dashboard</NavLink>
          <NavLink to="/claims" className={link}><FileText size={16} /> Claims</NavLink>
          {u.app_role === 'manager' && <ApprovalsLink />}
          {u.app_role === 'admin' && <NavLink to="/finance" className={link}><Landmark size={16} /> Finance</NavLink>}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex items-center justify-between border-b border-border bg-white px-6 py-3">
          <span className={`rounded-full px-3 py-1 text-xs font-medium ${reviewing ? 'bg-blue-50 text-blue-800' : 'bg-green-50 text-primary'}`}>
            {reviewing ? "● You're reviewing other people's items" : "● You're viewing your own claims"}
          </span>
          <div className="flex items-center gap-3">
            <Badge tone="blue">{roleLabel[u.app_role]}</Badge>
            <span className="text-sm font-medium">{u.name}</span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs font-semibold text-white">{initials}</span>
            <Button variant="outline" onClick={() => logout.mutate(undefined, { onSuccess: () => navigate('/login') })}>Switch user</Button>
          </div>
        </header>
        <main className="mx-auto max-w-6xl p-6"><Outlet /></main>
      </div>
      <ToastHost />
    </div>
  )
}
