'use client';

import { FormEvent, useState } from 'react';

import { getToken } from '@/lib/api';

export default function LoginPage() {
  const [username, setUsername] = useState('tenant-alpha');
  const [password, setPassword] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setToken(null);

    try {
      const response = await getToken(username, password);
      setToken(response.access_token);
      if (typeof window !== 'undefined') {
        localStorage.setItem('argus_token', response.access_token);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 text-slate-950">
      <div className="mx-auto flex w-full max-w-md flex-col gap-6 px-6 py-12">
        <header className="flex flex-col gap-1">
          <p className="text-sm font-medium uppercase tracking-normal text-slate-500">Argus</p>
          <h1 className="text-2xl font-semibold tracking-normal">Sign in</h1>
        </header>

        <form className="grid gap-4 rounded-md border border-slate-200 bg-white p-6" onSubmit={handleSubmit}>
          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Tenant name
            <input
              className="h-11 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-900"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>

          <label className="grid gap-2 text-sm font-medium text-slate-700">
            Password
            <input
              type="password"
              className="h-11 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none focus:border-slate-900"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>

          <button
            className="h-11 rounded-md bg-slate-950 text-sm font-medium text-white disabled:cursor-not-allowed disabled:bg-slate-400"
            disabled={loading}
            type="submit"
          >
            {loading ? 'Signing in…' : 'Sign in'}
          </button>

          {error ? <p className="text-sm text-red-700">{error}</p> : null}
        </form>

        {token ? (
          <div className="rounded-md border border-green-200 bg-green-50 p-4">
            <p className="text-sm font-medium text-green-800">Signed in — token saved to localStorage.</p>
            <p className="mt-2 break-all font-mono text-xs text-green-700">{token}</p>
            <p className="mt-3 text-xs text-green-700">
              The token is pre-filled on the <a href="/query" className="underline">Query</a> and{' '}
              <a href="/dashboard" className="underline">Dashboard</a> pages.
            </p>
          </div>
        ) : null}
      </div>
    </main>
  );
}
