import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { api } from '../src/api/client';
import type { Me, MCPConnection, MCPServerVersion } from '../src/api/types';
import { AuthProvider } from '../src/auth';
import { Layout } from '../src/components/Layout';
import { ConnectionsPage } from '../src/features/Connections';
import { AdminPage } from '../src/features/Admin';

const uid = '10000000-0000-4000-8000-000000000001';
const sid = '20000000-0000-4000-8000-000000000001';
const cid = '30000000-0000-4000-8000-000000000001';
const bid = '40000000-0000-4000-8000-000000000001';
const did = '50000000-0000-4000-8000-000000000001';
const token = 'synthetic-private-employee-mcp-token';
const me: Me = {
  user_id: uid,
  org_id: '60000000-0000-4000-8000-000000000001',
  display_name: '测试员工',
  organization_name: '测试组织',
  role: 'member',
  membership_revision: 0,
  csrf_token: 'synthetic-csrf',
  departments: [],
  permissions: { organization_admin: false, audit: false, operations: false },
  capabilities: {
    mcp: true,
    knowledge: false,
    team: false,
    file_upload: true,
    python_compute: true,
    skill_publishing: true,
  },
};
const server: MCPServerVersion = {
  id: sid,
  name: '公司资料 MCP',
  version: '1.0.0',
  endpoint_id: 'company',
  endpoint_digest: 'd'.repeat(64),
  endpoint_url: 'https://mcp.example.test/mcp',
  authentication: 'bearer',
  endpoint_available: true,
  state: 'published',
  revision: 1,
  digest: 'a'.repeat(64),
  published_tools: [],
  created_at: '2026-09-12T00:00:00Z',
};
const initial: MCPConnection = {
  id: cid,
  server_id: sid,
  name: '我的只读账号',
  owner_id: uid,
  scope: 'personal',
  department_id: null,
  state: 'pending',
  credential_revision: 0,
  resource_status: 'active',
  resource_revision: 0,
  created_at: '2026-09-12T00:00:00Z',
};
const discovery = {
  id: did,
  state: 'ready',
  error_code: null,
  result: {
    protocol_version: '2025-06-18',
    endpoint_digest: server.endpoint_digest,
    remote_session_closed: true,
    unapproved_tool_count: 1,
    tools: [
      {
        name: 'find_docs',
        description: '只读检索公司资料',
        input_schema: { type: 'object' },
        output_schema: null,
        annotations: { readOnlyHint: false },
        digest: 'f'.repeat(64),
      },
    ],
  },
};
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}
function setup({
  identity = me,
  rows = [initial],
  definition = server,
  lostPut = false,
  failedProbe = false,
  oauthUrl = 'https://id.example.test/authorize?state=synthetic-authorization-state',
}: {
  identity?: Me;
  rows?: MCPConnection[];
  definition?: MCPServerVersion;
  lostPut?: boolean;
  failedProbe?: boolean;
  oauthUrl?: string;
} = {}) {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  let connections = rows,
    lost = lostPut;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const path = String(input),
        method = init.method ?? 'GET';
      const body = init.body ? JSON.parse(String(init.body)) : null;
      calls.push({ path, method, body });
      if (path === '/api/v2/me') return response(identity);
      if (path === '/api/v2/projects' || path === '/api/v2/sessions' || path === '/api/v2/skills')
        return response({ items: [] });
      if (path === '/api/v2/mcp/servers' || (path === '/api/v2/admin/mcp/servers' && method === 'GET'))
        return response({ items: [definition] });
      if (path === '/api/v2/admin/mcp/servers' && method === 'POST') return response(definition, 201);
      if (path === '/api/v2/admin/options')
        return response({
          model_allowed_origins: [],
          model_secret_names: [],
          sandbox_profiles: [],
          supported_drivers: [],
          supported_engines: ['local-harness-v2'],
          connector_endpoints: [
            {
              id: 'company',
              url: server.endpoint_url,
              digest: server.endpoint_digest,
              authentication: 'bearer',
              read_tools: ['find_docs'],
              timeout_seconds: 30,
            },
          ],
        });
      if (path === '/api/v2/connections' && method === 'POST') {
        connections = [{ ...initial, ...body }];
        return response(connections[0], 201);
      }
      if (path === '/api/v2/connections') return response({ items: connections });
      if (path === `/api/v2/connections/${cid}/oauth`) {
        if (lost) {
          lost = false;
          throw new TypeError('Synthetic authorization response lost');
        }
        return response({ flow_id: bid, authorization_url: oauthUrl }, 201);
      }
      if (path === `/api/v2/connections/${cid}/credentials`)
        return response({ binding_id: bid, state: 'pending' }, 201);
      if (path === `/api/v2/connections/${cid}/credentials/${bid}`) {
        if (lost) {
          lost = false;
          throw new TypeError('Synthetic lost acknowledgement');
        }
        connections = [{ ...initial, credential_revision: 1, resource_revision: 2 }];
        return response(connections[0]);
      }
      if (path === `/api/v2/connections/${cid}/discover`) {
        if (failedProbe) return response({ error: { code: 'MCP_AUTH_REQUIRED' } }, 403);
        connections = [{ ...initial, state: 'active', credential_revision: 1, resource_revision: 2 }];
        return response(discovery);
      }
      if (path === `/api/v2/admin/mcp/servers/${sid}/publish`)
        return response({ ...definition, state: 'published' });
      if (path === `/api/v2/connections/${cid}` && method === 'DELETE') {
        connections = [{ ...initial, state: 'revoked' }];
        return response({ state: 'revoked', credential_cleanup: 'pending' });
      }
      if (path === '/api/v2/directory') return response({ members: [], departments: [] });
      return response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404);
    }),
  );
  return calls;
}
function mount(admin = false) {
  return render(
    <MemoryRouter initialEntries={[admin ? '/app/admin/mcp' : '/app/connections']}>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/app/connections" element={<ConnectionsPage />} />
            <Route path="/app/admin/:section" element={<AdminPage />} />
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

it('ordinary users create only personal connections to a fixed approved destination', async () => {
  const calls = setup({ rows: [] });
  mount();
  const add = await screen.findByRole('button', { name: '添加连接' });
  await waitFor(() => expect(add).toBeEnabled());
  await userEvent.click(add);
  await userEvent.type(screen.getByLabelText('连接名称'), '我的资料账号');
  expect(screen.queryByLabelText('身份使用范围')).toBeNull();
  expect(screen.queryByLabelText('端点 URL')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: '创建连接' }));
  await screen.findByRole('dialog', { name: '配置 MCP 凭据' });
  expect(calls.find((c) => c.path === '/api/v2/connections' && c.method === 'POST')?.body).toMatchObject({
    name: '我的资料账号',
    server_id: sid,
    scope: 'personal',
    department_id: null,
  });
});

