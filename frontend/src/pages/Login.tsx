import { useNavigate } from 'react-router-dom'
import { useEmployees, useLogin } from '@/api/client'
import { Card } from '@/components/ui/card'

// "Log in as" picker — no passwords (see README). Agent C builds the grouped version.
export default function Login() {
  const employees = useEmployees()
  const login = useLogin()
  const navigate = useNavigate()
  return (
    <div className="mx-auto max-w-3xl space-y-3 p-8">
      <h1 className="text-2xl font-semibold">Log in as…</h1>
      {employees.data?.map((e) => (
        <Card key={e.emp_code} className="cursor-pointer hover:bg-muted"
          onClick={() => login.mutate(e.emp_code, { onSuccess: () => navigate('/') })}>
          {e.name} · {e.designation} · {e.app_role}
        </Card>
      ))}
    </div>
  )
}
