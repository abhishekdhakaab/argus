'use client';

import { FormEvent, useEffect, useState } from 'react';

import { ingestDocument } from '@/lib/api';

export default function IngestPage() {
  const [token, setToken] = useState('');
  const [source, setSource] = useState('');
  const [text, setText] = useState('');
  const [result, setResult] = useState<{ chunks_inserted: number; source: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setToken(localStorage.getItem('argus_token') ?? '');
    }
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await ingestDocument(text, source, token);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ingest failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-6">
        <header className="flex flex-col gap-1 border-b border-slate-200 pb-4">
          <p className="text-sm font-medium uppercase tracking-normal text-slate-500">Argus</p>
          <h1 className="text-2xl font-semibold tracking-normal">Ingest document</h1>
        </header>

        <form className="grid gap-4" onSubmit={handleSubmit}>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Bearer token
            <input
              className="h-11 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-900"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="eyJ..."
              required
            />
          </label>

          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Source name
            <input
              className="h-11 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-900"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="q3-cloud-policy.pdf"
              required
            />
          </label>

          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Document text
            <textarea
              className="min-h-48 rounded-md border border-slate-300 bg-white px-3 py-3 text-sm leading-6 outline-none focus:border-slate-900"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste the full document content here…"
              required
            />
          </label>

          <button
            className="h-11 w-fit rounded-md bg-slate-950 px-4 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            disabled={loading}
            type="submit"
          >
            {loading ? 'Ingesting…' : 'Ingest document'}
          </button>
        </form>

        {result ? (
          <div className="rounded-md border border-green-200 bg-green-50 p-4">
            <p className="text-sm font-medium text-green-800">
              Ingested <span className="font-mono">{result.source}</span> — {result.chunks_inserted} chunk
              {result.chunks_inserted !== 1 ? 's' : ''} inserted.
            </p>
          </div>
        ) : null}

        {error ? <p className="text-sm text-red-700">{error}</p> : null}
      </div>
    </main>
  );
}
