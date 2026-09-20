import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../src/api/client';
import type { Me, SkillDetail } from '../src/api/types';
import { AuthProvider } from '../src/auth';
import { Layout } from '../src/components/Layout';
import { AdminPage } from '../src/features/Admin';

const owner = '10000000-0000-4000-8000-000000000001';
const reviewer = '10000000-0000-4000-8000-000000000002';
const id = '20000000-0000-4000-8000-000000000001';
const model = '30000000-0000-4000-8000-000000000001';
const identity: Me = {
  user_id: owner,
  org_id: '40000000-0000-4000-8000-000000000001',
  display_name: '发布人',
  organization_name: '测试组织',
  role: 'org_admin',
  membership_revision: 0,
  csrf_token: 'synthetic-csrf',
  departments: [],
  permissions: { organization_admin: true, operations: true, audit: true },
  capabilities: {
    file_upload: true,
    python_compute: true,
    skill_publishing: true,
    knowledge: false,
    mcp: false,
    team: false,
  },
};
const initial: SkillDetail = {
  id,
  name: 'sales-helper',
  version: '1.0.0',
  digest: 'a'.repeat(64),
  state: 'draft',
  revision: 0,
  resource_status: 'active',
  resource_revision: 0,
  owner_id: owner,
  reviewer_id: reviewer,
  profile_id: 'test',
  image_digest: 'sha256:' + '1'.repeat(64),
  created_at: '2026-09-11T00:00:00Z',
  published_at: null,
  published_tools: [],
  package: {
    schema_version: 1,
    name: 'sales-helper',
    version: '1.0.0',
    description: '销售分析',
    source: '内部编写',
    license: '内部使用',
    files: [{ path: 'SKILL.md', content: '# 检查获权资料' }],
    instruction_path: 'SKILL.md',
    reference_paths: [],
    entrypoints: [],
  },
  file_manifest: [{ path: 'SKILL.md', bytes: 24, sha256: 'b'.repeat(64) }],
  review_note: null,
  validations: [],
};
const validated: SkillDetail = {
  ...initial,
  state: 'validated',
  revision: 2,
  validations: [
    {
      id: 'job-1',
      state: 'passed',
      cleanup_state: 'confirmed',
      error_code: null,
      results: [{ kind: 'scan', passed: true }],
      created_at: '2026-09-11T00:00:00Z',
      finished_at: '2026-09-11T00:01:00Z',
    },
  ],
};
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } });
}
function setup(start: SkillDetail | null = null, me = identity, dependencyRuntime = false) {
  let row = start;
  const requests: Array<{ path: string; method: string; body?: unknown }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const path = String(input),
        method = init.method ?? 'GET';
      const body = init.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ path, method, body });
      if (path === '/api/v2/me') return response(me);
      if (path === '/api/v2/projects' || path === '/api/v2/sessions') return response({ items: [] });
      if (path === '/api/v2/admin/options')
        return response({
          model_allowed_origins: [],
          model_secret_names: [],
          sandbox_profiles: [
            { id: 'test', image_digest: 'sha256:' + '1'.repeat(64), max_timeout_seconds: 120 },
            ...(dependencyRuntime
              ? [
                  {
                    id: 'analytics',
                    image_digest: 'sha256:' + '2'.repeat(64),
                    max_timeout_seconds: 60,
                    runtime: {
                      manifest_digest: 'd'.repeat(64),
                      key_id: 'operator',
                      purpose: 'test',
                      manifest: {
                        name: 'analytics',
                        python: '3.12',
                        packages: [
                          { name: 'numpy', version: '2.5.3' },
                          { name: 'pandas', version: '3.0.5' },
                        ],
                      },
                    },
                  },
                ]
              : []),
          ],
          supported_drivers: ['sandbox.python'],
          supported_engines: ['local-harness-v2'],
        });
      if (path === '/api/v2/admin/members')
        return response({
          items: [owner, reviewer].map((user_id, index) => ({
            user_id,
            display_name: index ? '审核人' : '发布人',
            subject: user_id,
            role: 'org_admin',
            active: true,
            revision: 0,
          })),
        });
      if (path === '/api/v2/admin/skills' && method === 'POST') {
        row = { ...initial, package: body.package, name: body.package.name };
        return response(row, 201);
      }
      if (path === '/api/v2/admin/skills') return response({ items: row ? [row] : [] });
      if (path === `/api/v2/admin/skills/${id}`) return response(row ?? initial);
      if (path === `/api/v2/admin/skills/${id}/validate`) {
        row = { ...(row ?? initial), state: 'validating', revision: 1 };
        return response({ job_id: 'job-1', state: 'queued', revision: 1 }, 202);
      }
      if (path === `/api/v2/admin/skills/${id}/review`) {
        row = {
          ...(row ?? validated),
          state: body.decision === 'approve' ? 'published' : 'rejected',
          revision: 3,
        };
        return response(row);
      }
      if (path === '/api/v2/skills') return response({ items: row ? [row] : [] });
      if (path === '/api/v2/admin/models')
        return response({
          items: [{ id: model, provider: 'test', model: 'test', status: 'active', config: {} }],
        });
      if (path === '/api/v2/admin/tools') return response({ items: [] });
      if (path === '/api/v2/admin/agents' && method === 'POST') return response({ id: model }, 201);
      if (path === '/api/v2/admin/agents') return response({ items: [] });
      return response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404);
    }),
  );
  return requests;
}
function mount(section = 'skills') {
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

it('creates an inert instruction draft and explicitly assigns a distinct reviewer', async () => {
  const requests = setup();
  mount();
  const create = await screen.findByRole('button', { name: '创建 Skill' });
  await waitFor(() => expect(create).toBeEnabled());
  await userEvent.click(create);
  await userEvent.type(await screen.findByLabelText(/Skill 标识/), 'sales-helper');
  await userEvent.type(screen.getByLabelText('用途说明'), '销售分析');
  await userEvent.type(screen.getByLabelText('内容来源'), '销售部内部编写');
  await userEvent.type(screen.getByLabelText(/SKILL.md 任务说明/), '先核对获权数据，再总结差异。');
  await userEvent.click(screen.getByRole('button', { name: '保存私有草稿' }));
  await screen.findByText('提交隔离验证与人工审核');
  const created = requests.find((r) => r.path === '/api/v2/admin/skills' && r.method === 'POST');
  expect(created?.body).toMatchObject({
    sandbox_profile: 'test',
    package: {
      name: 'sales-helper',
      version: '1.0.0',
      entrypoints: [],
      files: [{ path: 'SKILL.md', content: '先核对获权数据，再总结差异。' }],
    },
  });
  expect(JSON.stringify(created?.body)).not.toMatch(/host_command|docker_flags|secret_env/);
  expect(screen.queryByRole('button', { name: '批准固定版本' })).toBeNull();
  await userEvent.selectOptions(screen.getByLabelText(/指定另一位组织管理员/), reviewer);
  await userEvent.click(screen.getByRole('button', { name: '验证固定包并提交审核' }));
  await waitFor(() =>
    expect(requests.find((r) => r.path.endsWith('/validate'))?.body).toEqual({
      reviewer_id: reviewer,
      expected_revision: 0,
    }),
  );
});

it('requires an explicit reviewer acknowledgement and note before publishing the exact revision', async () => {
  const requests = setup(validated, { ...identity, user_id: reviewer, display_name: '审核人' });
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '查看包与验证' }));
  const approve = await screen.findByRole('button', { name: '批准固定版本' });
  expect(approve).toBeDisabled();
  expect(requests.some((r) => r.path.endsWith('/review'))).toBe(false);
  await userEvent.type(screen.getByLabelText('审核意见'), '已核对固定版本用途与测试');
  expect(approve).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: /我已核对这个版本/ }));
  await userEvent.click(approve);
  await waitFor(() =>
    expect(requests.find((r) => r.path.endsWith('/review'))?.body).toEqual({
      expected_revision: 2,
      decision: 'approve',
      note: '已核对固定版本用途与测试',
    }),
  );
});

