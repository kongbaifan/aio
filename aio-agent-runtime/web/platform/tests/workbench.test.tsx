import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../src/auth';
import { api } from '../src/api/client';
import type { Me } from '../src/api/types';
import { Layout } from '../src/components/Layout';
import { Modal } from '../src/components/ui';
import { Home } from '../src/features/Home';
import { Conversation, Markdown } from '../src/features/Conversation';
import { AdminPage } from '../src/features/Admin';
import { UsagePage } from '../src/features/WorkspacePages';

const user: Me = {
  user_id: '10000000-0000-4000-8000-000000000001',
  org_id: '20000000-0000-4000-8000-000000000001',
  display_name: '同事甲',
  organization_name: '样例组织',
  role: 'member',
  membership_revision: 0,
  csrf_token: 'synthetic-ui-csrf',
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
const pid = '30000000-0000-4000-8000-000000000001',
  aid = '40000000-0000-4000-8000-000000000001',
  sid = '50000000-0000-4000-8000-000000000001',
  rid = '60000000-0000-4000-8000-000000000001';
function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { 'content-type': 'application/json' } });
}
function mount(path = '/app') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/app" element={<Home />} />
            <Route path="/app/sessions/:sessionId" element={<Conversation />} />
            <Route path="/app/admin/:section?" element={<AdminPage />} />
            <Route path="/app/usage" element={<UsagePage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}
function server(
  me: Me = user,
  extra?: (path: string, init: RequestInit) => Response | Promise<Response> | undefined,
) {
  const requests: Array<{ path: string; init: RequestInit }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const path = String(input);
      requests.push({ path, init });
      const overridden = extra?.(path, init);
      if (overridden) return overridden;
      if (path === '/api/v2/me') return response(me);
      if (path === '/api/v2/projects')
        return response({ items: [{ id: pid, name: '我的项目', revision: 0 }] });
      if (path === '/api/v2/sessions') return response({ items: [] });
      if (path === '/api/v2/agents')
        return response({
          items: [
            {
              id: aid,
              name: '文件分析助手',
              version: '1',
              engine: 'local-harness-v2',
              digest: 'a'.repeat(64),
            },
          ],
        });
      return response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404);
    }),
  );
  return requests;
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

