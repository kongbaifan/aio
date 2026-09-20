import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { api } from '../src/api/client';
import type { Me } from '../src/api/types';
import { AuthProvider } from '../src/auth';
import { Layout } from '../src/components/Layout';
import { KnowledgePage, KnowledgeDetailPage } from '../src/features/Knowledge';
import { AdminPage } from '../src/features/Admin';

const uid = '10000000-0000-4000-8000-000000000001',
  kid = '20000000-0000-4000-8000-000000000001',
  did = '30000000-0000-4000-8000-000000000001',
  vid = '40000000-0000-4000-8000-000000000001',
  mid = '50000000-0000-4000-8000-000000000001',
  cid = '60000000-0000-4000-8000-000000000001';
const me: Me = {
  user_id: uid,
  org_id: '70000000-0000-4000-8000-000000000001',
  display_name: '知识维护者',
  organization_name: '合成组织',
  role: 'org_admin',
  membership_revision: 0,
  csrf_token: 'test-csrf',
  departments: [],
  permissions: { organization_admin: true, operations: true, audit: true },
  capabilities: {
    knowledge: true,
    file_upload: true,
    python_compute: true,
    skill_publishing: true,
    mcp: false,
    team: false,
  },
};
const kb = {
  id: kid,
  name: '报销知识',
  description: '已授权的业务资料',
  embedding_model_id: null,
  profile_id: 'documents',
  image_digest: 'sha256:' + '1'.repeat(64),
  tool_id: mid,
  index_revision: 1,
  storage_limit_bytes: 67108864,
  created_at: '2026-09-12T00:00:00Z',
  can_manage: true,
};
const document = {
  id: did,
  knowledge_id: kid,
  title: '报销规定',
  owner_id: uid,
  visibility: 'restricted',
  state: 'active',
  current_version_id: vid,
  revision: 2,
  versions: [
    {
      id: vid,
      number: 1,
      filename: 'policy.txt',
      format: 'txt',
      state: 'ready',
      source_bytes: 42,
      warnings: [],
      created_at: '2026-09-12T00:00:00Z',
    },
  ],
  latest_job: {
    id: mid,
    state: 'ready',
    phase: 'publish',
    generation: 1,
    cleanup_state: 'confirmed',
    export_acknowledged: true,
    error_code: null,
  },
};
const embedding = {
  id: mid,
  name: '批准的嵌入模型',
  model: 'test-embedding',
  config: {
    dimensions: 3,
    endpoint: 'https://embedding.example.test/v1/embeddings',
    secret_env: 'APPROVED_EMBED_KEY',
    input_price_per_million: '1',
    max_call_charge: '0.01',
    batch_size: 32,
  },
  digest: 'b'.repeat(64),
};
const citation = {
  id: cid,
  label: 'K-fixed',
  document_id: did,
  version_id: vid,
  title: '报销规定',
  filename: 'policy.txt',
  version: 1,
  location: { kind: 'lines', line_start: 1, line_end: 2 },
  text: '餐费上限200元。<script>window.unsafe=1</script>',
  download_url: `/api/v2/knowledge/versions/${vid}/download`,
};
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}
function setup() {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const path = String(input),
        method = init.method ?? 'GET';
      const body = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
      calls.push({ path, method, body });
      if (path === '/api/v2/me') return response(me);
      if (
        path === '/api/v2/projects' ||
        path === '/api/v2/sessions' ||
        path === '/api/v2/skills' ||
        path === '/api/v2/admin/tools'
      )
        return response({ items: [] });
      if (path === '/api/v2/knowledge/options')
        return response({
          parser_profiles: [{ id: 'documents', image_digest: 'sha256:' + '1'.repeat(64) }],
          formats: ['txt', 'pdf', 'docx', 'xlsx', 'csv', 'md'],
        });
      if (path === '/api/v2/knowledge' && method === 'POST') return response(kb, 201);
      if (path === '/api/v2/knowledge') return response({ items: [kb] });
      if (path === `/api/v2/knowledge/${kid}`) return response(kb);
      if (path === `/api/v2/knowledge/${kid}/documents` && method === 'POST')
        return response({ document_id: did, version_id: vid, number: 1, state: 'uploading' }, 201);
      if (path === `/api/v2/knowledge/${kid}/documents`) return response({ items: [document] });
      if (path === `/api/v2/knowledge/uploads/${vid}/content`)
        return response({ version_id: vid, state: 'queued' });
      if (path === `/api/v2/knowledge/${kid}/search`)
        return response({
          query_id: mid,
          matches: [citation],
          answerable: true,
          retrieval_mode: 'lexical',
          untrusted_reference_data: true,
        });
      if (path === `/api/v2/knowledge/citations/${cid}`) return response(citation);
      if (path === `/api/v2/knowledge/documents/${did}/visibility`)
        return response({ id: did, visibility: body.visibility, revision: 3 });
      if (path === `/api/v2/knowledge/documents/${did}` && method === 'DELETE')
        return response({ id: did, state: 'deleting', access_revoked: true });
      if (path === '/api/v2/embedding-models') return response({ items: [embedding] });
      if (path === '/api/v2/admin/embedding-models') return response(embedding, 201);
      if (path === '/api/v2/admin/options')
        return response({
          model_allowed_origins: ['https://embedding.example.test'],
          model_secret_names: ['APPROVED_EMBED_KEY'],
          sandbox_profiles: [],
          supported_drivers: [],
          supported_engines: [],
          document_profiles: [{ id: 'documents', image_digest: kb.image_digest, max_timeout_seconds: 60 }],
        });
      if (path === '/api/v2/admin/embedding-calls')
        return response({
          items: [
            { id: mid, requested_by: uid, state: 'unknown', max_charge: '0.01', job_id: did, run_id: null },
          ],
        });
      if (path === '/api/v2/admin/models')
        return response({
          items: [{ id: mid, provider: 'test', model: 'test', status: 'active', config: {} }],
        });
      if (path === '/api/v2/admin/agents' && method === 'POST') return response({ id: mid }, 201);
      if (path === '/api/v2/admin/agents') return response({ items: [] });
      return response({ error: { code: 'RESOURCE_NOT_FOUND' } }, 404);
    }),
  );
  return calls;
}
function mount(path = '/app/knowledge') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/app/knowledge" element={<KnowledgePage />} />
            <Route path="/app/knowledge/:knowledgeId" element={<KnowledgeDetailPage />} />
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