it('never presents unconfirmed cleanup as publishable', async () => {
  setup(
    { ...validated, validations: [{ ...validated.validations[0], cleanup_state: 'pending' }] },
    { ...identity, user_id: reviewer },
  );
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '查看包与验证' }));
  await screen.findByText(/未确认，禁止发布/);
  expect(screen.queryByRole('button', { name: '批准固定版本' })).toBeNull();
});

it('renders package source as inert text rather than HTML', async () => {
  setup({
    ...initial,
    package: {
      ...initial.package,
      files: [
        { path: 'SKILL.md', content: '<script>window.skillXss=1</script><img src=x onerror=alert(1)>' },
      ],
    },
  });
  const page = mount();
  await userEvent.click(await screen.findByRole('button', { name: '查看包与验证' }));
  await screen.findByText(/window.skillXss/);
  expect(page.container.querySelector('.skill-source script, .skill-source img')).toBeNull();
});

it('denies ordinary members without fetching private Skill drafts', async () => {
  const requests = setup(null, {
    ...identity,
    role: 'member',
    permissions: { organization_admin: false, audit: false, operations: false },
  });
  mount();
  await screen.findByText('你没有访问该管理页面的权限。');
  expect(requests.some((r) => r.path.startsWith('/api/v2/admin/skills'))).toBe(false);
});

it('binds selected immutable Skill version IDs when creating an Agent', async () => {
  const requests = setup({ ...initial, state: 'published' });
  mount('agents');
  await userEvent.click(await screen.findByRole('button', { name: '新建 Agent' }));
  await userEvent.type(screen.getByLabelText('Agent 名称'), '销售助手');
  await userEvent.click(await screen.findByRole('checkbox', { name: /sales-helper · v1.0.0/ }));
  await userEvent.click(screen.getByRole('button', { name: '发布这个版本' }));
  await waitFor(() =>
    expect(
      requests.find((r) => r.path === '/api/v2/admin/agents' && r.method === 'POST')?.body,
    ).toMatchObject({ skill_ids: [id], model_id: model }),
  );
});

it('shows signed dependencies and preserves numeric v2 without an installation form', async () => {
  const requests = setup(null, identity, true);
  mount();
  const create = await screen.findByRole('button', { name: '创建 Skill' });
  await waitFor(() => expect(create).toBeEnabled());
  await userEvent.click(create);
  await userEvent.selectOptions(screen.getByLabelText(/固定验证与执行环境/), 'analytics');
  expect(await screen.findByText(/numpy==2.5.3/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('radio', { name: /JSON/ }));
  const editor = screen.getByRole('textbox', { name: '能力包内容' });
  const value = {
    ...initial.package,
    schema_version: 2,
    runtime_manifest_digest: 'd'.repeat(64),
    dependencies: [{ name: 'numpy', version: '2.5.3' }],
  };
  fireEvent.change(editor, { target: { value: JSON.stringify(value) } });
  await userEvent.click(screen.getByRole('button', { name: '保存私有草稿' }));
  await waitFor(() =>
    expect(
      requests.find((request) => request.path === '/api/v2/admin/skills' && request.method === 'POST')?.body,
    ).toMatchObject({
      sandbox_profile: 'analytics',
      package: { schema_version: 2, runtime_manifest_digest: 'd'.repeat(64) },
    }),
  );
  expect(screen.queryByRole('textbox', { name: /安装命令|Docker 参数|pip 命令/ })).toBeNull();
});
