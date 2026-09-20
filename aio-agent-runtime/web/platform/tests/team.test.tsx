import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { AuthProvider } from '../src/auth';
import { api } from '../src/api/client';
import type { Me, Run, RunTeam } from '../src/api/types';
import { Layout } from '../src/components/Layout';
import { Conversation } from '../src/features/Conversation';
import { AdminPage } from '../src/features/Admin';
import { TeamProgress } from '../src/features/TeamProgress';
import { useRun } from '../src/run';

const id = (n: number) => `${n}0000000-0000-4000-8000-000000000001`;
const rid = id(6),
  sid = id(5),
  aid = id(4),
  pid = id(3);
const me: Me = {
  user_id: id(1),
  org_id: id(2),
  display_name: '验收成员',
  organization_name: '合成组织',
  role: 'org_admin',
  membership_revision: 0,
  csrf_token: 'team-test-csrf',
  departments: [],
  permissions: { organization_admin: true, operations: true, audit: true },
  capabilities: {
    file_upload: false,
    python_compute: true,
    mcp: false,
    knowledge: false,
    skill_publishing: false,
    team: true,
  },
};
const team: RunTeam = {
  stage: 'step',
  current_step: 1,
  steps: [
    {
      id: id(7),
      ordinal: 1,
      title: '分析已授权数据',
      task: '只读任务',
      tools: ['approved_read'],
      state: 'running',
      input_checkpoint_seq: 4,
      output_checkpoint_seq: null,
      result: null,
      started_at: null,
      finished_at: null,
    },
    {
      id: id(8),
      ordinal: 2,
      title: '记录结论',
      task: '仅根据实际结果汇总',
      tools: [],
      state: 'pending',
      input_checkpoint_seq: null,
      output_checkpoint_seq: null,
      result: null,
      started_at: null,
      finished_at: null,
    },
  ],
};
const baseRun: Run = {
  id: rid,
  state: 'running',
  revision: 1,
  generation: 1,
  result: null,
  error_code: null,
  cleanup_state: 'not_allocated',
  created_at: '2026-09-12T00:00:00Z',
  finished_at: null,
  next_event_seq: 0,
  mode: 'team',
  team: { stage: 'planning', current_step: 0, steps: [] },
};
const response = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } });
function server(extra: (path: string, init: RequestInit) => Response | Promise<Response> | undefined) {
  const requests: Array<{ path: string; init: RequestInit }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const path = String(input);
      requests.push({ path, init });
      const value = extra(path, init);
      if (value) return value;
      if (path === '/api/v2/me') return response(me);
      if (
        [
          '/api/v2/projects',
          '/api/v2/sessions',
          '/api/v2/admin/agents',
          '/api/v2/admin/tools',
          '/api/v2/skills',
        ].includes(path)
      )
        return response({ items: [] });
      return response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404);
    }),
  );
  return requests;
}
function mount(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/app/sessions/:sessionId" element={<Conversation />} />
            <Route path="/app/admin/:section" element={<AdminPage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}
beforeEach(() => {
  api.invalidate();
  localStorage.clear();
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value: function () {
      this.setAttribute('open', '');
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value: function () {
      this.removeAttribute('open');
    },
  });
  HTMLElement.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  api.invalidate();
  vi.unstubAllGlobals();
});

it('publishes explicit bounded team policy, not arbitrary agent identities', async () => {
  const requests = server((path, init) => {
    if (path === '/api/v2/admin/models')
      return response({
        items: [
          {
            id: aid,
            model: 'synthetic',
            provider: 'test',
            status: 'active',
            config: { max_call_charge: '0.01' },
          },
        ],
      });
    if (path === '/api/v2/admin/agents' && init.method === 'POST') return response({ id: aid });
  });
  mount('/app/admin/agents');
  await userEvent.click(await screen.findByRole('button', { name: '新建 Agent' }));
  await userEvent.type(screen.getByLabelText('Agent 名称'), '受限多步骤助手');
  await userEvent.click(screen.getByLabelText('启用多步骤协作（Team）'));
  await userEvent.clear(screen.getByLabelText('最多任务步骤'));
  await userEvent.type(screen.getByLabelText('最多任务步骤'), '3');
  await userEvent.click(screen.getByRole('button', { name: '发布这个版本' }));
  await waitFor(() => expect(requests.some((r) => r.init.method === 'POST')).toBe(true));
  const body = JSON.parse(requests.find((r) => r.init.method === 'POST')!.init.body as string);
  expect(body.team).toEqual({ max_steps: 3, max_step_rounds: 3 });
  expect(body).not.toHaveProperty('user_id');
  expect(body.team).not.toHaveProperty('model_id');
});