it('defaults to lexical indexing and requires explicit acknowledgement for embedding data egress', async () => {
  const calls = setup();
  mount();
  await userEvent.click(await screen.findByRole('button', { name: '创建知识库' }));
  await userEvent.type(screen.getByLabelText('知识库名称'), '项目资料');
  await userEvent.type(screen.getByLabelText('资料用途'), '报销流程');
  expect(screen.getByLabelText('检索方式')).toHaveValue('');
  await userEvent.selectOptions(screen.getByLabelText('检索方式'), mid);
  expect(screen.getByRole('button', { name: '创建私有知识库' })).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: /我确认可将授权文档片段/ }));
  await userEvent.click(screen.getByRole('button', { name: '创建私有知识库' }));
  await waitFor(() =>
    expect(calls.find((c) => c.path === '/api/v2/knowledge' && c.method === 'POST')?.body).toMatchObject({
      name: '项目资料',
      parser_profile: 'documents',
      embedding_model_id: mid,
    }),
  );
});

it('uploads into a bound private document version and does not default to KB-wide sharing', async () => {
  const calls = setup();
  mount(`/app/knowledge/${kid}`);
  await userEvent.click(await screen.findByRole('button', { name: '上传文档' }));
  const dialog = screen.getByRole('dialog', { name: '上传知识文档' });
  expect(within(dialog).getByRole('checkbox')).not.toBeChecked();
  const file = new File(['private test document'], 'policy.txt', { type: 'text/plain' });
  await userEvent.upload(within(dialog).getByLabelText('原始文档'), file);
  expect(within(dialog).getByLabelText('文档标题')).toHaveValue('policy.txt');
  expect((within(dialog).getByLabelText('原始文档') as HTMLInputElement).files?.length).toBe(1);
  expect(within(dialog).getByRole('button', { name: '上传并进入隔离摄取' })).toBeEnabled();
  // jsdom's synthetic FileList does not update the native required-file validity state.
  // Exercise the submit handler after verifying the selected File and enabled control;
  // real browser constraint/visual verification remains a separate gate.
  fireEvent.submit(dialog.querySelector('form')!);
  await waitFor(() =>
    expect(calls.filter((c) => c.method !== 'GET').map((c) => [c.path, c.method])).toContainEqual([
      `/api/v2/knowledge/uploads/${vid}/content`,
      'PUT',
    ]),
  );
  expect(calls.find((c) => c.path.endsWith('/documents') && c.method === 'POST')?.body).toMatchObject({
    visibility: 'restricted',
    filename: 'policy.txt',
    max_bytes: file.size,
  });
  expect(calls.find((c) => c.path.endsWith('/content'))?.body).toBe(file);
});

