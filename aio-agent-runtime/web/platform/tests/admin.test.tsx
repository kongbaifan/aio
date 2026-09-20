import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../src/api/client';
import type { Me } from '../src/api/types';
import { AuthProvider } from '../src/auth';
import { Layout } from '../src/components/Layout';
import { AdminPage } from '../src/features/Admin';

const uid = '10000000-0000-4000-8000-000000000001',
  other = '10000000-0000-4000-8000-000000000002',
  org = '20000000-0000-4000-8000-000000000001',
  modelId = '30000000-0000-4000-8000-000000000001',
  agentId = '40000000-0000-4000-8000-000000000001',
  deptId = '50000000-0000-4000-8000-000000000001';
const admin: Me = {
  user_id: uid,
  org_id: org,
  display_name: '管理员',
  organization_name: '验证组织',
  role: 'org_admin',
  membership_revision: 0,
  csrf_token: 'csrf-admin',
  departments: [],
  permissions: { organization_admin: true, operations: true, audit: true },
  capabilities: {
    file_upload: true,
    python_compute: true,
    mcp: false,
    knowledge: false,
    skill_publishing: false,
    team: false,
  },
};
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } });
}
function mount(section: string) {
  return render(
    <MemoryRouter initialEntries={[`/app/admin/${section}`]}>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/app/admin/:section?" element={<AdminPage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}
function setup(extra?: (path: string, init: RequestInit) => Response | undefined, identity = admin) {
  const requests: Array<{ path: string; init: RequestInit }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const path = String(input);
      requests.push({ path, init });
      const result = extra?.(path, init);
      if (result) return result;
      if (path === '/api/v2/me') return response(identity);
      if (path === '/api/v2/projects' || path === '/api/v2/sessions') return response({ items: [] });
      if (path === '/api/v2/admin/options')
        return response({
          model_allowed_origins: ['https://models.example.test'],
          model_secret_names: ['APPROVED_KEY'],
          sandbox_profiles: [
            { id: 'standard', image_digest: 'sha256:' + '1'.repeat(64), max_timeout_seconds: 120 },
          ],
          supported_drivers: ['sandbox.python'],
          supported_engines: ['local-harness-v2'],
        });
      if (path === '/api/v2/admin/models') return response({ items: [] });
      if (path === '/api/v2/admin/tools') return response({ items: [] });
      if (path === '/api/v2/skills') return response({ items: [] });
      if (path === '/api/v2/directory')
        return response({
          members: [{ user_id: other, display_name: '业务同事' }],
          departments: [{ id: deptId, name: '销售' }],
        });
      return response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404);
    }),
  );
  return requests;
}
beforeEach(() => {
  api.invalidate();
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
});
afterEach(() => {
  api.invalidate();
  vi.unstubAllGlobals();
});

