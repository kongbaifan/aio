import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../src/api/client';
import type { AdminOptions, Me, SkillArchiveImport, SkillArchivePrepareRequest } from '../src/api/types';
import { SkillArchives } from '../src/features/SkillArchives';

const id = '30000000-0000-4000-8000-000000000001';
const skill = '30000000-0000-4000-8000-000000000002';
const identity: Me = {
  user_id: '10000000-0000-4000-8000-000000000001',
  org_id: '20000000-0000-4000-8000-000000000001',
  display_name: '归档作者',
  organization_name: '测试组织',
  role: 'org_admin',
  membership_revision: 0,
  csrf_token: 'synthetic-archive-csrf',
  departments: [],
  permissions: { organization_admin: true, operations: true, audit: true },
  capabilities: {
    file_upload: true,
    python_compute: true,
    skill_publishing: true,
    mcp: false,
    knowledge: false,
    team: false,
  },
};
const options: AdminOptions = {
  model_allowed_origins: [],
  model_secret_names: [],
  supported_drivers: [],
  supported_engines: [],
  sandbox_profiles: [{ id: 'standard', image_digest: 'sha256:' + 'a'.repeat(64), max_timeout_seconds: 30 }],
};

function response(value: unknown) {
  return new Response(JSON.stringify(value), { headers: { 'content-type': 'application/json' } });
}
function file() {
  const bytes = new TextEncoder().encode('Synthetic archive bytes, not decoded by the browser.');
  const value = new File([bytes], 'skill.zip', { type: 'application/zip' });
  Object.defineProperty(value, 'arrayBuffer', { configurable: true, value: vi.fn(async () => bytes.buffer) });
  return value;
}

function setup({ available = true, loseFirstResponse = false, initial = false } = {}) {
  const requests: Array<{ path: string; method: string; data: unknown; init: RequestInit }> = [];
  const rows: SkillArchiveImport[] = [];
  let posted = 0;
  function item(body?: SkillArchivePrepareRequest): SkillArchiveImport {
    return {
      id,
      request_id: body?.request_id ?? id,
      state: 'imported',
      revision: 5,
      archive_sha256: body?.sha256 ?? 'a'.repeat(64),
      archive_size: body?.bytes ?? 100,
      archive_format: body?.archive_format ?? 'zip',
      mode: body?.native ? 'native_instruction_only' : 'manifest',
      execution_profile: 'standard',
      queue_expires_at: '2026-09-14T01:00:00Z',
      uploaded_at: '2026-09-14T00:00:00Z',
      created_at: '2026-09-14T00:00:00Z',
      finished_at: '2026-09-14T00:01:00Z',
      cleanup_state: 'confirmed',
      manager_acknowledged: true,
      error_code: null,
      purge_requested: false,
      archive_purged: false,
      skill_id: skill,
      automatically_published: false,
      scan_report: { files: 3, manual_source_license_review_required: true },
    };
  }
  if (initial) rows.push(item());
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, init: RequestInit = {}) => {
      const method = init.method ?? 'GET';
      const data = typeof init.body === 'string' ? JSON.parse(init.body) : init.body;
      requests.push({ path, method, data, init });
      if (path.endsWith('/config'))
        return response({
          available,
          formats: ['zip', 'tar', 'tar.gz'],
          max_bytes: 2 * 1024 * 1024,
          modes: ['manifest', 'native_instruction_only'],
          automatically_published: false,
        });
      if (path === '/api/v2/admin/skill-imports' && method === 'GET') return response({ items: rows });
      if (path === '/api/v2/admin/skill-imports' && method === 'POST') {
        const result = item(data as SkillArchivePrepareRequest);
        if (!rows.length)
          rows.push({ ...result, state: 'awaiting_upload', uploaded_at: null, skill_id: null });
        if (++posted === 1 && loseFirstResponse) throw new TypeError('synthetic lost response');
        return response(rows[0]);
      }
      if (path.endsWith('/content')) {
        rows[0] = { ...rows[0], state: 'imported', skill_id: skill, uploaded_at: '2026-09-14T00:00:00Z' };
        return response(rows[0]);
      }
      if (path.endsWith('/delete')) {
        rows[0] = { ...rows[0], purge_requested: true, archive_purged: true };
        return response(rows[0]);
      }
      throw new Error(`Unexpected fixture request ${method} ${path}`);
    }),
  );
  const onImported = vi.fn(),
    onClose = vi.fn();
  const view = render(<SkillArchives options={options} onClose={onClose} onImported={onImported} />);
  return { requests, rows, onImported, onClose, ...view };
}

beforeEach(() => {
  api.invalidate();
  api.bind(identity);
  vi.stubGlobal('crypto', webcrypto);
});
afterEach(() => {
  api.invalidate();
  vi.unstubAllGlobals();
});

