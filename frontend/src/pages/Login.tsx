import { useNavigate } from 'react-router-dom'
import { useEmployees, useLogin } from '@/api/client'
import type { AppRole } from '@/api/types'
import { Card } from '@/components/ui/card'
import ToastHost from '@/components/ToastHost'

const GROUPS: { role: AppRole; label: string }[] = [
  { role: 'employee', label: 'Employee' },
  { role: 'manager', label: 'Manager' },
  { role: 'admin', label: 'Admin (Finance)' },
]

// "Log in as" picker — no passwords (see README). Authorization is enforced on the server.
export default function Login() {
  const employees = useEmployees()
  const login = useLogin()
  const navigate = useNavigate()
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Nortex Travel Expenses</h1>
        <p className="text-sm text-zinc-500">Log in as one of the demo people. There are no passwords.</p>
      </div>
      {employees.isLoading && <p>Loading…</p>}
      {employees.error && <p className="text-red-600">{employees.error.message}</p>}
      {GROUPS.map((g) => (
        <section key={g.role}>
          <h2 className="mb-2 text-xs font-semibold uppercase text-zinc-500">{g.label}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {employees.data?.filter((e) => e.app_role === g.role).map((e) => (
              <Card key={e.emp_code} className="cursor-pointer transition hover:border-primary hover:shadow-md"
                onClick={() => login.mutate(e.emp_code, { onSuccess: () => navigate('/') })}>
                <div className="font-medium">{e.name} <span className="text-xs text-zinc-400">{e.emp_code}</span></div>
                <div className="text-sm text-zinc-600">{e.designation}</div>
                <div className="text-xs text-zinc-500">{e.department}</div>
              </Card>
            ))}
          </div>
        </section>
      ))}
      <ToastHost />
    </div>
  )
}
