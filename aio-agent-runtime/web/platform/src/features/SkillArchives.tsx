import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Archive, Download, RefreshCw, Trash2 } from 'lucide-react';
import { api, ApiError, explain, isAbort } from '../api/client';
import type {
  AdminOptions,
  Page,
  SkillArchiveConfig,
  SkillArchiveImport,
  SkillArchivePrepareRequest,
} from '../api/types';
import { formatBytes, formatDate, shortId, useResource } from '../hooks';
import { Button, Empty, ErrorBox, Field, Loading, Modal, Notice } from '../components/ui';

const STATES: Record<SkillArchiveImport['state'], string> = {
  awaiting_upload: '等待上传',
  uploading: '保存归档中',
  queued: '等待隔离扫描',
  leased: '隔离扫描中',
  stopping: '确认环境清理',
  imported: '已生成私有草稿',
  rejected: '导入未通过',
  cancelled: '已取消',
};
const ACTIVE = new Set(['awaiting_upload', 'uploading', 'queued', 'leased', 'stopping']);

export function SkillArchives({
  options,
  onClose,
  onImported,
}: {
  options: AdminOptions | null;
  onClose: () => void;
  onImported: (id: string) => void;
}) {
  const config = useResource<SkillArchiveConfig>('/api/v2/admin/skill-imports/config');
  const imports = useResource<Page<SkillArchiveImport>>('/api/v2/admin/skill-imports');
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [mode, setMode] = useState<'manifest' | 'native'>('manifest');
  const [profile, setProfile] = useState(options?.sandbox_profiles[0]?.id ?? '');
  const [native, setNative] = useState({
    name: '',
    version: '1.0.0',
    description: '',
    source: '公司内部提供',
    license: '内部使用（待审核）',
  });
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [removing, setRemoving] = useState<SkillArchiveImport | null>(null);
  const operation = useRef<AbortController | null>(null);
  const intention = useRef<{ key: string; body: SkillArchivePrepareRequest } | null>(null);
  useEffect(() => () => operation.current?.abort(), []);
  const active = imports.data?.items.some(
    (item) => ACTIVE.has(item.state) || (item.purge_requested && !item.archive_purged),
  );
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(imports.reload, 1500);
    return () => window.clearInterval(timer);
  }, [active, imports.reload]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !config.data?.available || !profile) return;
    setError('');
    setNotice('');
    if (!file.size || file.size > config.data.max_bytes) {
      setError(`请选择非空且不超过 ${formatBytes(config.data.max_bytes)} 的归档。`);
      return;
    }
    const name = file.name.toLowerCase();
    const format =
      name.endsWith('.tar.gz') || name.endsWith('.tgz')
        ? 'tar.gz'
        : name.endsWith('.tar')
          ? 'tar'
          : name.endsWith('.zip')
            ? 'zip'
            : null;
    if (!format) {
      setError('请选择 ZIP、TAR 或 TAR.GZ 文件。');
      return;
    }
    const controller = new AbortController();
    operation.current = controller;
    setBusy('upload');
    try {
      // Hash and transfer opaque bytes only. No archive extraction or script parsing in the browser.
      const hash = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
      if (controller.signal.aborted) return;
      const sha = Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('');
      const data: Omit<SkillArchivePrepareRequest, 'request_id'> = {
        archive_format: format,
        bytes: file.size,
        sha256: sha,
        sandbox_profile: profile,
        native: mode === 'native' ? native : null,
      };
      const key = JSON.stringify(data);
      const saved =
        intention.current?.key === key
          ? intention.current
          : { key, body: { ...data, request_id: crypto.randomUUID() } };
      intention.current = saved;
      const prepared = await api.request<SkillArchiveImport>(
        '/api/v2/admin/skill-imports',
        'POST',
        saved.body,
        { signal: controller.signal },
      );
      await api.request<SkillArchiveImport>(
        `/api/v2/admin/skill-imports/${prepared.id}/content`,
        'PUT',
        undefined,
        {
          signal: controller.signal,
          body: file,
          headers: { 'Content-Type': 'application/octet-stream' },
        },
      );
      if (controller.signal.aborted) return;
      setNotice('归档已提交隔离扫描。只有生成私有草稿后，才能继续申请验证和双人审核。');
      setFile(null);
      setFileKey((value) => value + 1);
      intention.current = null;
      imports.reload();
    } catch (failure) {
      if (!controller.signal.aborted && !isAbort(failure)) {
        setError(explain(failure));
        imports.reload();
      }
    } finally {
      if (!controller.signal.aborted) setBusy('');
    }
  }

  async function remove() {
    if (!removing) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(removing.id);
    setError('');
    try {
      await api.request(
        `/api/v2/admin/skill-imports/${removing.id}/delete`,
        'POST',
        { expected_revision: removing.revision },
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setRemoving(null);
        imports.reload();
      }
    } catch (failure) {
      if (!controller.signal.aborted && !isAbort(failure)) setError(explain(failure));
    } finally {
      if (!controller.signal.aborted) setBusy('');
    }
  }

  return (
    <Modal
      title="隔离导入 Skill 归档"
      onClose={onClose}
      description="归档先进入私有隔离区，不在服务器控制进程解压，也不会自动发布或共享。"
    >
      <div className="form-stack">
        {config.loading && !config.data ? (
          <Loading label="正在读取归档准入配置…" />
        ) : !config.data?.available ? (
          <Notice>
            运维尚未启用固定归档扫描环境。需要配置 PLATFORM_SKILL_IMPORT_PROFILE、隔离 Manager
            和私有存储；不会退回宿主解压。
          </Notice>
        ) : (
          <form onSubmit={(event) => void submit(event)} className="form-stack">
            <div className="form-grid">
              <Field label="归档结构">
                <select
                  value={mode}
                  disabled={Boolean(busy)}
                  onChange={(event) => {
                    setMode(event.target.value as 'manifest' | 'native');
                    intention.current = null;
                  }}
                >
                  <option value="manifest">含 skill.json 的能力包（v1/v2）</option>
                  <option value="native">原生 SKILL.md 文件夹（仅指令）</option>
                </select>
              </Field>
              <Field
                label="生成 Skill 的执行环境"
                hint="扫描环境由运维固定配置；这里指定后续验证和执行所用的批准镜像。"
              >
                <select
                  required
                  value={profile}
                  disabled={Boolean(busy)}
                  onChange={(event) => {
                    setProfile(event.target.value);
                    intention.current = null;
                  }}
                >
                  <option value="">选择批准环境</option>
                  {options?.sandbox_profiles.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id}
                      {item.runtime ? ' · 固定依赖' : ''}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            {mode === 'native' && (
              <>
                <Notice>
                  保留 SKILL.md 原文；脚本只作为包内数据，不会从 frontmatter
                  自动创建执行工具。来源和许可证仍需审核。
                </Notice>
                <div className="form-grid">
                  <Field label="归档 Skill 名称">
                    <input
                      required
                      pattern="[a-z][a-z0-9-]{0,39}"
                      value={native.name}
                      disabled={Boolean(busy)}
                      onChange={(e) => {
                        setNative({ ...native, name: e.target.value });
                        intention.current = null;
                      }}
                    />
                  </Field>
                  <Field label="归档 Skill 版本">
                    <input
                      required
                      value={native.version}
                      disabled={Boolean(busy)}
                      onChange={(e) => {
                        setNative({ ...native, version: e.target.value });
                        intention.current = null;
                      }}
                    />
                  </Field>
                  <Field label="归档用途说明">
                    <input
                      required
                      maxLength={1024}
                      value={native.description}
                      disabled={Boolean(busy)}
                      onChange={(e) => {
                        setNative({ ...native, description: e.target.value });
                        intention.current = null;
                      }}
                    />
                  </Field>
                  <Field label="归档来源">
                    <input
                      required
                      maxLength={1024}
                      value={native.source}
                      disabled={Boolean(busy)}
                      onChange={(e) => {
                        setNative({ ...native, source: e.target.value });
                        intention.current = null;
                      }}
                    />
                  </Field>
                  <Field label="归档许可证声明">
                    <input
                      required
                      maxLength={128}
                      value={native.license}
                      disabled={Boolean(busy)}
                      onChange={(e) => {
                        setNative({ ...native, license: e.target.value });
                        intention.current = null;
                      }}
                    />
                  </Field>
                </div>
              </>
            )}
            <Field
              label="Skill 归档文件"
              hint={`ZIP / TAR / TAR.GZ，不超过 ${formatBytes(config.data.max_bytes)}；仅接受有界 UTF-8 文本包，不含链接、隐藏配置或二进制资产。`}
            >
              <input
                key={fileKey}
                aria-label="Skill 归档文件"
                type="file"
                accept=".zip,.tar,.tar.gz,.tgz"
                disabled={Boolean(busy)}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  intention.current = null;
                  setError('');
                }}
              />
            </Field>
            <Button type="submit" busy={busy === 'upload'} disabled={!file || !profile || Boolean(busy)}>
              <Archive size={16} />
              上传并隔离扫描
            </Button>
          </form>
        )}
        {notice && <Notice>{notice}</Notice>}
        <ErrorBox
          message={error || config.error || imports.error}
          retry={() => {
            config.reload();
            imports.reload();
          }}
        />
        <div className="section-top">
          <div>
            <h3>我的归档导入</h3>
            <p>只有当前作者可读取原始归档；其他管理员不自动获得访问权。</p>
          </div>
          <Button variant="quiet" onClick={imports.reload}>
            <RefreshCw size={15} />
            刷新
          </Button>
        </div>
        {imports.loading && !imports.data ? (
          <Loading />
        ) : !imports.data?.items.length ? (
          <Empty title="还没有归档导入">可先选择一个经过来源审核的 Skill 包。</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>归档</th>
                  <th>状态</th>
                  <th>后续操作</th>
                </tr>
              </thead>
              <tbody>
                {imports.data.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <strong>
                        {shortId(item.id)} · {item.archive_format}
                      </strong>
                      <small>
                        {formatBytes(item.archive_size)} · {formatDate(item.created_at)}
                      </small>
                      <code>{item.archive_sha256.slice(0, 12)}…</code>
                    </td>
                    <td>
                      {STATES[item.state]}
                      {item.archive_purged ? (
                        <small>原始归档已清理</small>
                      ) : item.purge_requested ? (
                        <small>等待安全清理原始归档</small>
                      ) : null}
                      {item.cleanup_state === 'pending' && <small>执行环境尚未确认清理</small>}
                      {item.error_code && (
                        <small role="status">{explain(new ApiError(item.error_code, 422))}</small>
                      )}
                    </td>
                    <td>
                      {item.skill_id && (
                        <Button variant="secondary" onClick={() => onImported(item.skill_id!)}>
                          查看私有草稿
                        </Button>
                      )}
                      {item.uploaded_at && !item.archive_purged && !item.purge_requested && (
                        <Button
                          variant="quiet"
                          disabled={Boolean(busy)}
                          onClick={() => {
                            void api
                              .download(
                                `/api/v2/admin/skill-imports/${item.id}/download`,
                                `skill-archive.${item.archive_format}`,
                              )
                              .catch((failure) => setError(explain(failure)));
                          }}
                        >
                          <Download size={14} />
                          原始归档
                        </Button>
                      )}
                      {!item.purge_requested && (
                        <Button variant="quiet" disabled={Boolean(busy)} onClick={() => setRemoving(item)}>
                          <Trash2 size={14} />
                          清理归档
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {removing && (
          <div className="form-stack" role="group" aria-label="确认清理原始归档">
            <Notice>
              清理 {shortId(removing.id)}{' '}
              的原始归档会停止尚未完成的导入；必须确认执行环境停止后才释放存储。已经生成的 Skill
              不会被删除或撤回。
            </Notice>
            <div>
              <Button variant="danger" busy={busy === removing.id} onClick={() => void remove()}>
                确认清理原始归档
              </Button>
              <Button variant="quiet" disabled={Boolean(busy)} onClick={() => setRemoving(null)}>
                返回
              </Button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