it('model registration submits approved references, never a raw API key', async () => {
  const requests = setup((path, init) =>
    path === '/api/v2/admin/models' && init.method === 'POST'
      ? response({ id: modelId, digest: 'd'.repeat(64) }, 201)
      : undefined,
  );
  mount('models');
  await userEvent.click(await screen.findByRole('button', { name: /登记模型/ }));
  await userEvent.type(screen.getByLabelText('显示名称'), '内部模型');
  await userEvent.type(screen.getByLabelText('模型 ID'), 'approved-model');
  expect(screen.getByLabelText('已批准密钥引用')).toHaveValue('APPROVED_KEY');
  expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '创建模型版本' }));
  await waitFor(() =>
    expect(requests.some((r) => r.path === '/api/v2/admin/models' && r.init.method === 'POST')).toBe(true),
  );
  const payload = JSON.parse(
    requests.find((r) => r.path === '/api/v2/admin/models' && r.init.method === 'POST')!.init.body as string,
  );
  expect(payload.secret_env).toBe('APPROVED_KEY');
  expect(payload).not.toHaveProperty('api_key');
  expect(payload.endpoint).toBe('https://models.example.test/v1/chat/completions');
});
it('no operator allowlist means model registration is disabled', async () => {
  setup((path) =>
    path === '/api/v2/admin/options'
      ? response({
          model_allowed_origins: [],
          model_secret_names: [],
          sandbox_profiles: [],
          supported_drivers: [],
          supported_engines: [],
        })
      : undefined,
  );
  mount('models');
  expect(await screen.findByRole('button', { name: /登记模型/ })).toBeDisabled();
  expect(await screen.findByText(/尚未设置模型端点/)).toBeInTheDocument();
});
it('tool configuration cannot ask for arbitrary shell or privileged Docker flags', async () => {
  setup();
  mount('tools');
  await userEvent.click(await screen.findByRole('button', { name: /配置计算工具/ }));
  expect(screen.getByLabelText('部署批准的 Profile')).toHaveValue('standard');
  expect(screen.queryByLabelText('命令')).not.toBeInTheDocument();
  expect(screen.getByText(/镜像、无网络策略和系统权限由部署 Profile 决定/)).toBeInTheDocument();
});
it('department membership changes use explicit user and department identifiers', async () => {
  const requests = setup((path, init) => {
    if (path === '/api/v2/admin/departments')
      return response({ items: [{ id: deptId, name: '销售', active: true, members: [] }] });
    if (path === '/api/v2/admin/members')
      return response({
        items: [
          {
            user_id: other,
            display_name: '业务同事',
            subject: 'subject-2',
            active: true,
            role: 'member',
            revision: 0,
          },
        ],
      });
    if (path === `/api/v2/admin/departments/${deptId}/members` && init.method === 'PUT')
      return response({ department_id: deptId, user_id: other, role: 'member' });
  });
  mount('departments');
  await userEvent.click(await screen.findByRole('button', { name: /添加成员/ }));
  await userEvent.selectOptions(screen.getByLabelText('组织成员'), other);
  await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '添加成员' }));
  await waitFor(() => expect(requests.some((r) => r.init.method === 'PUT')).toBe(true));
  expect(JSON.parse(requests.find((r) => r.init.method === 'PUT')!.init.body as string)).toEqual({
    user_id: other,
    role: 'member',
  });
});
it('Agent sharing makes dependency grants an explicit user choice', async () => {
  const requests = setup((path, init) => {
    if (path === '/api/v2/admin/agents')
      return response({
        items: [
          {
            id: agentId,
            name: '销售助手',
            version: '1',
            engine: 'local-harness-v2',
            digest: 'd',
            revision: 0,
            status: 'active',
            manifest: { model: { id: modelId, digest: 'd' }, tools: [], max_rounds: 4, run_budget: '0.1' },
          },
        ],
      });
    if (path === `/api/v2/resources/${agentId}/grants` && init.method === 'GET')
      return response({
        resource_id: agentId,
        kind: 'agent',
        revision: 0,
        available_actions: ['agent.read', 'agent.use'],
        items: [],
      });
    if (path === `/api/v2/resources/${agentId}/grants` && init.method === 'PUT')
      return response({ resource_id: agentId, granted_resources: 2, revision: 1 });
  });
  mount('agents');
  await userEvent.click(await screen.findByRole('button', { name: '授权' }));
  await userEvent.selectOptions(await screen.findByLabelText('接收对象'), other);
  await userEvent.click(screen.getByLabelText('使用 Agent'));
  expect(screen.getByLabelText('同时授权此版本的模型、工具与知识能力依赖')).toBeChecked();
  await userEvent.click(screen.getByRole('button', { name: '保存授权' }));
  await waitFor(() => expect(requests.some((r) => r.init.method === 'PUT')).toBe(true));
  expect(JSON.parse(requests.find((r) => r.init.method === 'PUT')!.init.body as string)).toMatchObject({
    subject_type: 'user',
    subject_id: other,
    actions: ['agent.use'],
    include_dependencies: true,
  });
});
it('operator role exposes task metadata, not private messages or member administration', async () => {
  setup(
    (path) =>
      path === '/api/v2/admin/runs'
        ? response({
            items: [
              {
                id: agentId,
                actor_id: other,
                project_id: deptId,
                state: 'running',
                generation: 1,
                error_code: null,
                cleanup_state: 'pending',
                created_at: '2026-09-11T00:00:00Z',
                job_state: 'leased',
                result: 'private sentinel not for UI',
              },
            ],
          })
        : undefined,
    {
      ...admin,
      role: 'operator',
      permissions: { organization_admin: false, operations: true, audit: false },
    },
  );
  mount('operations');
  expect(await screen.findByText('任务监控', { selector: 'h2' })).toBeInTheDocument();
  expect(screen.queryByText('private sentinel not for UI')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: '成员与身份' })).not.toBeInTheDocument();
});
it('member budget amounts are rendered exactly as the server recorded them', async () => {
  setup((path) => {
    if (path === '/api/v2/admin/shared-budgets') return response({ items: [] });
    if (path === '/api/v2/admin/budgets')
      return response({
        items: [
          {
            id: '60000000-0000-4000-8000-000000000001',
            owner_id: other,
            display_name: '业务同事',
            // A cap just under ten, a charge far below one cent, and a migrated
            // amount whose trailing zeros state the precision that was recorded.
            hard_limit: '9.999999',
            consumed: '0.0000001',
            reserved: '1000000.000000',
            currency: 'USD',
          },
        ],
      });
    if (path === '/api/v2/admin/members') return response({ items: [] });
  });
  mount('budgets');
  const row = (await screen.findByText('业务同事')).closest('tr')!;
  const cells = Array.from(row.querySelectorAll('td')).map((cell) => cell.textContent?.trim());
  // Rounding the cap up to 10.00 would overstate the headroom an admin may hand
  // out, and flooring the charge to 0.000000 would deny that a real debit exists.
  expect(cells[1]).toBe('USD 9.999999');
  expect(cells[2]).toBe('0.0000001');
  expect(cells[3]).toBe('1000000.000000');
});
