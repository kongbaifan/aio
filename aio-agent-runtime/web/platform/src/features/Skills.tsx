import { Fragment, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import {
  BookOpen,
  CheckCircle2,
  FileCode2,
  KeyRound,
  Package,
  Plus,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { api, explain } from '../api/client';
import type {
  AdminOptions,
  Member,
  Page,
  SkillCreateRequest,
  SkillDetail,
  SkillPackageRequest,
  SkillReviewRequest,
  SkillValidateRequest,
  SkillVersion,
} from '../api/types';
import { useAuth } from '../auth';
import { formatBytes, formatDate, shortId, useResource } from '../hooks';
import { GrantModal } from '../components/GrantModal';
import { Button, Empty, ErrorBox, Field, Loading, Modal, Notice } from '../components/ui';
import { SkillArchives } from './SkillArchives';

const STATE: Record<SkillVersion['state'], string> = {
  draft: '私有草稿',
  validating: '隔离验证中',
  validated: '等待人工审核',
  rejected: '未获准发布',
  published: '已发布',
};
const EXAMPLE: SkillPackageRequest = {
  schema_version: 1,
  name: 'sales-helper',
  version: '1.0.0',
  description: '销售数据计算说明',
  source: '公司内部编写',
  license: '内部使用',
  instruction_path: 'SKILL.md',
  reference_paths: [],
  entrypoints: [],
  files: [
    { path: 'SKILL.md', content: '# 销售分析\n仅处理当前项目的获权资料，结果应包含可核对的计算过程。' },
  ],
};

export function Skills() {
  const { me } = useAuth();
  const registry = useResource<Page<SkillVersion>>('/api/v2/admin/skills');
  const options = useResource<AdminOptions>('/api/v2/admin/options');
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [share, setShare] = useState<SkillVersion | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  async function toggle(row: SkillVersion) {
    setBusy(row.id);
    setError('');
    try {
      await api.request(`/api/v2/resources/${row.id}/status`, 'PATCH', {
        expected_revision: row.resource_revision,
        status: row.resource_status === 'active' ? 'disabled' : 'active',
      });
      registry.reload();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy('');
    }
  }
  return (
    <section className="admin-section">
      <div className="section-top">
        <div>
          <h2>共享 Skill 版本库</h2>
          <p>共享经过审核的固定能力，不共享可写的服务器目录。草稿只对作者和指定审核人开放。</p>
        </div>
        <div className="form-grid">
          <Button variant="secondary" onClick={() => setImporting(true)}>
            导入归档
          </Button>
          <Button
            onClick={() => setCreating(true)}
            disabled={!me?.capabilities.skill_publishing || !options.data?.sandbox_profiles.length}
          >
            <Plus size={16} />
            创建 Skill
          </Button>
        </div>
      </div>
      <ol className="skill-release-path" aria-label="Skill 发布流程">
        <li>
          <Package size={19} />
          <span>
            <strong>私有草稿</strong>
            <small>固定内容与版本摘要</small>
          </span>
        </li>
        <li>
          <FileCode2 size={19} />
          <span>
            <strong>隔离验证</strong>
            <small>结构检查与合成输入测试</small>
          </span>
        </li>
        <li>
          <ShieldCheck size={19} />
          <span>
            <strong>双人审核</strong>
            <small>检查用途、权限与行为</small>
          </span>
        </li>
        <li>
          <CheckCircle2 size={19} />
          <span>
            <strong>明确授权</strong>
            <small>按部门或成员分享 Agent</small>
          </span>
        </li>
      </ol>
      {!me?.capabilities.skill_publishing && (
        <Notice>
          发布需要操作员配置隔离 Manager 和固定 Python profile。未配置时不会退回服务器本地执行。
        </Notice>
      )}
      <ErrorBox message={error || registry.error || options.error} retry={registry.reload} />
      {registry.loading ? (
        <Loading label="正在读取 Skill 版本…" />
      ) : !registry.data?.items.length ? (
        <Empty
          title="把可复用的经验变成受控能力"
          action={
            <Button
              variant="secondary"
              disabled={!me?.capabilities.skill_publishing}
              onClick={() => setCreating(true)}
            >
              创建第一个私有草稿
            </Button>
          }
        >
          先编写任务说明；需要执行代码时，导入带输入输出 schema 和测试样例的能力包。
        </Empty>
      ) : (
        <div className="skill-catalog">
          {registry.data.items.map((row) => (
            <article className="skill-card" key={row.id}>
              <header>
                <span className="skill-icon">
                  <BookOpen size={22} />
                </span>
                <div>
                  <h3>{row.name}</h3>
                  <small>
                    v{row.version} · {row.profile_id}
                  </small>
                </div>
                <span
                  className={`skill-state skill-state-${row.resource_status === 'disabled' ? 'rejected' : row.state}`}
                >
                  {row.resource_status === 'disabled' ? '已禁用' : STATE[row.state]}
                </span>
              </header>
              <dl className="skill-facts">
                <div>
                  <dt>内容指纹</dt>
                  <dd className="mono">{row.digest.slice(0, 16)}…</dd>
                </div>
                <div>
                  <dt>发布工具</dt>
                  <dd>{row.published_tools.length} 个</dd>
                </div>
                <div>
                  <dt>创建时间</dt>
                  <dd>{formatDate(row.created_at)}</dd>
                </div>
              </dl>
              <footer>
                <Button
                  variant="secondary"
                  onClick={() => setSelected(row.id)}
                  disabled={row.resource_status !== 'active'}
                >
                  查看包与验证
                </Button>
                {row.state === 'published' && (
                  <>
                    <Button variant="quiet" onClick={() => setShare(row)}>
                      <KeyRound size={15} />
                      授权
                    </Button>
                    <Button variant="quiet" busy={busy === row.id} onClick={() => void toggle(row)}>
                      {row.resource_status === 'active' ? '禁用版本' : '重新启用'}
                    </Button>
                  </>
                )}
              </footer>
            </article>
          ))}
        </div>
      )}
      {creating && (
        <CreateSkill
          options={options.data}
          onClose={() => setCreating(false)}
          onCreated={(id) => {
            setCreating(false);
            registry.reload();
            setSelected(id);
          }}
        />
      )}
      {importing && (
        <SkillArchives
          key={`${me?.org_id}:${me?.user_id}`}
          options={options.data}
          onClose={() => setImporting(false)}
          onImported={(id) => {
            setImporting(false);
            registry.reload();
            setSelected(id);
          }}
        />
      )}
      {selected && (
        <SkillInspector
          id={selected}
          onClose={() => {
            setSelected(null);
            registry.reload();
          }}
          onChange={registry.reload}
        />
      )}
      {share && (
        <GrantModal id={share.id} name={`${share.name}@${share.version}`} onClose={() => setShare(null)} />
      )}
    </section>
  );
}

function CreateSkill({
  options,
  onClose,
  onCreated,
}: {
  options: AdminOptions | null;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const [mode, setMode] = useState<'instructions' | 'package'>('instructions');
  const [form, setForm] = useState({
    name: '',
    version: '1.0.0',
    description: '',
    source: '',
    license: '公司内部使用',
    instruction: '',
  });
  const [profile, setProfile] = useState(options?.sandbox_profiles[0]?.id ?? '');
  const runtime = options?.sandbox_profiles.find((item) => item.id === profile)?.runtime;
  const [source, setSource] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load(file: File | undefined) {
    if (!file) return;
    if (file.size > 262144) {
      setError('能力包 JSON 不能超过 256 KiB。');
      return;
    }
    try {
      setSource(await file.text());
      setError('');
    } catch {
      setError('无法读取选择的本地文件。');
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      let payload: SkillCreateRequest;
      if (mode === 'package') {
        if (new TextEncoder().encode(source).length > 262144) throw new Error('package-size');
        const value: unknown = JSON.parse(source);
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('package-json');
        // The generated request shape documents the contract; the server validates every untrusted field.
        payload = { package: value as SkillPackageRequest, sandbox_profile: profile };
      } else {
        payload = {
          sandbox_profile: profile,
          package: {
            schema_version: 1,
            name: form.name,
            version: form.version,
            description: form.description,
            source: form.source,
            license: form.license,
            instruction_path: 'SKILL.md',
            files: [{ path: 'SKILL.md', content: form.instruction }],
            reference_paths: [],
            entrypoints: [],
          },
        };
      }
      const row = await api.request<SkillVersion>('/api/v2/admin/skills', 'POST', payload);
      onCreated(row.id);
    } catch (error) {
      setError(
        error instanceof SyntaxError
          ? '请输入有效的能力包 JSON。'
          : error instanceof Error && error.message.startsWith('package-')
            ? '能力包必须是 256 KiB 以内的 JSON 对象。'
            : explain(error),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="创建私有 Skill 草稿"
      description="版本号与内容保存后不可覆盖；修改需创建新版本。创建草稿不会运行脚本。"
      onClose={onClose}
    >
      <form className="form-stack" onSubmit={submit}>
        <ErrorBox message={error} />
        <fieldset className="skill-mode">
          <legend>内容来源</legend>
          <label>
            <input
              type="radio"
              name="skill-mode"
              checked={mode === 'instructions'}
              onChange={() => setMode('instructions')}
            />
            编写任务说明
          </label>
          <label>
            <input
              type="radio"
              name="skill-mode"
              checked={mode === 'package'}
              onChange={() => setMode('package')}
            />
            导入能力包 JSON
          </label>
        </fieldset>
        {mode === 'instructions' ? (
          <Fragment key="instructions">
            <div className="form-grid">
              <Field label="Skill 标识" hint="小写英文字母、数字、连字符">
                <input
                  required
                  pattern="[a-z][a-z0-9-]{0,39}"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="语义版本">
                <input
                  required
                  pattern="[0-9]+\.[0-9]+\.[0-9]+"
                  value={form.version}
                  onChange={(e) => setForm({ ...form, version: e.target.value })}
                />
              </Field>
            </div>
            <Field label="用途说明">
              <input
                required
                maxLength={1024}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </Field>
            <div className="form-grid">
              <Field label="内容来源">
                <input
                  required
                  maxLength={1024}
                  placeholder="例如：财务部内部编写"
                  value={form.source}
                  onChange={(e) => setForm({ ...form, source: e.target.value })}
                />
              </Field>
              <Field label="许可范围">
                <input
                  required
                  maxLength={128}
                  value={form.license}
                  onChange={(e) => setForm({ ...form, license: e.target.value })}
                />
              </Field>
            </div>
            <Field label="SKILL.md 任务说明" hint="说明不能授予额外权限；请勿粘贴 API Key 或其他凭据。">
              <textarea
                required
                rows={8}
                maxLength={32768}
                value={form.instruction}
                onChange={(e) => setForm({ ...form, instruction: e.target.value })}
              />
            </Field>
          </Fragment>
        ) : (
          <Fragment key="package">
            <Notice>
              目前接收显式文本能力包（Markdown、Python、JSON、CSV、TXT）；不接收
              ZIP、二进制依赖或安装钩子。Python 入口为 run(payload)，必须提供封闭的输入输出 schema
              和合成测试。
            </Notice>
            <Field label="选择能力包 JSON">
              <input
                type="file"
                accept=".json,application/json"
                onChange={(e) => void load(e.target.files?.[0])}
              />
            </Field>
            <Field label="能力包内容">
              <textarea
                className="code-input"
                required
                rows={12}
                value={source}
                onChange={(e) => setSource(e.target.value)}
                spellCheck={false}
              />
            </Field>
            <details className="skill-source">
              <summary>查看最小格式示例</summary>
              <pre>{JSON.stringify(EXAMPLE, null, 2)}</pre>
            </details>
          </Fragment>
        )}
        <Field
          label="固定验证与执行环境"
          hint="只使用操作员批准的不可变镜像；依赖在隔离 CI 构建，不在服务器或 Run 中在线安装。"
        >
          <select required value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="">请选择…</option>
            {options?.sandbox_profiles.map((p) => (
              <option value={p.id} key={p.id}>
                {p.id} · {p.image_digest.slice(0, 19)}…
              </option>
            ))}
          </select>
        </Field>
        {runtime && (
          <Notice>
            已签名依赖环境：
            {runtime.manifest.packages.map((p) => `${p.name}==${p.version}`).join('、')}
            <br />
            环境摘要：<code>{runtime.manifest_digest}</code>
            <br />
            v2 能力包需固定此摘要及精确依赖版本；不支持 URL、版本范围、安装命令或覆盖宿主环境。
          </Notice>
        )}
        <div className="form-actions">
          <Button type="submit" busy={busy}>
            保存私有草稿
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function SkillInspector({
  id,
  onClose,
  onChange,
}: {
  id: string;
  onClose: () => void;
  onChange: () => void;
}) {
  const { me } = useAuth();
  const detail = useResource<SkillDetail>(`/api/v2/admin/skills/${id}`);
  const members = useResource<Page<Member>>('/api/v2/admin/members');
  const [reviewer, setReviewer] = useState('');
  const [note, setNote] = useState('');
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const row = detail.data;
  const validationReady =
    row?.validations[0]?.state === 'passed' && row.validations[0].cleanup_state === 'confirmed';
  useEffect(() => {
    if (row?.state !== 'validating') return;
    const timer = window.setInterval(detail.reload, 2500);
    return () => window.clearInterval(timer);
  }, [row?.state, detail.reload]);
  const candidates =
    members.data?.items.filter((m) => m.active && m.role === 'org_admin' && m.user_id !== row?.owner_id) ??
    [];
  async function submitValidation(event: FormEvent) {
    event.preventDefault();
    if (!row || !reviewer) return;
    setBusy(true);
    setError('');
    try {
      const body: SkillValidateRequest = { expected_revision: row.revision, reviewer_id: reviewer };
      await api.request(`/api/v2/admin/skills/${id}/validate`, 'POST', body);
      detail.reload();
      onChange();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  async function review(decision: 'approve' | 'reject') {
    if (!row || !note.trim() || (decision === 'approve' && !checked)) return;
    setBusy(true);
    setError('');
    try {
      const body: SkillReviewRequest = { expected_revision: row.revision, decision, note: note.trim() };
      await api.request(`/api/v2/admin/skills/${id}/review`, 'POST', body);
      detail.reload();
      onChange();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={row ? `${row.name} · v${row.version}` : 'Skill 包详情'}
      description="检查的是固定摘要对应的内容。静态检查与样例测试通过，不代表已证明所有行为安全。"
      onClose={onClose}
    >
      <ErrorBox message={error || detail.error || members.error} retry={detail.reload} />
      {!row ? (
        detail.loading && <Loading />
      ) : (
        <div className="form-stack">
          <div className="skill-inspector-head">
            <span className={`skill-state skill-state-${row.state}`}>{STATE[row.state]}</span>
            <Button variant="quiet" onClick={detail.reload}>
              <RefreshCw size={15} />
              刷新状态
            </Button>
          </div>
          <p>{row.package.description}</p>
          <dl className="skill-inspector-facts">
            <div>
              <dt>内容 SHA-256</dt>
              <dd className="mono">{row.digest}</dd>
            </div>
            <div>
              <dt>镜像</dt>
              <dd className="mono">{row.image_digest}</dd>
            </div>
            <div>
              <dt>来源 / 许可</dt>
              <dd>
                {row.package.source} / {row.package.license}
              </dd>
            </div>
          </dl>
          {row.package.schema_version === 2 && (
            <Notice>
              固定依赖：{row.package.dependencies.map((p) => `${p.name}==${p.version}`).join('、')}
              <br />
              环境摘要：<code>{row.package.runtime_manifest_digest}</code>
              <br />
              验证任务包含隔离环境核验；签名和样例通过不等于第三方包不存在漏洞。
            </Notice>
          )}
          <section className="skill-file-list">
            <h3>固定包内容</h3>
            {row.package.files.map((file) => (
              <details className="skill-source" key={file.path}>
                <summary>
                  <FileCode2 size={15} />
                  {file.path}
                  <small>
                    {formatBytes(row.file_manifest.find((f) => f.path === file.path)?.bytes ?? 0)}
                  </small>
                </summary>
                <pre>{file.content}</pre>
              </details>
            ))}
          </section>
          {!!row.package.entrypoints?.length && (
            <section>
              <h3>声明的 Python 入口</h3>
              {row.package.entrypoints.map((e) => (
                <div className="skill-entrypoint" key={e.name}>
                  <strong>{e.name}</strong>
                  <p>{e.description}</p>
                  <small>
                    {e.path} · 最长 {e.timeout_seconds ?? 10}s · {e.tests.length} 个合成测试
                  </small>
                  <details>
                    <summary>输入、输出与测试内容</summary>
                    <pre>
                      {JSON.stringify(
                        { input_schema: e.input_schema, output_schema: e.output_schema, tests: e.tests },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </div>
              ))}
            </section>
          )}
          <section className="skill-validation-log">
            <h3>隔离验证记录</h3>
            {!row.validations.length ? (
              <p className="muted">尚未发起验证。源文件未被执行。</p>
            ) : (
              row.validations.map((job) => (
                <article key={job.id}>
                  <header>
                    <strong>
                      {job.state === 'passed'
                        ? '检查与样例通过'
                        : job.state === 'failed'
                          ? '未通过验证'
                          : job.state === 'stopping'
                            ? '等待确认环境清理'
                            : job.state === 'queued'
                              ? '排队等待 Worker'
                              : '隔离验证运行中'}
                    </strong>
                    <small>
                      {formatDate(job.created_at)} · {shortId(job.id)}
                    </small>
                  </header>
                  <p>
                    已确认 {job.results.length} 个步骤 · 环境清理：
                    {job.cleanup_state === 'confirmed'
                      ? '已确认'
                      : job.cleanup_state === 'pending'
                        ? '未确认，禁止发布'
                        : '尚未分配环境'}
                  </p>
                  {job.error_code && <code>{job.error_code}</code>}
                </article>
              ))
            )}
          </section>
          {row.review_note && <Notice>最近审核意见：{row.review_note}</Notice>}
          {row.owner_id === me?.user_id && ['draft', 'rejected', 'validated'].includes(row.state) && (
            <form className="form-stack skill-review-form" onSubmit={submitValidation}>
              <h3>提交隔离验证与人工审核</h3>
              <Field
                label="指定另一位组织管理员"
                hint="指定审核人会获得这个包的读取授权；作者不能批准自己发布。"
              >
                <select required value={reviewer} onChange={(e) => setReviewer(e.target.value)}>
                  <option value="">请选择审核人…</option>
                  {candidates.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.display_name}
                    </option>
                  ))}
                </select>
              </Field>
              {!members.loading && !candidates.length && (
                <Notice>需要先配置另一位有效组织管理员，才能完成双人审核。</Notice>
              )}
              <Button type="submit" busy={busy} disabled={!reviewer || !me.capabilities.skill_publishing}>
                验证固定包并提交审核
              </Button>
            </form>
          )}
          {row.state === 'validated' &&
            validationReady &&
            row.reviewer_id === me?.user_id &&
            row.owner_id !== me.user_id && (
              <section className="skill-review-form form-stack">
                <h3>你的审核决定</h3>
                <Field label="审核意见">
                  <textarea
                    required
                    maxLength={1000}
                    rows={3}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </Field>
                <label className="check-row">
                  <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
                  我已核对这个版本的用途、源代码、输入输出、测试与无网络执行范围。
                </label>
                <div className="form-actions">
                  <Button
                    variant="secondary"
                    disabled={!note.trim() || busy}
                    onClick={() => void review('reject')}
                  >
                    拒绝发布
                  </Button>
                  <Button
                    busy={busy}
                    disabled={!checked || !note.trim()}
                    onClick={() => void review('approve')}
                  >
                    批准固定版本
                  </Button>
                </div>
              </section>
            )}
          {row.state === 'published' && (
            <Notice>
              这个版本可以绑定到 Agent。请通过 Agent 授权对话框显式授予模型、工具和 Skill 依赖；单独给 Skill
              使用权不会开放其包内容读取。
            </Notice>
          )}
        </div>
      )}
    </Modal>
  );
}