it('prepares a stable credential ticket, keeps the token out of the page, and tests before showing success', async () => {
  const calls = setup();
  const page = mount();
  await userEvent.click(await screen.findByRole('button', { name: '配置凭据' }));
  const secret = screen.getByLabelText(/个人只读 MCP 令牌/);
  expect(secret).toHaveAttribute('type', 'password');
  await userEvent.type(secret, token);
  await userEvent.click(screen.getByRole('button', { name: '保存凭据并检测连接' }));
  await screen.findByText('MCP 初始化与工具发现已通过');
  expect(calls.find((c) => c.path.endsWith(`/credentials/${bid}`))?.body).toEqual({ secret: token });
  expect(page.container.textContent).not.toContain(token);
  expect(JSON.stringify(window.localStorage)).not.toContain(token);
  expect(calls.findIndex((c) => c.path.endsWith('/discover'))).toBeGreaterThan(
    calls.findIndex((c) => c.path.endsWith(`/credentials/${bid}`)),
  );
});

it('a lost credential acknowledgement retries the same prepared binding rather than allocating another identity', async () => {
  const calls = setup({ lostPut: true });
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '配置凭据' }));
  await userEvent.type(screen.getByLabelText(/个人只读 MCP 令牌/), token);
  await userEvent.click(screen.getByRole('button', { name: '保存凭据并检测连接' }));
  await screen.findByText(/连接暂时不可用/);
  expect(screen.getByLabelText(/个人只读 MCP 令牌/)).toHaveValue('');
  await userEvent.type(screen.getByLabelText(/个人只读 MCP 令牌/), token);
  await userEvent.click(screen.getByRole('button', { name: '保存凭据并检测连接' }));
  await screen.findByText('MCP 初始化与工具发现已通过');
  expect(calls.filter((c) => c.path === `/api/v2/connections/${cid}/credentials`)).toHaveLength(1);
  expect(calls.filter((c) => c.path.endsWith(`/credentials/${bid}`))).toHaveLength(2);
});

it('does not mistake encrypted storage for successful upstream authentication', async () => {
  setup({ failedProbe: true });
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '配置凭据' }));
  await userEvent.type(screen.getByLabelText(/个人只读 MCP 令牌/), token);
  await userEvent.click(screen.getByRole('button', { name: '保存凭据并检测连接' }));
  await screen.findByText(/源系统未接受这个凭据/);
  expect(screen.queryByText('MCP 初始化与工具发现已通过')).toBeNull();
  expect(screen.getByLabelText(/个人只读 MCP 令牌/)).toHaveValue('');
});

