'use client';

import { FormEvent, useState } from 'react';

import { UsageStatsSchema, type UsageStats } from '@/lib/schemas';

const defaultTenantId = '00000000-0000-0000-0000-000000000001';

export default function DashboardPage() {
  const [tenantId, setTenantId] = useState(defaultTenantId);
  const [token, setToken] = useState('');
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function loadUsage(event: FormEvent<HTMLFormElement>) {
    const startedAt = performance.now();
    event.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/v1/tenants/${tenantId}/usage`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        throw new Error(`Usage request failed with status ${response.status}`);
      }
      const parsed = UsageStatsSchema.parse(await response.json());
      setUsage(parsed);
      console.info('usage_dashboard_load_complete', {
        tenant_id: tenantId,
        queries_today: parsed.queries_today,
        duration_ms: Math.round(performance.now() - startedAt),
      });
    } catch (usageError) {
      const message = usageError instanceof Error ? usageError.message : 'Unknown usage error';
      setError(message);
      console.error('usage_dashboard_load_failed', { tenant_id: tenantId, error: usageError });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-6">
        <header className="flex flex-col gap-1 border-b border-slate-200 pb-4">
          <p className="text-sm font-medium uppercase tracking-normal text-slate-500">Argus</p>
          <h1 className="text-2xl font-semibold tracking-normal">Usage dashboard</h1>
        </header>

        <form className="grid gap-4 border-b border-slate-200 pb-6 md:grid-cols-[1fr_1fr_auto]" onSubmit={loadUsage}>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Tenant ID
            <input
              className="h-11 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-900"
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
              required
            />
          </label>

          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Bearer token
            <input
              className="h-11 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-900"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="eyJ..."
              required
            />
          </label>

          <button
            className="mt-auto h-11 rounded-md bg-slate-950 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            disabled={loading}
            type="submit"
          >
            {loading ? 'Loading' : 'Load usage'}
          </button>
        </form>

        {usage ? (
          <section className="grid gap-4 md:grid-cols-3">
            <Metric label="Queries today" value={usage.queries_today.toString()} />
            <Metric label="Avg latency" value={`${Math.round(usage.avg_latency_ms)} ms`} />
            <Metric label="P95 latency" value={`${Math.round(usage.p95_latency_ms)} ms`} />
            <Metric label="Total cost" value={`$${usage.total_cost_usd.toFixed(6)}`} />
            <Metric label="Avg cost" value={`$${usage.avg_cost_per_query.toFixed(6)}`} />
            <Metric label="Top tools" value={usage.top_tools.join(', ') || 'None'} />
          </section>
        ) : null}

        {error ? <p className="text-sm text-red-700">{error}</p> : null}
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-normal text-slate-500">{label}</p>
      <p className="mt-3 text-2xl font-semibold tracking-normal text-slate-950">{value}</p>
    </div>
  );
}
