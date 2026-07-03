'use client';

import { FormEvent, useState } from 'react';

import { useAgentQuery } from './hooks/useQuery';

const defaultQuery = 'compare our cloud budget policy from the docs with actual Q3 spending numbers';

export default function QueryPage() {
  const [query, setQuery] = useState(defaultQuery);
  const [token, setToken] = useState('');
  const { steps, answer, done, error, running, submit } = useAgentQuery();

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    const startedAt = performance.now();
    event.preventDefault();
    await submit(query, token);
    console.info('query_form_submit_complete', {
      query_len: query.length,
      duration_ms: Math.round(performance.now() - startedAt),
    });
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-6">
        <header className="flex flex-col gap-1 border-b border-slate-200 pb-4">
          <p className="text-sm font-medium uppercase tracking-normal text-slate-500">Argus</p>
          <h1 className="text-2xl font-semibold tracking-normal">Enterprise intelligence query</h1>
        </header>

        <form className="grid gap-4 border-b border-slate-200 pb-6" onSubmit={handleSubmit}>
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

          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Query
            <textarea
              className="min-h-28 rounded-md border border-slate-300 bg-white px-3 py-3 text-sm leading-6 outline-none focus:border-slate-900"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              required
            />
          </label>

          <button
            className="h-11 w-fit rounded-md bg-slate-950 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            disabled={running}
            type="submit"
          >
            {running ? 'Running' : 'Run query'}
          </button>
        </form>

        <section className="grid gap-6 lg:grid-cols-[280px_1fr]">
          <div className="rounded-md border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold tracking-normal text-slate-900">Agent steps</h2>
            <ol className="mt-4 grid gap-3 text-sm text-slate-700">
              {steps.map((step, index) => (
                <li className="flex gap-3" key={`${step}-${index}`}>
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-slate-100 text-xs font-medium">
                    {index + 1}
                  </span>
                  <span className="pt-0.5">{step}</span>
                </li>
              ))}
            </ol>
          </div>

          <div className="rounded-md border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between gap-4">
              <h2 className="text-sm font-semibold tracking-normal text-slate-900">Answer</h2>
              {done ? (
                <span className="text-xs text-slate-500">
                  ${done.cost_usd.toFixed(6)} · {done.latency_ms} ms
                </span>
              ) : null}
            </div>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-slate-800">{answer}</p>
            {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