describe('Workbench identity and tasks', () => {
  it('shows authorized Agent versions without fabricated activity counters', async () => {
    server();
    mount();
    expect(await screen.findByRole('heading', { name: '文件分析助手' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '你好，同事甲' })).toBeInTheDocument();
    expect(screen.queryByText('管理中心')).not.toBeInTheDocument();
    expect(screen.getByText('1 个可用')).toBeInTheDocument();
  });
  it('handles an empty authorized catalog without showing fake Agents', async () => {
    server(user, (path) => (path === '/api/v2/agents' ? response({ items: [] }) : undefined));
    mount();
    expect(await screen.findByText('还没有分配 Agent')).toBeInTheDocument();
    expect(screen.queryByText('文件分析助手')).not.toBeInTheDocument();
  });
  it('denies the management route in the UI for a non-admin identity', async () => {
    const requests = server();
    mount('/app/admin/members');
    expect(await screen.findByText('你没有访问该管理页面的权限。')).toBeInTheDocument();
    expect(requests.some((r) => r.path === '/api/v2/admin/members')).toBe(false);
  });
  it('creates a Session with explicit project and Agent version', async () => {
    const requests = server(user, (path, init) => {
      if (path === '/api/v2/sessions' && init.method === 'POST') return response({ id: sid }, 201);
      if (path === `/api/v2/sessions/${sid}`)
        return response({
          id: sid,
          title: '新的对话',
          project_id: pid,
          agent_version_id: aid,
          revision: 0,
          messages: [],
          runs: [],
        });
    });
    mount();
    await userEvent.click(await screen.findByRole('button', { name: /文件分析助手/ }));
    await userEvent.click(screen.getByRole('button', { name: /进入对话/ }));
    expect(await screen.findByRole('heading', { name: '新的对话' })).toBeInTheDocument();
    const request = requests.find((r) => r.path === '/api/v2/sessions' && r.init.method === 'POST')!;
    expect(JSON.parse(request.init.body as string)).toMatchObject({ project_id: pid, agent_version_id: aid });
  });
  it('submits once with a stable idempotency key and renders the server final result', async () => {
    let submitted = false;
    const requests = server(user, (path) => {
      if (path === `/api/v2/sessions/${sid}`)
        return response({
          id: sid,
          title: '数据任务',
          project_id: pid,
          agent_version_id: aid,
          revision: submitted ? 1 : 0,
          messages: submitted ? [{ seq: 1, role: 'user', run_id: rid, content: { text: '分析数据' } }] : [],
          runs: submitted ? [{ id: rid, state: 'succeeded', created_at: '2026-09-11T00:00:00Z' }] : [],
        });
      if (path === `/api/v2/sessions/${sid}/runs`) {
        submitted = true;
        return response({ run_id: rid }, 202);
      }
      if (path === `/api/v2/runs/${rid}`)
        return response({
          id: rid,
          state: 'succeeded',
          generation: 1,
          revision: 3,
          result: { answer: '这是已保存的分析结果。' },
          error_code: null,
          cleanup_state: 'clean',
          created_at: '2026-09-11T00:00:00Z',
          finished_at: '2026-09-11T00:00:01Z',
          next_event_seq: 1,
        });
      if (path.endsWith('/events'))
        return new Response(
          `id: ${rid}:1\nevent: run.completed\ndata: ${JSON.stringify({ schema_version: 1, run_id: rid, seq: 1, timestamp: '2026-09-11T00:00:01Z', payload: { state: 'succeeded' } })}\n\n`,
          { headers: { 'content-type': 'text/event-stream' } },
        );
    });
    mount(`/app/sessions/${sid}`);
    await userEvent.type(await screen.findByRole('textbox', { name: '任务内容' }), '分析数据');
    await userEvent.click(screen.getByRole('button', { name: /发送任务/ }));
    expect(await screen.findByText('这是已保存的分析结果。')).toBeInTheDocument();
    const posts = requests.filter((r) => r.path.endsWith('/runs') && r.init.method === 'POST');
    expect(posts).toHaveLength(1);
    expect(new Headers(posts[0].init.headers).get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    expect(JSON.parse(posts[0].init.body as string)).not.toHaveProperty('user_id');
  });
  it('retains a submission key when network confirmation is lost', async () => {
    const keys: string[] = [];
    server(user, (path, init) => {
      if (path === `/api/v2/sessions/${sid}`)
        return response({
          id: sid,
          title: '数据任务',
          project_id: pid,
          agent_version_id: aid,
          revision: 0,
          messages: [],
          runs: [],
        });
      if (path === `/api/v2/sessions/${sid}/runs`) {
        keys.push(new Headers(init.headers).get('Idempotency-Key')!);
        return Promise.reject(new TypeError('network lost'));
      }
    });
    mount(`/app/sessions/${sid}`);
    await userEvent.type(await screen.findByRole('textbox', { name: '任务内容' }), '确认不重跑');
    await userEvent.click(screen.getByRole('button', { name: /发送任务/ }));
    await screen.findByText(/连接暂时不可用/);
    await userEvent.click(screen.getByRole('button', { name: /重试同一提交/ }));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).toBe(keys[1]);
  });
  it('shows budget unknowns as pending, not free usage', async () => {
    server(user, (path) =>
      path === '/api/v2/usage'
        ? response({
            configured: true,
            currency: 'USD',
            hard_limit: '10',
            reserved: '1.02',
            consumed: '0.25',
            unknown_calls: 2,
          })
        : undefined,
    );
    mount('/app/usage');
    expect(await screen.findByText('1.02')).toBeInTheDocument();
    expect(screen.getByText('8.73')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders exact ledger amounts without grouping, rounding or float drift', async () => {
    // Number(x).toLocaleString('zh-CN', …) would print 1,000,000.00 for the cap and
    // derive headroom in binary floating point. Both alter a financial fact for display.
    server(user, (path) =>
      path === '/api/v2/usage'
        ? response({
            configured: true,
            currency: 'USD',
            hard_limit: '1000000.000000',
            reserved: '0.000001',
            consumed: '1.500000',
            unknown_calls: 0,
          })
        : undefined,
    );
    mount('/app/usage');
    expect(await screen.findByText('1000000.000000')).toBeInTheDocument();
    // Trailing zeros are a statement about recorded precision, so 1.500000 stays as sent.
    expect(screen.getByText('1.500000')).toBeInTheDocument();
    expect(screen.getByText('0.000001')).toBeInTheDocument();
    expect(screen.getByText('999998.499999')).toBeInTheDocument();
    expect(screen.queryByText(/1,000,000/)).not.toBeInTheDocument();
  });
});

describe('Explicit stdio attachment permission', () => {
  it.each([false, true])(
    'defaults closed, resets changed files and freezes consent on retry (%s)',
    async (consent) => {
      const serverId = '71000000-0000-4000-8000-000000000001';
      const artifactId = '72000000-0000-4000-8000-000000000001';
      const file = new File(['item,value\nalpha,73\n'], 'selected.csv', { type: 'text/csv' });
      const requests = server(
        { ...user, capabilities: { ...user.capabilities, mcp: true } },
        (path, init) => {
          if (path === `/api/v2/sessions/${sid}`)
            return response({
              id: sid,
              title: '附件权限',
              project_id: pid,
              agent_version_id: aid,
              revision: 0,
              messages: [],
              runs: [],
              mcp_server_ids: [serverId],
            });
          if (path === '/api/v2/connections')
            return response({
              items: [
                {
                  id: '73000000-0000-4000-8000-000000000001',
                  server_id: serverId,
                  name: '我的连接',
                  scope: 'personal',
                  state: 'active',
                  resource_status: 'active',
                },
              ],
            });
          if (path === `/api/v2/projects/${pid}/uploads` && init.method === 'POST')
            return response({ content_url: '/api/v2/uploads/synthetic/content' }, 201);
          if (path === '/api/v2/uploads/synthetic/content')
            return response({
              id: artifactId,
              project_id: pid,
              run_id: null,
              path: file.name,
              bytes: file.size,
              sha256: 'a'.repeat(64),
              media_type: 'text/csv',
              state: 'published',
              scan_state: 'opaque_attachment',
            });
          if (path === `/api/v2/sessions/${sid}/runs`)
            return Promise.reject(new TypeError('synthetic lost response'));
        },
      );
      const view = mount(`/app/sessions/${sid}`);
      await screen.findByRole('textbox', { name: '任务内容' });
      const input = view.container.querySelector<HTMLInputElement>('input[type="file"]')!;
      await userEvent.upload(input, file);
      let control = await screen.findByRole('checkbox', { name: '允许隔离 MCP 读取本次所选附件' });
      expect(control).not.toBeChecked();
      expect(screen.getByText(/不包含项目其他文件或宿主目录/)).toBeInTheDocument();
      if (consent) {
        await userEvent.click(control);
        await userEvent.click(screen.getByRole('button', { name: /移除/ }));
        expect(
          screen.queryByRole('checkbox', { name: '允许隔离 MCP 读取本次所选附件' }),
        ).not.toBeInTheDocument();
        await userEvent.upload(input, file);
        control = await screen.findByRole('checkbox', { name: '允许隔离 MCP 读取本次所选附件' });
        expect(control).not.toBeChecked();
        await userEvent.click(control);
      }
      await userEvent.type(screen.getByRole('textbox', { name: '任务内容' }), '读取这份附件');
      await userEvent.click(screen.getByRole('button', { name: /发送任务/ }));
      await screen.findByRole('button', { name: /重试同一提交/ });
      expect(control).toBeDisabled();
      await userEvent.click(screen.getByRole('button', { name: /重试同一提交/ }));
      await waitFor(() =>
        expect(requests.filter((request) => request.path.endsWith('/runs'))).toHaveLength(2),
      );
      const posts = requests.filter((request) => request.path.endsWith('/runs'));
      expect(JSON.parse(posts[0].init.body as string)).toMatchObject({
        allow_stdio_attachments: consent,
        input_artifact_ids: [artifactId],
      });
      expect(posts[1].init.body).toBe(posts[0].init.body);
      expect(new Headers(posts[1].init.headers).get('Idempotency-Key')).toBe(
        new Headers(posts[0].init.headers).get('Idempotency-Key'),
      );
    },
  );
});

describe('Content and interaction safety', () => {
  it('does not execute raw HTML or javascript links in model markdown', () => {
    const { container } = render(
      <Markdown text={'hello <script>window.bad=true</script>\n\n[bad](javascript:alert(1))\n\n**safe**'} />,
    );
    expect(container.querySelector('script')).toBeNull();
    expect(container.querySelector('a')?.getAttribute('href')).not.toMatch(/^javascript:/i);
    expect(screen.getByText('safe').tagName).toBe('STRONG');
  });
  it('external markdown links use noopener and noreferrer', () => {
    render(<Markdown text={'[source](https://example.test)'} />);
    const link = screen.getByRole('link', { name: 'source' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });
  it('dialog has an accessible label and cancel does not imply approval', () => {
    const close = vi.fn();
    render(
      <Modal title="具体动作确认" onClose={close}>
        <button>只是一项操作</button>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog', { name: '具体动作确认' });
    fireEvent(dialog, new Event('cancel', { cancelable: true, bubbles: true }));
    expect(close).toHaveBeenCalledOnce();
  });
});
