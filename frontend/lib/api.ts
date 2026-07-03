import { TokenResponseSchema, UsageStatsSchema, type TokenResponse, type UsageStats } from './schemas';

const GATEWAY = '';  // Next.js rewrites /api/* → FastAPI

async function request<T>(path: string, options: RequestInit, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${GATEWAY}${path}`, { ...options, headers });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export async function getToken(username: string, password: string): Promise<TokenResponse> {
  const data = await request('/api/v1/auth/token', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  return TokenResponseSchema.parse(data);
}

export async function refreshToken(token: string): Promise<TokenResponse> {
  const data = await request('/api/v1/auth/refresh', { method: 'POST' }, token);
  return TokenResponseSchema.parse(data);
}

export async function ingestDocument(
  text: string,
  source: string,
  token: string,
): Promise<{ chunks_inserted: number; source: string }> {
  return request(
    '/api/v1/ingest/documents',
    { method: 'POST', body: JSON.stringify({ text, source }) },
    token,
  );
}

export async function getUsage(tenantId: string, token: string): Promise<UsageStats> {
  const data = await request(`/api/v1/tenants/${tenantId}/usage`, { method: 'GET' }, token);
  return UsageStatsSchema.parse(data);
}