it('uploads only hashed opaque archive bytes and leaves publishing as an explicit later workflow', async () => {
  const test = setup(),
    user = userEvent.setup(),
    archive = file();
  await user.upload(await screen.findByLabelText('Skill 归档文件'), archive);
  await user.click(screen.getByRole('button', { name: '上传并隔离扫描' }));
  await screen.findByText('已生成私有草稿');
  const prepared = test.requests.find((r) => r.method === 'POST')!;
  expect(prepared.data).toMatchObject({
    bytes: archive.size,
    archive_format: 'zip',
    sandbox_profile: 'standard',
    native: null,
  });
  expect((prepared.data as SkillArchivePrepareRequest).sha256).toMatch(/^[0-9a-f]{64}$/);
  const upload = test.requests.find((r) => r.method === 'PUT')!;
  expect(upload.data).toBe(archive);
  expect(new Headers(upload.init.headers).get('content-type')).toBe('application/octet-stream');
  expect(new Headers(upload.init.headers).get('x-csrf-token')).toBe(identity.csrf_token);
  expect(test.requests.some((r) => r.path.includes('/review'))).toBe(false);
  await user.click(screen.getByRole('button', { name: '查看私有草稿' }));
  expect(test.onImported).toHaveBeenCalledWith(skill);
});

it('reuses the identical upload intention after a lost response rather than silently starting another import', async () => {
  const test = setup({ loseFirstResponse: true }),
    user = userEvent.setup();
  await user.upload(await screen.findByLabelText('Skill 归档文件'), file());
  await user.click(screen.getByRole('button', { name: '上传并隔离扫描' }));
  await screen.findByRole('alert');
  await waitFor(() => expect(screen.getByRole('button', { name: '上传并隔离扫描' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: '上传并隔离扫描' }));
  await screen.findByText('已生成私有草稿');
  const posts = test.requests.filter((r) => r.method === 'POST');
  expect(posts).toHaveLength(2);
  expect(posts[0].data).toEqual(posts[1].data);
  expect(test.requests.filter((r) => r.method === 'PUT')).toHaveLength(1);
});

it('makes native SKILL.md imports instruction-only with explicit identity/source metadata', async () => {
  const test = setup(),
    user = userEvent.setup();
  await user.selectOptions(await screen.findByLabelText('归档结构'), 'native');
  await user.type(screen.getByLabelText('归档 Skill 名称'), 'native-fixture');
  await user.type(screen.getByLabelText('归档用途说明'), '仅为指令');
  await user.upload(screen.getByLabelText('Skill 归档文件'), file());
  await user.click(screen.getByRole('button', { name: '上传并隔离扫描' }));
  await screen.findByText('已生成私有草稿');
  const posted = test.requests.find((r) => r.method === 'POST')!.data as SkillArchivePrepareRequest;
  expect(posted.native).toMatchObject({ name: 'native-fixture', version: '1.0.0', description: '仅为指令' });
  expect(posted.native).not.toHaveProperty('entrypoints');
});

it('does not offer an upload or local extraction fallback when no operator scanner is configured', async () => {
  const test = setup({ available: false });
  await screen.findByText(/运维尚未启用固定归档扫描环境/);
  expect(screen.queryByLabelText('Skill 归档文件')).not.toBeInTheDocument();
  expect(test.requests.every((r) => r.method === 'GET')).toBe(true);
});

it('requires explicit raw-archive cleanup confirmation and never deletes the generated Skill', async () => {
  const test = setup({ initial: true }),
    user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: '清理归档' }));
  expect(test.requests.every((r) => r.method === 'GET')).toBe(true);
  expect(screen.getByText(/已经生成的 Skill 不会被删除或撤回/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '确认清理原始归档' }));
  await screen.findByText('原始归档已清理');
  const posts = test.requests.filter((r) => r.method === 'POST');
  expect(posts).toHaveLength(1);
  expect(posts[0].path).toBe(`/api/v2/admin/skill-imports/${id}/delete`);
  expect(posts[0].data).toEqual({ expected_revision: 5 });
});

it('does not submit a file after its dialog closes while checksum preparation is pending', async () => {
  const test = setup(),
    user = userEvent.setup(),
    archive = file();
  let complete: ((value: ArrayBuffer) => void) | undefined;
  Object.defineProperty(archive, 'arrayBuffer', {
    configurable: true,
    value: () =>
      new Promise<ArrayBuffer>((resolve) => {
        complete = resolve;
      }),
  });
  await user.upload(await screen.findByLabelText('Skill 归档文件'), archive);
  await user.click(screen.getByRole('button', { name: '上传并隔离扫描' }));
  test.unmount();
  complete?.(new ArrayBuffer(1));
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(test.requests.every((r) => r.method === 'GET')).toBe(true);
});
