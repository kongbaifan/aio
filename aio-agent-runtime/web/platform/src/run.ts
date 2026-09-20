import { useEffect, useRef, useState } from 'react';
import { api, ApiError, explain, isAbort } from './api/client';
import type { Run, RunEvent } from './api/types';
import { TERMINAL } from './components/ui';

export function useRun(runId: string | null) {
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState('');
  const [connected, setConnected] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const sequence = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    sequence.current = 0;
    setRun(null);
    setEvents([]);
    setDraft('');
    setError('');
    setConnected(false);
    if (!runId) return () => controller.abort();
    let stopped = false;
    const parts = new Map<string, string>();
    let projection: Promise<void> | null = null;
    let projectionDirty = false;
    function acceptSnapshot(current: Run) {
      if (controller.signal.aborted) return;
      setRun((old) => (!old || current.revision >= old.revision ? current : old));
    }
    function refreshProjection() {
      projectionDirty = true;
      if (projection) return;
      projection = (async () => {
        while (projectionDirty && !controller.signal.aborted) {
          projectionDirty = false;
          try {
            const current = await api.request<Run>(`/api/v2/runs/${runId}`, 'GET', undefined, {
              signal: controller.signal,
            });
            acceptSnapshot(current);
          } catch (error) {
            if (controller.signal.aborted || isAbort(error)) return;
            setError(explain(error));
            if (error instanceof ApiError && [401, 403, 404, 409, 410].includes(error.status)) {
              stopped = true;
              parts.clear();
              setRun(null);
              setDraft('');
              setEvents([]);
              setConnected(false);
              controller.abort();
            }
            return;
          }
        }
      })().finally(() => {
        projection = null;
      });
    }
    const delay = (ms: number) =>
      new Promise<void>((resolve) => {
        const id = setTimeout(done, ms);
        function done() {
          clearTimeout(id);
          controller.signal.removeEventListener('abort', done);
          resolve();
        }
        controller.signal.addEventListener('abort', done, { once: true });
      });
    async function watch() {
      let attempts = 0;
      while (!controller.signal.aborted && !stopped) {
        try {
          const current = await api.request<Run>(`/api/v2/runs/${runId}`, 'GET', undefined, {
            signal: controller.signal,
          });
          if (controller.signal.aborted) return;
          acceptSnapshot(current);
          await api.events(runId!, sequence.current, controller.signal, (event) => {
            sequence.current = event.seq;
            setConnected(true);
            if (!['answer.delta', 'team.output.delta'].includes(event.kind)) {
              setEvents((old) => [...old, event].slice(-100));
            }
            if (
              (event.kind.startsWith('team.') && event.kind !== 'team.output.delta') ||
              event.kind.startsWith('approval.') ||
              event.kind.startsWith('workspace.')
            ) {
              refreshProjection();
            }
            if (event.kind === 'answer.delta' && typeof event.payload.text === 'string') {
              const segment =
                typeof event.payload.segment_id === 'string' ? event.payload.segment_id : 'answer';
              parts.set(segment, (parts.get(segment) ?? '') + event.payload.text);
              const last = [...parts.values()].at(-1) ?? '';
              setDraft(last.slice(-262144));
            }
          });
          if (controller.signal.aborted) return;
          const final = await api.request<Run>(`/api/v2/runs/${runId}`, 'GET', undefined, {
            signal: controller.signal,
          });
          acceptSnapshot(final);
          attempts = 0;
          setError('');
          if (TERMINAL.has(final.state)) {
            stopped = true;
            setConnected(false);
            return;
          }
        } catch (error) {
          if (controller.signal.aborted || isAbort(error)) return;
          setConnected(false);
          setError(explain(error));
          if (error instanceof ApiError && [401, 403, 404, 409, 410].includes(error.status)) {
            stopped = true;
            parts.clear();
            setRun(null);
            setDraft('');
            setEvents([]);
            controller.abort();
            return;
          }
          attempts++;
        }
        await delay(Math.min(10000, 500 * 2 ** Math.min(attempts, 5)));
      }
    }
    void watch();
    return () => controller.abort();
  }, [runId, refresh]);
  return { run, events, draft, error, connected, reconnect: () => setRefresh((v) => v + 1) };
}