it('search previews and citations remain inert text and refer to a fixed version', async () => {
  const calls = setup();
  const page = mount(`/app/knowledge/${kid}`);
  await userEvent.type(await screen.findByLabelText('检索问题或关键词'), '餐费标准');
  await userEvent.click(screen.getByRole('button', { name: '检索获权片段' }));
  await userEvent.click(await screen.findByRole('button', { name: /K-fixed/ }));
  await screen.findByRole('dialog', { name: '报销规定' });
  expect(screen.getByText(/版本 1 · 第 1–2 行/)).toBeInTheDocument();
  expect(page.container.querySelector('.citation-text script')).toBeNull();
  expect(calls.some((c) => c.path.endsWith(`/citations/${cid}`))).toBe(true);
  expect(calls.some((c) => c.path.includes('/v1/embeddings'))).toBe(false);
});

it('deletion requires confirmation and sends the document revision, not a raw filesystem path', async () => {
  const calls = setup();
  mount(`/app/knowledge/${kid}`);
  await userEvent.click(await screen.findByRole('button', { name: '删除' }));
  const dialog = screen.getByRole('dialog', { name: '删除这个文档及其版本？' });
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
  await userEvent.click(within(dialog).getByRole('button', { name: '确认删除' }));
  await waitFor(() =>
    expect(calls.find((c) => c.method === 'DELETE')?.body).toEqual({ expected_revision: 2 }),
  );
});

it('changing document inheritance is a separate explicit permission action', async () => {
  const calls = setup();
  mount(`/app/knowledge/${kid}`);
  await userEvent.click(await screen.findByRole('button', { name: '开放给知识库成员' }));
  expect(calls.some((c) => c.method === 'PATCH')).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: '确认权限变更' }));
  await waitFor(() =>
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      expected_revision: 2,
      visibility: 'inherited',
    }),
  );
});

it('embedding administration uses approved secret names and cannot self-confirm unknown usage', async () => {
  const calls = setup();
  mount('/app/admin/embeddings');
  expect(await screen.findByRole('button', { name: '录入核对依据' })).toBeDisabled();
  await userEvent.click(screen.getByRole('button', { name: '登记嵌入模型' }));
  await userEvent.type(screen.getByLabelText('显示名称'), '受控嵌入');
  await userEvent.type(screen.getByLabelText('模型标识'), 'test-embedding');
  expect(screen.queryByLabelText('API Key')).toBeNull();
  expect(screen.getByLabelText('获准密钥变量名')).toHaveValue('APPROVED_EMBED_KEY');
  await userEvent.click(screen.getByRole('button', { name: '保存嵌入模型配置' }));
  await waitFor(() =>
    expect(
      calls.find((c) => c.path === '/api/v2/admin/embedding-models' && c.method === 'POST')?.body,
    ).toMatchObject({
      secret_env: 'APPROVED_EMBED_KEY',
      endpoint: 'https://embedding.example.test/v1/embeddings',
    }),
  );
});

it('Agent creation binds the knowledge base rather than exposing a global file directory', async () => {
  const calls = setup();
  mount('/app/admin/agents');
  await userEvent.click(await screen.findByRole('button', { name: '新建 Agent' }));
  await userEvent.type(screen.getByLabelText('Agent 名称'), '资料助手');
  await userEvent.click(await screen.findByRole('checkbox', { name: /报销知识/ }));
  await userEvent.click(screen.getByRole('button', { name: '发布这个版本' }));
  await waitFor(() =>
    expect(calls.find((c) => c.path === '/api/v2/admin/agents' && c.method === 'POST')?.body).toMatchObject({
      knowledge_ids: [kid],
    }),
  );
});
