let csrfToken = '';
export function setCsrfToken(value: string) { csrfToken = value; }
export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) { super(typeof detail === 'string' ? detail : JSON.stringify(detail)); }
}
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...options, credentials: 'include', headers: { 'Content-Type': 'application/json', ...(csrfToken ? {'X-CSRF-Token': csrfToken} : {}), ...options.headers } });
  const text = await response.text();
  let body: any;
  try { body = text ? JSON.parse(text) : null; } catch { throw new ApiError(response.status, '服务返回无效响应'); }
  if (!response.ok) throw new ApiError(response.status, body?.detail ?? body);
  return body as T;
}
export const idempotencyKey = () => crypto.randomUUID();

