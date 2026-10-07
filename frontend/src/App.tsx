import { Navigate, Route, Routes } from 'react-router-dom'
import { useMe } from '@/api/client'
import AppShell from '@/components/AppShell'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import Claims from '@/pages/Claims'
import RequestForm from '@/pages/RequestForm'
import RequestDetail from '@/pages/RequestDetail'
import SettlementEditor from '@/pages/SettlementEditor'
import ApprovalsInbox from '@/pages/ApprovalsInbox'
import ReviewItem from '@/pages/ReviewItem'
import Finance from '@/pages/Finance'

export default function App() {
  const me = useMe()
  if (me.isLoading) return <div className="p-8 text-zinc-500">Loading…</div>
  const authed = !!me.data
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={authed ? <AppShell /> : <Navigate to="/login" replace />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/claims" element={<Claims />} />
        <Route path="/requests/new" element={<RequestForm />} />
        <Route path="/requests/:id/edit" element={<RequestForm />} />
        <Route path="/requests/:id" element={<RequestDetail />} />
        <Route path="/settlements/:id" element={<SettlementEditor />} />
        <Route path="/approvals" element={<ApprovalsInbox />} />
        <Route path="/approvals/:entityType/:entityId" element={<ReviewItem />} />
        <Route path="/finance" element={<Finance />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
