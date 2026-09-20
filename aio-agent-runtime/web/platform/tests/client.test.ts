import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiClient, ApiError, StaleResponseError, parseEvents } from '../src/api/client';
import type { Me, RunEvent } from '../src/api/types';

export const alice: Me = {
  user_id: '10000000-0000-4000-8000-000000000001',
  org_id: '20000000-0000-4000-8000-000000000001',
  display_name: 'Alice',
  organization_name: '测试组织',
  role: 'member',
  membership_revision: 0,
  csrf_token: 'synthetic-csrf-token',
  departments: [],
  permissions: { organization_admin: false, operations: false, audit: false },
  capabilities: {
    file_upload: true,
    python_compute: true,
    mcp: false,
    knowledge: false,
    skill_publishing: false,
    team: false,
  },
};
function body(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } });
}
function frame(run: string, seq: number, kind = 'run.started') {
  return `id: ${run}:${seq}\nevent: ${kind}\ndata: ${JSON.stringify({ schema_version: 1, run_id: run, seq, timestamp: '2026-09-11T00:00:00Z', payload: { state: 'running' } })}\n\n`;
}
function chunks(text: string, step = 7) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (let i = 0; i < bytes.length; i += step) controller.enqueue(bytes.slice(i, i + step));
      controller.close();
    },
  });
}
afterEach(() => vi.unstubAllGlobals());

describe('Identity-scoped API client', () => {
  let client: ApiClient;
  beforeEach(() => {
    client = new ApiClient();
  });
  it('sends CSRF only from bound session and never stores it in localStorage', async () => {
    const fetch = vi.fn().mockResolvedValue(body({ ok: true }));
    vi.stubGlobal('fetch', fetch);
    client.bind(alice);
    await client.request('/api/v2/projects', 'POST', { name: 'Private' });
    expect(fetch).toHaveBeenCalledOnce();
    const [path, options] = fetch.mock.calls[0];
    expect(path).toBe('/api/v2/projects');
    expect(options.credentials).toBe('same-origin');
    expect(new Headers(options.headers).get('X-CSRF-Token')).toBe(alice.csrf_token);
    expect(localStorage.getItem('harnessToken')).toBeNull();
    expect(localStorage.getItem('csrf_token')).toBeNull();
  });
  it('rejects a response from the previous user even when transport ignores abort', async () => {
    let complete!: (response: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            complete = resolve;
          }),
      ),
    );
    client.bind(alice);
    const pending = client.request('/api/v2/sessions');
    client.bind({ ...alice, user_id: '10000000-0000-4000-8000-000000000002', csrf_token: 'bob-csrf' });
    complete(body({ items: [{ title: 'Alice private' }] }));
    await expect(pending).rejects.toBeInstanceOf(StaleResponseError);
  });
  it('does not send requests to arbitrary external URLs', async () => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    await expect(client.request('https://evil.example.test/api')).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('does not expose raw upstream error text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('private password=do-not-display', { status: 500 })),
    );
    await expect(client.request('/api/v2/runs')).rejects.toMatchObject({
      message: '请求未完成，请稍后重试。',
    });
  });
  it('invalidates browser identity on authentication failure', async () => {
    client.bind(alice);
    const lost = vi.fn();
    client.addEventListener('auth-lost', lost);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(body({ error: { code: 'AUTH_REQUIRED' } }, 401)));
    await expect(client.request('/api/v2/me')).rejects.toBeInstanceOf(ApiError);
    expect(lost).toHaveBeenCalledOnce();
  });
  it('sends upload bytes with a CSRF header but never JSON-encodes the file', async () => {
    const fetch = vi.fn().mockResolvedValue(body({ id: 'artifact' }));
    vi.stubGlobal('fetch', fetch);
    client.bind(alice);
    const blob = new Blob(['abc']);
    await client.request('/api/v2/uploads/id/content', 'PUT', undefined, {
      body: blob,
      headers: { 'Content-Type': 'application/octet-stream' },
    });
    expect(fetch.mock.calls[0][1].body).toBe(blob);
  });
});

describe('Strict durable event replay', () => {
  const run = '40000000-0000-4000-8000-000000000001';
  it('handles arbitrary chunk splits, heartbeats, CRLF and duplicate frames', async () => {
    const output: RunEvent[] = [];
    const source = (': heartbeat\n\n' + frame(run, 1) + frame(run, 1) + frame(run, 2)).replaceAll(
      '\n',
      '\r\n',
    );
    await parseEvents(chunks(source, 3), run, 0, (e) => output.push(e));
    expect(output.map((e) => e.seq)).toEqual([1, 2]);
  });
  it('starts replay after the last known sequence without reapplying older events', async () => {
    const result: RunEvent[] = [];
    await parseEvents(chunks(frame(run, 1) + frame(run, 2) + frame(run, 3)), run, 2, (e) => result.push(e));
    expect(result.map((e) => e.seq)).toEqual([3]);
  });
  it('rejects frames from another run', async () => {
    await expect(parseEvents(chunks(frame('other-run', 1)), run, 0, () => {})).rejects.toBeInstanceOf(
      ApiError,
    );
  });
  it('rejects sequence gaps rather than silently hiding lost events', async () => {
    await expect(parseEvents(chunks(frame(run, 2)), run, 0, () => {})).rejects.toMatchObject({
      code: 'STREAM_CURSOR_GAP',
    });
  });
  it('rejects malformed JSON and oversized frames', async () => {
    await expect(parseEvents(chunks('id: 1\nevent: bad\ndata: {\n\n'), run, 0, () => {})).rejects.toThrow();
    await expect(
      parseEvents(chunks('x'.repeat(1024 * 1024 + 10), 131072), run, 0, () => {}),
    ).rejects.toMatchObject({ code: 'STREAM_FRAME_TOO_LARGE' });
  });
  it('does not render unsupported schema versions', async () => {
    await expect(
      parseEvents(
        chunks(frame(run, 1).replace('"schema_version":1', '"schema_version":7')),
        run,
        0,
        () => {},
      ),
    ).rejects.toBeInstanceOf(ApiError);
  });
  it('cancels the stream when a rejected frame cannot be consumed', async () => {
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(new TextEncoder().encode(frame('wrong', 1)));
      },
      cancel,
    });
    await expect(parseEvents(stream, run, 0, () => {})).rejects.toThrow();
    expect(cancel).toHaveBeenCalledOnce();
  });
});