it.each([true, false])(
  'only offers team for an opted-in agent and freezes the submitted mode on retry (%s)',
  async (enabled) => {
    const requests = server((path) => {
      if (path === `/api/v2/sessions/${sid}`)
        return response({
          id: sid,
          project_id: pid,
          agent_version_id: aid,
          title: '合成会话',
          revision: 0,
          messages: [],
          runs: [],
          supported_modes: enabled ? ['single', 'team'] : ['single'],
        });
      if (path.endsWith('/runs')) return Promise.reject(new TypeError('synthetic lost response'));
    });
    mount(`/app/sessions/${sid}`);
    await userEvent.type(await screen.findByLabelText('任务内容'), '执行任务');
    if (enabled) await userEvent.selectOptions(screen.getByLabelText('执行方式'), 'team');
    else expect(screen.queryByLabelText('执行方式')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /发送任务/ }));
    await screen.findByText(/连接暂时不可用/);
    if (enabled) expect(screen.getByLabelText('执行方式')).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /重试同一提交/ }));
    const posts = requests.filter((r) => r.init.method === 'POST');
    expect(posts).toHaveLength(2);
    expect(JSON.parse(posts[0].init.body as string).mode).toBe(enabled ? 'team' : 'single');
    expect(posts[0].init.body).toBe(posts[1].init.body);
    expect(new Headers(posts[0].init.headers).get('Idempotency-Key')).toBe(
      new Headers(posts[1].init.headers).get('Idempotency-Key'),
    );
  },
);

it('renders durable denial/skipped states as authority, without evaluating step output HTML', () => {
  const { container } = render(
    <TeamProgress
      runState="failed"
      team={{
        ...team,
        stage: 'completed',
        steps: [
          {
            ...team.steps[0],
            state: 'denied',
            output_checkpoint_seq: 8,
            result: { answer: '<script>bad()</script>', reason_codes: ['TOOL_DENIED'] },
          },
          { ...team.steps[1], state: 'skipped' },
        ],
      }}
    />,
  );
  expect(screen.getByText('操作被拒绝')).toBeInTheDocument();
  expect(screen.getByText('未执行')).toBeInTheDocument();
  expect(screen.getByText('TOOL_DENIED')).toBeInTheDocument();
  expect(container.querySelector('script')).toBeNull();
});

function Watch() {
  const live = useRun(rid);
  return (
    <>
      <output aria-label="最终回答草稿">{live.draft}</output>
      <output aria-label="文件检查点">{live.run?.workspace_checkpoint?.state ?? 'none'}</output>
      <p>{live.error}</p>
      {live.run?.team && <TeamProgress team={live.run.team} runState={live.run.state} />}
    </>
  );
}

it('does not let an older in-flight projection restore content after stream authorization fails', async () => {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  let respond: (value: Response) => void;
  let reads = 0;
  server((path) => {
    if (path === `/api/v2/runs/${rid}`) {
      reads++;
      if (reads === 1) return response({ ...baseRun, team });
      if (reads === 2)
        return new Promise<Response>((resolve) => {
          respond = resolve;
        });
      return response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404);
    }
    if (path.endsWith('/events'))
      return new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            controller = c;
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      );
  });
  render(<Watch />);
  await screen.findByText('1. 分析已授权数据');
  await act(async () => {
    controller!.enqueue(frame(1, 'team.plan.committed', { steps: 2 }));
  });
  await waitFor(() => expect(reads).toBe(2));
  await act(async () => {
    controller!.close();
  });
  await screen.findByText('内容不存在，或你没有访问权限。');
  await act(async () => {
    respond!(response({ ...baseRun, team, revision: 99 }));
  });
  expect(screen.queryByLabelText('团队步骤')).not.toBeInTheDocument();
});
function frame(seq: number, kind: string, payload: object) {
  return new TextEncoder().encode(
    `id: ${rid}:${seq}\nevent: ${kind}\ndata: ${JSON.stringify({
      schema_version: 1,
      run_id: rid,
      seq,
      timestamp: '2026-09-12T00:00:01Z',
      payload,
    })}\n\n`,
  );
}

