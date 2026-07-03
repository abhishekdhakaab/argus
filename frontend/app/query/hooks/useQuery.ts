'use client';

import { useCallback, useState } from 'react';

import { AgentEventSchema, type DoneEvent } from '@/lib/schemas';

type DoneState = DoneEvent['data'] | null;

export function useAgentQuery() {
  const [steps, setSteps] = useState<string[]>([]);
  const [answer, setAnswer] = useState('');
  const [done, setDone] = useState<DoneState>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const submit = useCallback(async (query: string, token: string) => {
    const startedAt = performance.now();
    setSteps([]);
    setAnswer('');
    setDone(null);
    setError(null);
    setRunning(true);

    try {
      const response = await fetch('/api/v1/query', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) {
        throw new Error(`Query request failed with status ${response.status}`);
      }
      if (!response.body) {
        throw new Error('Query response did not include a readable stream');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          if (!part.startsWith('data: ')) {
            continue;
          }

          const raw = part.slice(6).trim();
          if (!raw) {
            continue;
          }

          try {
            const event = AgentEventSchema.parse(JSON.parse(raw));
            if (event.type === 'step') {
              setSteps((previous) => [...previous, event.data.message]);
            }
            if (event.type === 'token') {
              setAnswer((previous) => previous + event.data);
            }
            if (event.type === 'done') {
              setDone(event.data);
            }
          } catch (parseError) {
            console.error('Failed to parse SSE event', { raw, parseError });
          }
        }
      }

      const durationMs = Math.round(performance.now() - startedAt);
      console.info('agent_query_stream_complete', { query_len: query.length, duration_ms: durationMs });
    } catch (streamError) {
      const message = streamError instanceof Error ? streamError.message : 'Unknown query stream error';
      setError(message);
      console.error('agent_query_stream_failed', { query_len: query.length, error: streamError });
      throw streamError;
    } finally {
      setRunning(false);
    }
  }, []);

  return { steps, answer, done, error, running, submit };
}
