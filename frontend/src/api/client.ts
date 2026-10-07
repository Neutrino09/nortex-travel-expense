// fetch wrapper + TanStack Query hooks for every endpoint in CLAUDE.md §11.
// Every mutation invalidates the relevant queries. Errors carry the server's `detail` string.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type {
  ActIn, ActOut, ClaimLineIn, ClockOut, ClaimLineOut, ClaimLinePatch, DisburseIn, EmployeeOut, FinanceQueue,
  ImportResult, InboxItem, PaymentOut, RequestIn, RequestListItem, RequestOut, RequestValidateOut,
  SettlementCreate, SettlementOut, SubmitOut, TimelineEvent, ValidationResult,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
  }
}

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const isForm = body instanceof FormData
  const res = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers: body !== undefined && !isForm ? { 'Content-Type': 'application/json' } : undefined,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const get = <T,>(p: string) => api<T>('GET', p)
export const post = <T,>(p: string, b?: unknown) => api<T>('POST', p, b ?? {})

// ---- query keys ----
export const qk = {
  me: ['me'] as const,
  employees: ['employees'] as const,
  requests: ['requests'] as const,
  request: (id: string) => ['requests', id] as const,
  settlement: (id: number) => ['settlements', id] as const,
  inbox: ['inbox'] as const,
  financeQueue: ['finance', 'queue'] as const,
  audit: (t?: string, id?: string) => ['audit', t, id] as const,
}

// ---- auth ----
export const useClock = () =>
  useQuery({ queryKey: ['clock'], queryFn: () => get<ClockOut>('/clock'), staleTime: Infinity })
export const useMe = () =>
  useQuery({ queryKey: qk.me, queryFn: () => get<EmployeeOut>('/auth/me'), retry: false })
export const useEmployees = () =>
  useQuery({ queryKey: qk.employees, queryFn: () => get<EmployeeOut[]>('/employees') })

// Login/logout change who "me" is, so everything cached must go.
export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (emp_code: string) => post<EmployeeOut>('/auth/login', { emp_code }),
    onSuccess: () => qc.clear(),
  })
}
export function useLogout() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: () => post<void>('/auth/logout'), onSuccess: () => qc.clear() })
}

// ---- requests ----
export const useRequests = () =>
  useQuery({ queryKey: qk.requests, queryFn: () => get<RequestListItem[]>('/requests') })
export const useRequest = (id: string | undefined) =>
  useQuery({ queryKey: qk.request(id ?? ''), queryFn: () => get<RequestOut>(`/requests/${id}`), enabled: !!id })

function useInvalidateAll() {
  const qc = useQueryClient()
  return () => qc.invalidateQueries() // simple and safe: state is small
}

export function useCreateRequest() {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: RequestIn) => post<RequestOut>('/requests', b), onSuccess: inv })
}
export function usePatchRequest(id: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: RequestIn) => api<RequestOut>('PATCH', `/requests/${id}`, b), onSuccess: inv })
}
export function useValidateRequest(id: string) {
  return useMutation({ mutationFn: () => post<RequestValidateOut>(`/requests/${id}/validate`) })
}
export function useSubmitRequest(id: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => post<SubmitOut>(`/requests/${id}/submit`), onSuccess: inv })
}
export function useResubmitRequest(id: string) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => post<SubmitOut>(`/requests/${id}/resubmit`), onSuccess: inv })
}

// ---- settlements ----
export function useCreateSettlement() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (b: SettlementCreate) => post<SettlementOut>('/settlements', b),
    onSuccess: inv,
  })
}
export const useSettlement = (id: number | undefined) =>
  useQuery({
    queryKey: qk.settlement(id ?? 0),
    queryFn: () => get<SettlementOut>(`/settlements/${id}`),
    enabled: id !== undefined,
  })
export function useAddLine(sid: number) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: (b: ClaimLineIn) => post<ClaimLineOut>(`/settlements/${sid}/lines`, b), onSuccess: inv })
}
export function usePatchLine(sid: number) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ lineId, patch }: { lineId: number; patch: ClaimLinePatch }) =>
      api<ClaimLineOut>('PATCH', `/settlements/${sid}/lines/${lineId}`, patch),
    onSuccess: inv,
  })
}
export function useDeleteLine(sid: number) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (lineId: number) => api<void>('DELETE', `/settlements/${sid}/lines/${lineId}`),
    onSuccess: inv,
  })
}
export function useImportFiles(sid: number) {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (files: File[]) => {
      const fd = new FormData()
      files.forEach((f) => fd.append('files', f))
      return post<ImportResult>(`/settlements/${sid}/import`, fd)
    },
    onSuccess: inv,
  })
}
export function useImportSample(sid: number) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => post<ImportResult>(`/settlements/${sid}/import-sample`), onSuccess: inv })
}
// Validation lives only on the server. Call after every edit (debounce 400 ms in the caller).
export function useValidateSettlement(sid: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => post<ValidationResult>(`/settlements/${sid}/validate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.settlement(sid) }),
  })
}
export function useSubmitSettlement(sid: number) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => post<SubmitOut>(`/settlements/${sid}/submit`), onSuccess: inv })
}
export function useResubmitSettlement(sid: number) {
  const inv = useInvalidateAll()
  return useMutation({ mutationFn: () => post<SubmitOut>(`/settlements/${sid}/resubmit`), onSuccess: inv })
}

// ---- evidence ----
export const evidenceFileUrl = (id: number) => `/api/evidence/${id}/file`

// ---- approvals ----
export const useInbox = () =>
  useQuery({ queryKey: qk.inbox, queryFn: () => get<InboxItem[]>('/approvals/inbox') })
export function useAct() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ entityType, entityId, body }: { entityType: string; entityId: string; body: ActIn }) =>
      post<ActOut>(`/approvals/${entityType}/${entityId}/act`, body),
    onSuccess: inv,
  })
}

// ---- finance ----
export const useFinanceQueue = () =>
  useQuery({ queryKey: qk.financeQueue, queryFn: () => get<FinanceQueue>('/finance/queue') })
export function useDisburseAdvance() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: ({ requestId, body }: { requestId: string; body: DisburseIn }) =>
      post<RequestOut>(`/finance/requests/${requestId}/disburse-advance`, body),
    onSuccess: inv,
  })
}
export function useMarkPaid() {
  const inv = useInvalidateAll()
  return useMutation({
    mutationFn: (paymentId: number) => post<PaymentOut>(`/finance/payments/${paymentId}/mark-paid`),
    onSuccess: inv,
  })
}

// ---- audit ----
export const useAudit = (entityType?: string, entityId?: string) =>
  useQuery({
    queryKey: qk.audit(entityType, entityId),
    queryFn: () => {
      const q = new URLSearchParams()
      if (entityType) q.set('entity_type', entityType)
      if (entityId) q.set('entity_id', entityId)
      return get<TimelineEvent[]>(`/audit?${q}`)
    },
  })

// Additive helper (Agent C): PATCH with a typed body for callers that manage ids dynamically.
export const patchJson = <T,>(p: string, b: unknown) => api<T>('PATCH', p, b)