it('refreshes a file checkpoint during an open stream without waiting for an approval event', async () => {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  let saved = false;
  const checkpoint = {
    id: id(9),
    state: 'ready',
    generation: 1,
    engine_checkpoint_seq: 8,
    file_count: 1,
    bytes: 2,
    preserved_state: 'filesystem_only',
    manager_acknowledged: true,
  };
  const requests = server((path) => {
    if (path === `/api/v2/runs/${rid}`)
      return response(saved ? { ...baseRun, revision: 5, workspace_checkpoint: checkpoint } : baseRun);
    if (path.endsWith('/events'))
      return new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            controller = c;
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      );
  });
  const mounted = render(<Watch />);
  await waitFor(() => expect(requests.some((r) => r.path.endsWith('/events'))).toBe(true));
  saved = true;
  await act(async () => {
    controller!.enqueue(
      frame(1, 'workspace.checkpointed', { checkpoint_id: id(9), preserved_state: 'filesystem_only' }),
    );
  });
  await waitFor(() => expect(screen.getByLabelText('文件检查点')).toHaveTextContent('ready'));
  expect(screen.getByLabelText('最终回答草稿')).toBeEmptyDOMElement();
  mounted.unmount();
});

it('refreshes durable team steps during an open stream and never mixes internal deltas into the final draft', async () => {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  let changed = false;
  const requests = server((path) => {
    if (path === `/api/v2/runs/${rid}`)
      return response(changed ? { ...baseRun, revision: 4, team } : baseRun);
    if (path.endsWith('/events'))
      return new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            controller = c;
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      );
  });
  const mounted = render(<Watch />);
  await screen.findByText('计划尚未提交，暂无已执行步骤。');
  await waitFor(() => expect(requests.some((r) => r.path.endsWith('/events'))).toBe(true));
  changed = true;
  await act(async () => {
    controller!.enqueue(
      frame(1, 'team.output.delta', { segment_id: 'planning', text: 'INTERNAL PLANNER TEXT' }),
    );
    controller!.enqueue(frame(2, 'team.plan.committed', { steps: 2 }));
  });
  expect(await screen.findByText('1. 分析已授权数据')).toBeInTheDocument();
  expect(screen.getByLabelText('最终回答草稿')).toBeEmptyDOMElement();
  await act(async () => {
    controller!.enqueue(frame(3, 'answer.delta', { segment_id: 'synthesis', text: '最终汇总' }));
  });
  expect(screen.getByLabelText('最终回答草稿')).toHaveTextContent('最终汇总');
  expect(screen.queryByText('INTERNAL PLANNER TEXT')).not.toBeInTheDocument();
  mounted.unmount();
});

it('clears team and draft projections when current source authorization is revoked', async () => {
  let controller: ReadableStreamDefaultController<Uint8Array>;
  let revoked = false;
  const requests = server((path) => {
    if (path === `/api/v2/runs/${rid}`)
      return revoked
        ? response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404)
        : response({ ...baseRun, team });
    if (path.endsWith('/events'))
      return new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            controller = c;
          },
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      );
  });
  render(<Watch />);
  await screen.findByText('1. 分析已授权数据');
  await waitFor(() => expect(requests.some((r) => r.path.endsWith('/events'))).toBe(true));
  revoked = true;
  await act(async () => {
    controller!.enqueue(frame(1, 'team.step.completed', { step_id: id(7) }));
  });
  await screen.findByText('内容不存在，或你没有访问权限。');
  expect(screen.queryByLabelText('团队步骤')).not.toBeInTheDocument();
  expect(screen.getByLabelText('最终回答草稿')).toBeEmptyDOMElement();
});