it('publishes only explicitly selected tools with a read-only-account acknowledgement', async () => {
  const admin: Me = {
    ...me,
    role: 'org_admin',
    permissions: { organization_admin: true, operations: true, audit: true },
  };
  const calls = setup({
    identity: admin,
    definition: { ...server, state: 'draft', revision: 0 },
    rows: [{ ...initial, state: 'active', credential_revision: 1 }],
  });
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '检测并发现工具' }));
  const publish = await screen.findByRole('button', { name: '发布选中的固定工具' });
  expect(publish).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: '将这个工具加入固定发布版本' }));
  expect(publish).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: /我已确认源系统使用只读权限/ }));
  await userEvent.click(publish);
  await waitFor(() =>
    expect(calls.find((c) => c.path.endsWith('/publish'))?.body).toEqual({
      expected_revision: 0,
      discovery_id: did,
      tools: [{ remote_name: 'find_docs', alias: 'mcp_find_docs' }],
      acknowledge_readonly_credentials: true,
    }),
  );
});

it('requires an explicit confirmation before retiring a connection', async () => {
  const calls = setup();
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '撤销连接' }));
  const dialog = await screen.findByRole('dialog', { name: '撤销这个连接？' });
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  expect(within(dialog).getByText(/不等于已在源系统撤销令牌/)).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole('button', { name: '确认撤销连接' }));
  await waitFor(() =>
    expect(calls.some((c) => c.method === 'DELETE' && c.path === `/api/v2/connections/${cid}`)).toBe(true),
  );
});

const oauthDefinition: MCPServerVersion = {
  ...server,
  authentication: 'oauth2',
  oauth: {
    issuer: 'https://id.example.test',
    authorization_endpoint: 'https://id.example.test/authorize',
    redirect_uri: 'https://platform.example.test/auth/mcp/callback/company',
    client_id: 'public-client-id',
    scopes: ['mcp.read'],
    resource: server.endpoint_url!,
    require_issuer_response: true,
    config_digest: 'a'.repeat(64),
  },
};

it('uses a session-bound OAuth link instead of asking the user for raw tokens', async () => {
  const calls = setup({ definition: oauthDefinition });
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '使用 OAuth 授权' }));
  expect(screen.queryByLabelText('个人只读 MCP 令牌')).not.toBeInTheDocument();
  expect(screen.getByText(/mcp.read/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '生成安全授权链接' }));
  const link = await screen.findByRole('link', { name: '前往授权服务器' });
  expect(link).toHaveAttribute('href', expect.stringContaining('https://id.example.test/authorize?'));
  const request = calls.find((c) => c.path.endsWith('/oauth'))!;
  expect(request.body).toMatchObject({ expected_revision: 0 });
  expect(request.body).not.toHaveProperty('user_id');
  expect(request.body).not.toHaveProperty('secret');
  expect(localStorage.getItem('access_token')).toBeNull();
});

it('reuses the OAuth intent id on a lost response and rejects an unapproved redirect', async () => {
  const calls = setup({
    definition: oauthDefinition,
    lostPut: true,
    oauthUrl: 'https://attacker.example/steal',
  });
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '使用 OAuth 授权' }));
  await userEvent.click(screen.getByRole('button', { name: '生成安全授权链接' }));
  await screen.findByText(/连接暂时不可用/);
  await userEvent.click(screen.getByRole('button', { name: '生成安全授权链接' }));
  await screen.findByText(/已阻止跳转/);
  expect(screen.queryByRole('link', { name: '前往授权服务器' })).not.toBeInTheDocument();
  const sent = calls.filter((c) => c.path.endsWith('/oauth'));
  expect(sent).toHaveLength(2);
  expect(sent[0].body).toEqual(sent[1].body);
});

it('does not turn uncertain remote revocation into a confirmed source-system disconnect', async () => {
  setup({
    definition: oauthDefinition,
    rows: [{ ...initial, state: 'revoked', credential_cleanup: 'unknown' }],
  });
  mount();
  expect(await screen.findByText('平台已断开；请在源系统核对未确认的授权')).toBeInTheDocument();
  expect(screen.queryByText('授权服务器已确认令牌撤销')).not.toBeInTheDocument();
});

it('discloses that isolated stdio code can read its injected credential without offering a host command field', async () => {
  setup({
    definition: {
      ...server,
      transport: 'stdio',
      endpoint_url: 'stdio://approved-image',
      stdio: {
        profile_id: 'approved-image',
        image_digest: 'sha256:' + 'a'.repeat(64),
        template_digest: 'b'.repeat(64),
        credential_env: 'UPSTREAM_TOKEN',
        network_profile: 'none',
      },
    },
  });
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '配置凭据' }));
  const dialog = screen.getByRole('dialog', { name: '配置 MCP 凭据' });
  expect(within(dialog).getByText(/该进程及同执行单元代码能够读取/)).toBeInTheDocument();
  expect(within(dialog).queryByLabelText(/启动命令/)).not.toBeInTheDocument();
});
