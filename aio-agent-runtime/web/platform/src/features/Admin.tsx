import { useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { Bot, Building2, KeyRound, Pencil, Plus, Shield, SlidersHorizontal, Wrench, X } from 'lucide-react';
import { api, explain } from '../api/client';
import type {
  AdminOptions,
  ModelCreateRequest,
  AgentCreateRequest,
  ToolCreateRequest,
  Agent,
  AuditEvent,
  Budget,
  Department,
  Member,
  ModelConfig,
  Operation,
  OrganizationPolicy,
  Page,
  Role,
  Tool,
  SkillVersion,
  MCPServerVersion,
  KnowledgeBase,
} from '../api/types';
import { useAuth } from '../auth';
import { formatDate, shortId, useResource } from '../hooks';
import { money } from '../money';
import { GrantModal } from '../components/GrantModal';
import { Skills } from './Skills';
import { MCPAdmin } from './Connections';
import { EmbeddingAdmin } from './Embeddings';
import { SharedBudgets } from './SharedBudgets';
import { Badge, Button, Empty, ErrorBox, Field, Loading, Modal, Notice, PageTitle } from '../components/ui';

const ROLE_NAMES: Record<Role, string> = {
  member: '组织成员',
  org_admin: '组织管理员',
  operator: '平台运维',
  auditor: '安全审计',
};
function useAction(after?: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  return {
    busy,
    error,
    setError,
    async run(action: () => Promise<unknown>) {
      setBusy(true);
      setError('');
      try {
        await action();
        after?.();
        return true;
      } catch (error) {
        setError(explain(error));
        return false;
      } finally {
        setBusy(false);
      }
    },
  };
}
export function AdminPage() {
  const { me } = useAuth();
  const { section } = useParams();
  if (!me) return null;
  const tabs: Array<{ id: string; label: string; allowed: boolean }> = [
    { id: 'members', label: '成员与身份', allowed: me.permissions.organization_admin },
    { id: 'departments', label: '部门', allowed: me.permissions.organization_admin },
    { id: 'models', label: '模型', allowed: me.permissions.organization_admin },
    { id: 'tools', label: '工具', allowed: me.permissions.organization_admin },
    { id: 'skills', label: '共享 Skill', allowed: me.permissions.organization_admin },
    { id: 'mcp', label: 'MCP 服务', allowed: me.permissions.organization_admin },
    { id: 'embeddings', label: '嵌入模型', allowed: me.permissions.organization_admin },
    { id: 'agents', label: 'Agent', allowed: me.permissions.organization_admin },
    { id: 'budgets', label: '预算', allowed: me.permissions.organization_admin },
    { id: 'operations', label: '任务监控', allowed: me.permissions.operations },
    { id: 'audit', label: '审计', allowed: me.permissions.audit },
    { id: 'policy', label: '组织策略', allowed: me.permissions.organization_admin },
  ];
  const visible = tabs.filter((t) => t.allowed);
  const current = section ?? visible[0]?.id;
  if (!visible.some((t) => t.id === current))
    return (
      <div className="page">
        <ErrorBox message="你没有访问该管理页面的权限。" />
      </div>
    );
  return (
    <div className="page admin-page">
      <PageTitle
        eyebrow="ORGANIZATION CONTROL"
        title="管理中心"
        description="配置组织能力与明确授权。管理权限不会自动授予成员私人对话和文件的读取权。"
      />
      <nav className="admin-tabs" aria-label="管理功能">
        {visible.map((t) => (
          <NavLink to={`/app/admin/${t.id}`} key={t.id} className={current === t.id ? 'selected' : ''}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      {current === 'members' ? (
        <Members />
      ) : current === 'departments' ? (
        <Departments />
      ) : current === 'models' ? (
        <Models />
      ) : current === 'tools' ? (
        <Tools />
      ) : current === 'agents' ? (
        <Agents />
      ) : current === 'skills' ? (
        <Skills />
      ) : current === 'mcp' ? (
        <MCPAdmin />
      ) : current === 'embeddings' ? (
        <EmbeddingAdmin />
      ) : current === 'budgets' ? (
        <>
          <SharedBudgets />
          <Budgets />
        </>
      ) : current === 'operations' ? (
        <Operations />
      ) : current === 'audit' ? (
        <Audit />
      ) : (
        <Policy />
      )}
    </div>
  );
}
function Section({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="admin-section">
      <div className="section-top">
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Members() {
  const resource = useResource<Page<Member>>('/api/v2/admin/members');
  const action = useAction(resource.reload);
  const [edit, setEdit] = useState<Member | 'new' | null>(null);
  const [display, setDisplay] = useState('');
  const [subject, setSubject] = useState('');
  const [role, setRole] = useState<Role>('member');
  const [active, setActive] = useState(true);
  function open(member: Member | 'new') {
    setEdit(member);
    setDisplay(member === 'new' ? '' : member.display_name);
    setSubject(member === 'new' ? '' : member.subject);
    setRole(member === 'new' ? 'member' : member.role);
    setActive(member === 'new' || member.active);
    action.setError('');
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!edit) return;
    const ok = await action.run(() =>
      edit === 'new'
        ? api.request('/api/v2/admin/members', 'POST', { subject, display_name: display, role })
        : api.request(`/api/v2/admin/members/${edit.user_id}`, 'PATCH', {
            expected_revision: edit.revision,
            display_name: display,
            role,
            active,
          }),
    );
    if (ok) setEdit(null);
  }
  return (
    <Section
      title="成员与身份"
      description="先登记企业身份，再分配部门、预算和可用能力。新成员不会自动获得全组织权限。"
      action={
        <Button onClick={() => open('new')}>
          <Plus size={16} />
          登记成员
        </Button>
      }
    >
      <ErrorBox message={resource.error} retry={resource.reload} />
      {resource.loading ? (
        <Loading />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>成员</th>
                <th>企业身份 Subject</th>
                <th>角色</th>
                <th>状态</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {resource.data?.items.map((m) => (
                <tr key={m.user_id}>
                  <td>
                    <div className="person-cell">
                      <span className="avatar">{m.display_name.slice(0, 1)}</span>
                      <strong>{m.display_name}</strong>
                    </div>
                  </td>
                  <td className="mono truncate-cell">{m.subject}</td>
                  <td>{ROLE_NAMES[m.role]}</td>
                  <td>
                    <Badge state={m.active ? 'active' : 'disabled'} />
                  </td>
                  <td>
                    <Button variant="quiet" onClick={() => open(m)}>
                      <Pencil size={14} />
                      编辑
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {edit && (
        <Modal title={edit === 'new' ? '登记企业成员' : '编辑组织成员'} onClose={() => setEdit(null)}>
          <form onSubmit={save} className="form-stack">
            <ErrorBox message={action.error} />
            <Field label="显示名称">
              <input required maxLength={100} value={display} onChange={(e) => setDisplay(e.target.value)} />
            </Field>
            {edit === 'new' && (
              <Field label="企业身份 Subject" hint="填写当前身份提供方中的稳定用户标识，不是密码。">
                <input
                  required
                  maxLength={255}
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                />
              </Field>
            )}
            <Field label="组织角色">
              <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {Object.entries(ROLE_NAMES).map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
            </Field>
            {edit !== 'new' && (
              <label className="check-row">
                <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
                成员可以登录并使用已授权能力
              </label>
            )}
            <p className="small-note">
              停用会撤销浏览器会话并阻止任务后续调用。最后一名有效组织管理员不能被移除。
            </p>
            <div className="form-actions">
              <Button type="submit" busy={action.busy}>
                保存成员
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}
function Departments() {
  const depts = useResource<Page<Department>>('/api/v2/admin/departments');
  const members = useResource<Page<Member>>('/api/v2/admin/members');
  const action = useAction(depts.reload);
  const [create, setCreate] = useState(false);
  const [name, setName] = useState('');
  const [selected, setSelected] = useState<Department | null>(null);
  const [memberId, setMember] = useState('');
  async function createDept(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.request('/api/v2/admin/departments', 'POST', { name }))) {
      setCreate(false);
      setName('');
    }
  }
  async function add(e: FormEvent) {
    e.preventDefault();
    if (!selected) return;
    if (
      await action.run(() =>
        api.request(`/api/v2/admin/departments/${selected.id}/members`, 'PUT', {
          user_id: memberId,
          role: 'member',
        }),
      )
    )
      setSelected(null);
  }
  return (
    <Section
      title="部门空间"
      description="同一个人可以加入多个部门。能力授予部门后，成员变更会影响下一次访问和工具调用。"
      action={
        <Button
          onClick={() => {
            setCreate(true);
            action.setError('');
          }}
        >
          <Plus size={16} />
          新增部门
        </Button>
      }
    >
      <ErrorBox
        message={depts.error || members.error || (!create && !selected ? action.error : '')}
        retry={depts.reload}
      />
      {depts.loading ? (
        <Loading />
      ) : !depts.data?.items.length ? (
        <Empty title="尚未建立部门">可以先创建销售、财务或业务项目对应的部门范围。</Empty>
      ) : (
        <div className="department-grid">
          {depts.data.items.map((d) => (
            <article className="department-card" key={d.id}>
              <header>
                <span className="department-icon">
                  <Building2 size={20} />
                </span>
                <div>
                  <h3>{d.name}</h3>
                  <small>{d.members.length} 位成员</small>
                </div>
                <Badge state={d.active ? 'active' : 'disabled'} />
              </header>
              <ul>
                {d.members.map((m) => (
                  <li key={m.user_id}>
                    <span className="mini-avatar">{m.display_name.slice(0, 1)}</span>
                    <span>{m.display_name}</span>
                    <button
                      className="icon-button"
                      aria-label={`从 ${d.name} 移除 ${m.display_name}`}
                      disabled={action.busy}
                      onClick={() =>
                        void action.run(() =>
                          api.request(`/api/v2/admin/departments/${d.id}/members/${m.user_id}`, 'DELETE'),
                        )
                      }
                    >
                      <X size={14} />
                    </button>
                  </li>
                ))}
              </ul>
              <footer>
                <Button
                  variant="quiet"
                  disabled={!d.active}
                  onClick={() => {
                    setSelected(d);
                    setMember('');
                    action.setError('');
                  }}
                >
                  <Plus size={14} />
                  添加成员
                </Button>
                <Button
                  variant="quiet"
                  busy={action.busy}
                  onClick={() =>
                    void action.run(() =>
                      api.request(`/api/v2/admin/departments/${d.id}`, 'PATCH', { active: !d.active }),
                    )
                  }
                >
                  {d.active ? '停用部门' : '重新启用'}
                </Button>
              </footer>
            </article>
          ))}
        </div>
      )}
      {create && (
        <Modal title="新增部门" onClose={() => setCreate(false)}>
          <form onSubmit={createDept} className="form-stack">
            <ErrorBox message={action.error} />
            <Field label="部门名称">
              <input required value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
            </Field>
            <div className="form-actions">
              <Button type="submit" busy={action.busy}>
                创建部门
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {selected && (
        <Modal title={`添加成员 · ${selected.name}`} onClose={() => setSelected(null)}>
          <form onSubmit={add} className="form-stack">
            <ErrorBox message={action.error} />
            <Field label="组织成员">
              <select value={memberId} required onChange={(e) => setMember(e.target.value)}>
                <option value="">请选择…</option>
                {members.data?.items
                  .filter((m) => m.active && !selected.members.some((x) => x.user_id === m.user_id))
                  .map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.display_name}
                    </option>
                  ))}
              </select>
            </Field>
            <div className="form-actions">
              <Button type="submit" busy={action.busy} disabled={!memberId}>
                添加成员
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}
function ResourceActions({
  id,
  name,
  status,
  revision,
  onChange,
}: {
  id: string;
  name: string;
  status: string;
  revision: number;
  onChange: () => void;
}) {
  const [share, setShare] = useState(false);
  const action = useAction(onChange);
  const [confirm, setConfirm] = useState(false);
  async function toggle() {
    if (
      await action.run(() =>
        api.request(`/api/v2/resources/${id}/status`, 'PATCH', {
          expected_revision: revision,
          status: status === 'active' ? 'disabled' : 'active',
        }),
      )
    )
      setConfirm(false);
  }
  return (
    <>
      <div className="row-actions">
        <Button variant="quiet" onClick={() => setShare(true)}>
          <KeyRound size={14} />
          授权
        </Button>
        <Button variant="quiet" onClick={() => setConfirm(true)}>
          {status === 'active' ? '停用' : '启用'}
        </Button>
      </div>
      {share && (
        <GrantModal
          id={id}
          name={name}
          onClose={() => {
            setShare(false);
            onChange();
          }}
        />
      )}
      {confirm && (
        <Modal
          title={`${status === 'active' ? '停用' : '启用'} · ${name}`}
          description="发布内容不可变。此操作改变新访问与后续调用的可用性，不会撤销已经发生的业务操作。"
          onClose={() => setConfirm(false)}
        >
          <ErrorBox message={action.error} />
          <div className="form-actions">
            <Button variant="secondary" onClick={() => setConfirm(false)}>
              取消
            </Button>
            <Button
              variant={status === 'active' ? 'danger' : 'primary'}
              busy={action.busy}
              onClick={() => void toggle()}
            >
              确认{status === 'active' ? '停用' : '启用'}
            </Button>
          </div>
        </Modal>
      )}
    </>
  );
}
function Models() {
  const models = useResource<Page<ModelConfig>>('/api/v2/admin/models');
  const options = useResource<AdminOptions>('/api/v2/admin/options');
  const action = useAction(models.reload);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    provider: 'company',
    model: '',
    endpoint: '',
    secret_env: '',
    max_output_tokens: 2048,
    max_call_charge: '0.02',
    input_price_per_million: '0',
    output_price_per_million: '0',
    max_tokens_field: 'max_tokens',
  });
  async function save(e: FormEvent) {
    e.preventDefault();
    if (
      await action.run(() =>
        api.request('/api/v2/admin/models', 'POST', {
          ...form,
          max_tokens_field: form.max_tokens_field as ModelCreateRequest['max_tokens_field'],
        } satisfies ModelCreateRequest),
      )
    )
      setOpen(false);
  }
  return (
    <Section
      title="模型版本"
      description="仅引用部署侧已允许的端点和密钥变量。不在网页中保存或回显 API Key。"
      action={
        <Button
          disabled={!options.data?.model_allowed_origins.length || !options.data?.model_secret_names.length}
          onClick={() => {
            setOpen(true);
            action.setError('');
            setForm((f) => ({
              ...f,
              endpoint: (options.data?.model_allowed_origins[0] ?? '') + '/v1/chat/completions',
              secret_env: options.data?.model_secret_names[0] ?? '',
            }));
          }}
        >
          <Plus size={16} />
          登记模型
        </Button>
      }
    >
      <ErrorBox message={models.error || options.error} retry={models.reload} />
      {options.data &&
        (!options.data.model_allowed_origins.length || !options.data.model_secret_names.length) && (
          <Notice>部署管理员尚未设置模型端点／密钥引用白名单。配置后才能从此处登记模型。</Notice>
        )}
      {models.loading ? (
        <Loading />
      ) : !models.data?.items.length ? (
        <Empty title="还没有已登记模型">先配置部署白名单，再创建一个不可变模型版本。</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>模型</th>
                <th>Provider / 版本</th>
                <th>单次预留上限</th>
                <th>状态</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {models.data.items.map((m) => (
                <tr key={m.id}>
                  <td>
                    <strong>{m.config.name ?? m.model}</strong>
                    <small className="block muted mono">{m.config.endpoint}</small>
                  </td>
                  <td>
                    {m.provider}
                    <small className="block mono">{m.model}</small>
                  </td>
                  <td className="mono">USD {m.config.max_call_charge ?? '—'}</td>
                  <td>
                    <Badge state={m.status} />
                  </td>
                  <td>
                    <ResourceActions
                      id={m.id}
                      name={m.config.name ?? m.model}
                      status={m.status}
                      revision={m.revision}
                      onChange={models.reload}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && (
        <Modal
          title="登记新的模型版本"
          onClose={() => setOpen(false)}
          description="配置内容不可变。需要修改时创建新版本，再更新 Agent 引用。"
        >
          <form className="form-stack" onSubmit={save}>
            <ErrorBox message={action.error} />
            <div className="form-grid">
              <Field label="显示名称">
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Provider 标识">
                <input
                  required
                  pattern="[A-Za-z0-9_-]+"
                  value={form.provider}
                  onChange={(e) => setForm({ ...form, provider: e.target.value })}
                />
              </Field>
            </div>
            <Field label="模型 ID">
              <input
                required
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
              />
            </Field>
            <Field
              label="Chat Completions 完整地址"
              hint={`允许来源：${options.data?.model_allowed_origins.join('、')}`}
            >
              <input
                required
                type="url"
                value={form.endpoint}
                onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
              />
            </Field>
            <Field label="已批准密钥引用">
              <select
                required
                value={form.secret_env}
                onChange={(e) => setForm({ ...form, secret_env: e.target.value })}
              >
                {options.data?.model_secret_names.map((name) => (
                  <option value={name} key={name}>
                    {name}
                  </option>
                ))}
              </select>
            </Field>
            <div className="form-grid">
              <Field label="最大输出 Tokens">
                <input
                  type="number"
                  required
                  min={1}
                  max={32768}
                  value={form.max_output_tokens}
                  onChange={(e) => setForm({ ...form, max_output_tokens: Number(e.target.value) })}
                />
              </Field>
              <Field label="单次费用预留上限（USD）">
                <input
                  type="number"
                  required
                  min="0.000001"
                  max="100"
                  step="0.000001"
                  value={form.max_call_charge}
                  onChange={(e) => setForm({ ...form, max_call_charge: e.target.value })}
                />
              </Field>
              <Field label="输入单价 / 百万 Tokens">
                <input
                  type="number"
                  required
                  min="0"
                  step="0.000001"
                  value={form.input_price_per_million}
                  onChange={(e) => setForm({ ...form, input_price_per_million: e.target.value })}
                />
              </Field>
              <Field label="输出单价 / 百万 Tokens">
                <input
                  type="number"
                  required
                  min="0"
                  step="0.000001"
                  value={form.output_price_per_million}
                  onChange={(e) => setForm({ ...form, output_price_per_million: e.target.value })}
                />
              </Field>
            </div>
            <Field label="供应商 Token 限制字段">
              <select
                value={form.max_tokens_field}
                onChange={(e) => setForm({ ...form, max_tokens_field: e.target.value })}
              >
                <option>max_tokens</option>
                <option>max_completion_tokens</option>
              </select>
            </Field>
            <div className="form-actions">
              <Button type="submit" busy={action.busy}>
                创建模型版本
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}
function Tools() {
  const tools = useResource<Page<Tool>>('/api/v2/admin/tools');
  const options = useResource<AdminOptions>('/api/v2/admin/options');
  const action = useAction(tools.reload);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: 'python_compute',
    description: '在独立、无网络的 Python 工作区中分析文件并生成结果。',
    sandbox_profile: '',
    timeout_seconds: 60,
  });
  async function save(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.request('/api/v2/admin/tools', 'POST', form satisfies ToolCreateRequest)))
      setOpen(false);
  }
  return (
    <Section
      title="已批准工具"
      description="当前管理入口仅发布真实已实现的无网络 Python 工具。不会提供任意宿主命令、Docker 参数或业务凭据输入框。"
      action={
        <Button
          disabled={!options.data?.sandbox_profiles.length}
          onClick={() => {
            setOpen(true);
            action.setError('');
            setForm((f) => ({ ...f, sandbox_profile: options.data?.sandbox_profiles[0]?.id ?? '' }));
          }}
        >
          <Plus size={16} />
          配置计算工具
        </Button>
      }
    >
      <ErrorBox message={tools.error || options.error} retry={tools.reload} />
      {options.data && !options.data.sandbox_profiles.length && (
        <Notice>请先由部署管理员提供已验证的执行 Profile 与固定镜像摘要。</Notice>
      )}
      {tools.loading ? (
        <Loading />
      ) : !tools.data?.items.length ? (
        <Empty title="尚无计算工具">配置后还需要向使用者授予工具权限，并加入 Agent 版本。</Empty>
      ) : (
        <div className="tool-grid">
          {tools.data.items.map((t) => (
            <article key={t.id} className="tool-card">
              <div className="tool-title">
                <span>
                  <Wrench size={19} />
                </span>
                <div>
                  <h3>{t.name}</h3>
                  <small className="mono">
                    {t.driver} · {t.risk}
                  </small>
                </div>
                <Badge state={t.status ?? 'active'} />
              </div>
              <p>{t.config?.description ?? '已登记工具版本'}</p>
              <dl>
                <div>
                  <dt>隔离 Profile</dt>
                  <dd>{t.config?.sandbox_profile ?? '—'}</dd>
                </div>
                <div>
                  <dt>最长执行</dt>
                  <dd>{t.config?.timeout_seconds ?? '—'} 秒</dd>
                </div>
              </dl>
              <ResourceActions
                id={t.id}
                name={t.name}
                status={t.status ?? 'active'}
                revision={t.revision ?? 0}
                onChange={tools.reload}
              />
            </article>
          ))}
        </div>
      )}
      {open && (
        <Modal title="配置 Python 计算工具" onClose={() => setOpen(false)}>
          <form onSubmit={save} className="form-stack">
            <ErrorBox message={action.error} />
            <Field label="工具别名">
              <input
                required
                pattern="[A-Za-z][A-Za-z0-9_-]*"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="使用说明">
              <textarea
                required
                rows={3}
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
              />
            </Field>
            <Field label="部署批准的 Profile">
              <select
                required
                value={form.sandbox_profile}
                onChange={(e) => setForm({ ...form, sandbox_profile: e.target.value })}
              >
                {options.data?.sandbox_profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.id} · 最长 {p.max_timeout_seconds} 秒
                  </option>
                ))}
              </select>
            </Field>
            <Field label="工具执行上限（秒）">
              <input
                type="number"
                min={1}
                max={300}
                required
                value={form.timeout_seconds}
                onChange={(e) => setForm({ ...form, timeout_seconds: Number(e.target.value) })}
              />
            </Field>
            <Notice>镜像、无网络策略和系统权限由部署 Profile 决定，Agent 不能覆盖。</Notice>
            <div className="form-actions">
              <Button type="submit" busy={action.busy}>
                发布工具版本
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}
function Agents() {
  const { me } = useAuth();
  const agents = useResource<Page<Agent>>('/api/v2/admin/agents');
  const models = useResource<Page<ModelConfig>>('/api/v2/admin/models');
  const tools = useResource<Page<Tool>>('/api/v2/admin/tools');
  const skills = useResource<Page<SkillVersion>>('/api/v2/skills');
  const mcpServers = useResource<Page<MCPServerVersion>>(me?.capabilities.mcp ? '/api/v2/mcp/servers' : null);
  const knowledge = useResource<Page<KnowledgeBase>>(me?.capabilities.knowledge ? '/api/v2/knowledge' : null);
  const action = useAction(agents.reload);
  const [open, setOpen] = useState(false);
  const [teamEnabled, setTeamEnabled] = useState(false);
  const [teamSteps, setTeamSteps] = useState(2);
  const [teamRounds, setTeamRounds] = useState(3);
  const [form, setForm] = useState({
    name: '',
    version: '1',
    instruction: '你是企业工作助手。仅使用已授权的工具处理当前项目资料；明确说明不确定性，输出可核对的结果。',
    model_id: '',
    tool_ids: [] as string[],
    skill_ids: [] as string[],
    mcp_server_ids: [] as string[],
    knowledge_ids: [] as string[],
    run_budget: '0.10',
    max_rounds: 8,
  });
  async function save(e: FormEvent) {
    e.preventDefault();
    if (
      await action.run(() =>
        api.request('/api/v2/admin/agents', 'POST', {
          ...form,
          team: teamEnabled ? { max_steps: teamSteps, max_step_rounds: teamRounds } : null,
        } satisfies AgentCreateRequest),
      )
    )
      setOpen(false);
  }
  const availableModels = models.data?.items.filter((m) => m.status === 'active') ?? [];
  const availableTools =
    tools.data?.items.filter(
      (t) =>
        t.status === 'active' &&
        !t.driver.startsWith('skill.') &&
        !['mcp.http', 'mcp.stdio', 'knowledge.search'].includes(t.driver),
    ) ?? [];
  return (
    <Section
      title="Agent 发布版本"
      description="将模型、工具与任务指令组合成员工可以直接选择的 Agent。发布后内容固定，权限和可用状态独立管理。"
      action={
        <Button
          disabled={!availableModels.length}
          onClick={() => {
            setOpen(true);
            action.setError('');
            setForm((f) => ({ ...f, model_id: availableModels[0]?.id ?? '' }));
          }}
        >
          <Plus size={16} />
          新建 Agent
        </Button>
      }
    >
      <ErrorBox message={agents.error || models.error || tools.error || skills.error} retry={agents.reload} />
      {!models.loading && !availableModels.length && <Notice>先登记一个可用模型，再创建 Agent 版本。</Notice>}
      {agents.loading ? (
        <Loading />
      ) : !agents.data?.items.length ? (
        <Empty title="准备你的第一个 Agent">建议从一个具体业务任务开始，配置少量已验证的工具。</Empty>
      ) : (
        <div className="agent-admin-grid">
          {agents.data.items.map((agent) => (
            <article className="agent-admin-card" key={agent.id}>
              <header>
                <span className="agent-glyph">
                  <Bot size={23} />
                </span>
                <div>
                  <h3>{agent.name}</h3>
                  <small>版本 {agent.version}</small>
                </div>
                <Badge state={agent.status ?? 'active'} />
              </header>
              <p>{agent.instruction?.slice(0, 180) ?? '已发布任务模板'}</p>
              <div className="agent-meta">
                <span>{agent.manifest?.tools.length ?? 0} 个工具</span>
                <span>{agent.manifest?.skills?.length ?? 0} 个 Skill</span>
                <span>最多 {agent.manifest?.max_rounds ?? '—'} 轮</span>
                <span>预算 ${agent.manifest?.run_budget ?? '—'}</span>
                {agent.manifest?.team && <span>多步骤 · 最多 {agent.manifest.team.max_steps} 步</span>}
              </div>
              <ResourceActions
                id={agent.id}
                name={agent.name}
                status={agent.status ?? 'active'}
                revision={agent.revision ?? 0}
                onChange={agents.reload}
              />
            </article>
          ))}
        </div>
      )}
      {open && (
        <Modal
          title="发布 Agent 版本"
          onClose={() => setOpen(false)}
          description="此表单不会授予新的底层权限。员工使用前仍需要获得 Agent 及其依赖的模型、工具授权。"
        >
          <form className="form-stack" onSubmit={save}>
            <ErrorBox message={action.error} />
            <div className="form-grid">
              <Field label="Agent 名称">
                <input
                  required
                  maxLength={100}
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="版本标识">
                <input
                  required
                  maxLength={64}
                  value={form.version}
                  onChange={(e) => setForm({ ...form, version: e.target.value })}
                />
              </Field>
            </div>
            <Field label="任务指令">
              <textarea
                required
                rows={6}
                maxLength={32768}
                value={form.instruction}
                onChange={(e) => setForm({ ...form, instruction: e.target.value })}
              />
            </Field>
            <Field label="模型版本">
              <select
                required
                value={form.model_id}
                onChange={(e) => setForm({ ...form, model_id: e.target.value })}
              >
                <option value="">请选择…</option>
                {availableModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.config.name ?? m.model} · {m.model}
                  </option>
                ))}
              </select>
            </Field>
            <fieldset className="check-fieldset">
              <legend>允许使用的工具</legend>
              {availableTools.length ? (
                availableTools.map((t) => (
                  <label className="check-row" key={t.id}>
                    <input
                      type="checkbox"
                      checked={form.tool_ids.includes(t.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          tool_ids: e.target.checked
                            ? [...form.tool_ids, t.id]
                            : form.tool_ids.filter((id) => id !== t.id),
                        })
                      }
                    />
                    {t.name}
                    <small>{t.driver}</small>
                  </label>
                ))
              ) : (
                <small className="muted">没有可用工具，Agent 仅可进行模型对话。</small>
              )}
            </fieldset>
            <fieldset className="check-fieldset">
              <legend>固定 Skill 版本</legend>
              {skills.data?.items.length ? (
                skills.data.items.map((skill) => (
                  <label className="check-row" key={skill.id}>
                    <input
                      type="checkbox"
                      checked={form.skill_ids.includes(skill.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          skill_ids: e.target.checked
                            ? [...form.skill_ids, skill.id]
                            : form.skill_ids.filter((id) => id !== skill.id),
                        })
                      }
                    />
                    {skill.name} · v{skill.version}
                    <small>{skill.published_tools.length} 个关联工具</small>
                  </label>
                ))
              ) : (
                <small className="muted">暂无已获权的发布版本。可在共享 Skill 页创建并提交双人审核。</small>
              )}
              <small className="muted">
                选择 Skill 会固定其说明和已发布工具；使用前仍需显式授予依赖权限。
              </small>
            </fieldset>
            {me?.capabilities.mcp && (
              <fieldset className="check-fieldset">
                <legend>固定 MCP 服务版本</legend>
                <ErrorBox message={mcpServers.error} retry={mcpServers.reload} />
                {mcpServers.data?.items.map((server) => (
                  <label className="check-row" key={server.id}>
                    <input
                      type="checkbox"
                      checked={form.mcp_server_ids.includes(server.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          mcp_server_ids: e.target.checked
                            ? [...form.mcp_server_ids, server.id]
                            : form.mcp_server_ids.filter((id) => id !== server.id),
                        })
                      }
                    />
                    {server.name} · v{server.version}
                    <small>{server.published_tools.length} 个工具</small>
                  </label>
                ))}
                <small className="muted">这里只固定工具定义，不会把你的个人连接借给其他使用者。</small>
              </fieldset>
            )}
            {me?.capabilities.knowledge && (
              <fieldset className="check-fieldset">
                <legend>授权知识库</legend>
                <ErrorBox message={knowledge.error} retry={knowledge.reload} />
                {knowledge.data?.items.map((kb) => (
                  <label key={kb.id} className="check-row">
                    <input
                      type="checkbox"
                      checked={form.knowledge_ids.includes(kb.id)}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          knowledge_ids: e.target.checked
                            ? [...form.knowledge_ids, kb.id]
                            : form.knowledge_ids.filter((id) => id !== kb.id),
                        })
                      }
                    />
                    {kb.name}
                    <small>{kb.embedding_model_id ? '混合检索' : '中文关键词'}</small>
                  </label>
                ))}
                <small className="muted">文档权限独立检查；知识库分享不会公开仍然受限的文档。</small>
              </fieldset>
            )}
            <div className="form-grid">
              <Field label="每次任务预算（USD）">
                <input
                  required
                  type="number"
                  min="0.000001"
                  max="100"
                  step="0.000001"
                  value={form.run_budget}
                  onChange={(e) => setForm({ ...form, run_budget: e.target.value })}
                />
              </Field>
              <Field label="最大模型轮次">
                <input
                  required
                  type="number"
                  min={teamEnabled ? teamSteps + 2 : 1}
                  max={32}
                  value={form.max_rounds}
                  onChange={(e) => setForm({ ...form, max_rounds: Number(e.target.value) })}
                />
              </Field>
            </div>
            {me?.capabilities.team && (
              <fieldset className="check-fieldset">
                <legend>多步骤协作</legend>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={teamEnabled}
                    onChange={(e) => setTeamEnabled(e.target.checked)}
                  />
                  启用多步骤协作（Team）
                </label>
                {teamEnabled && (
                  <>
                    <div className="form-grid">
                      <Field label="最多任务步骤">
                        <input
                          type="number"
                          required
                          min={1}
                          max={6}
                          value={teamSteps}
                          onChange={(e) => setTeamSteps(Number(e.target.value))}
                        />
                      </Field>
                      <Field label="每步最多模型轮次">
                        <input
                          type="number"
                          required
                          min={1}
                          max={16}
                          value={teamRounds}
                          onChange={(e) => setTeamRounds(Number(e.target.value))}
                        />
                      </Field>
                    </div>
                    <small className="muted">
                      规划与汇总也计入全局轮数、费用和截止时间。全局至少需 {teamSteps + 2}{' '}
                      轮；预算至少覆盖这些模型调用。步骤不能增加模型、工具或借用其他身份。
                    </small>
                  </>
                )}
              </fieldset>
            )}
            <div className="form-actions">
              <Button busy={action.busy} type="submit">
                发布这个版本
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}
function Budgets() {
  const budgets = useResource<Page<Budget>>('/api/v2/admin/budgets');
  const members = useResource<Page<Member>>('/api/v2/admin/members');
  const action = useAction(budgets.reload);
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState('');
  const [limit, setLimit] = useState('10');
  async function save(e: FormEvent) {
    e.preventDefault();
    if (await action.run(() => api.request(`/api/v2/admin/budgets/${user}`, 'PUT', { hard_limit: limit })))
      setOpen(false);
  }
  return (
    <Section
      title="成员任务预算"
      description="个人额度与组织／部门附加上限同时约束任务。已消费和已预留金额不能被调低额度的操作抹掉。"
      action={
        <Button
          onClick={() => {
            setOpen(true);
            setUser('');
            setLimit('10');
            action.setError('');
          }}
        >
          <Plus size={16} />
          分配预算
        </Button>
      }
    >
      <ErrorBox message={budgets.error || members.error} retry={budgets.reload} />
      {budgets.loading ? (
        <Loading />
      ) : !budgets.data?.items.length ? (
        <Empty title="尚无任务预算">向已登记的成员分配额度后，他们才可以发起模型任务。</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>成员</th>
                <th>总额度</th>
                <th>已记账</th>
                <th>任务预留</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {budgets.data.items.map((b) => (
                <tr key={b.id}>
                  <td>
                    <strong>{b.display_name}</strong>
                  </td>
                  <td className="mono">
                    {b.currency} {money(b.hard_limit)}
                  </td>
                  <td className="mono">{money(b.consumed)}</td>
                  <td className="mono">{money(b.reserved)}</td>
                  <td>
                    <Button
                      variant="quiet"
                      onClick={() => {
                        setUser(b.owner_id);
                        setLimit(b.hard_limit);
                        setOpen(true);
                        action.setError('');
                      }}
                    >
                      <Pencil size={14} />
                      调整额度
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open && (
        <Modal title="设置成员预算" onClose={() => setOpen(false)}>
          <form className="form-stack" onSubmit={save}>
            <ErrorBox message={action.error} />
            <Field label="成员">
              <select required value={user} onChange={(e) => setUser(e.target.value)}>
                <option value="">请选择…</option>
                {members.data?.items
                  .filter((m) => m.active)
                  .map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.display_name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="总额度（USD）">
              <input
                type="number"
                required
                min="0.000001"
                step="0.000001"
                max="1000000"
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
              />
            </Field>
            <p className="small-note">这是额度上限，不是充值交易。实际账单与未知费用需要按供应商记录核对。</p>
            <div className="form-actions">
              <Button busy={action.busy} type="submit">
                保存额度
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}
function Operations() {
  const runs = useResource<Page<Operation>>('/api/v2/admin/runs');
  const action = useAction(runs.reload);
  const [stop, setStop] = useState<Operation | null>(null);
  const terminal = new Set(['succeeded', 'failed', 'cancelled', 'timed_out', 'recovery_required']);
  async function confirm() {
    if (stop && (await action.run(() => api.request(`/api/v2/admin/runs/${stop.id}/stop`, 'POST'))))
      setStop(null);
  }
  return (
    <Section
      title="任务监控"
      description="只显示运行元数据，不打开私人对话、文件或模型原始输入。停止任务不等于撤销已发生的外部操作。"
      action={
        <Button variant="secondary" onClick={runs.reload}>
          刷新状态
        </Button>
      }
    >
      <ErrorBox message={runs.error} retry={runs.reload} />
      {runs.loading ? (
        <Loading />
      ) : !runs.data?.items.length ? (
        <Empty title="还没有任务记录">员工发起任务后，这里会显示其状态与资源回收情况。</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>资源状态</th>
                <th>时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.data.items.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong className="mono">{shortId(r.id)}</strong>
                    <small className="block muted">
                      执行代次 {r.generation} · 用户 {shortId(r.actor_id)}
                    </small>
                    {r.error_code && <code className="small-code">{r.error_code}</code>}
                  </td>
                  <td>
                    <Badge state={r.state} />
                  </td>
                  <td>
                    {r.cleanup_state === 'clean'
                      ? '已回收'
                      : r.cleanup_state === 'not_allocated'
                        ? '未分配'
                        : r.cleanup_state}
                  </td>
                  <td>{formatDate(r.created_at)}</td>
                  <td>
                    {!terminal.has(r.state) && (
                      <Button
                        variant="quiet"
                        onClick={() => {
                          setStop(r);
                          action.setError('');
                        }}
                      >
                        请求停止
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {stop && (
        <Modal title="请求停止这次任务？" onClose={() => setStop(null)}>
          <p>
            任务 {shortId(stop.id)} 会停止后续调用并进入回收／核对流程。已发生的业务影响不能通过这个按钮撤销。
          </p>
          <ErrorBox message={action.error} />
          <div className="form-actions">
            <Button variant="secondary" onClick={() => setStop(null)}>
              返回
            </Button>
            <Button variant="danger" busy={action.busy} onClick={() => void confirm()}>
              确认停止
            </Button>
          </div>
        </Modal>
      )}
    </Section>
  );
}
function Audit() {
  const data = useResource<Page<AuditEvent>>('/api/v2/admin/audit');
  return (
    <Section
      title="审计记录"
      description="追踪谁对什么资源进行了操作。此页面不回显工具原始参数、文件正文或凭据。"
      action={
        <Button variant="secondary" onClick={data.reload}>
          刷新记录
        </Button>
      }
    >
      <ErrorBox message={data.error} retry={data.reload} />
      {data.loading ? (
        <Loading />
      ) : !data.data?.items.length ? (
        <Empty title="尚无审计记录">管理与任务操作发生后会记录在这里。</Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>操作</th>
                <th>操作者</th>
                <th>资源</th>
                <th>结果</th>
              </tr>
            </thead>
            <tbody>
              {data.data.items.map((e) => (
                <tr key={e.id}>
                  <td>{formatDate(e.created_at)}</td>
                  <td>
                    <code>{e.action}</code>
                  </td>
                  <td className="mono">{shortId(e.actor_id)}</td>
                  <td className="mono">{e.resource_id ? shortId(e.resource_id) : '—'}</td>
                  <td>{e.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
function Policy() {
  const resource = useResource<OrganizationPolicy>('/api/v2/admin/policy');
  const action = useAction(resource.reload);
  const [edit, setEdit] = useState(false);
  const [allowed, setAllowed] = useState<string[]>([]);
  const [denied, setDenied] = useState<string[]>([]);
  const [storage, setStorage] = useState('1');
  const actions: { id: string; label: string }[] = [
    { id: 'project.create', label: '新建项目' },
    { id: 'project.write', label: '在项目中执行任务' },
    { id: 'agent.use', label: '使用 Agent' },
    { id: 'model.use', label: '调用模型' },
    { id: 'tool.use', label: '调用工具' },
    { id: 'artifact.download', label: '下载文件' },
  ];
  function open() {
    if (!resource.data) return;
    setAllowed(resource.data.allowed_classifications);
    setDenied(resource.data.denied_actions);
    setStorage(String(resource.data.storage_limit_bytes / 1024 ** 3));
    setEdit(true);
    action.setError('');
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (!resource.data) return;
    if (
      await action.run(() =>
        api.request('/api/v2/admin/policy', 'PUT', {
          expected_revision: resource.data!.policy_revision,
          allowed_classifications: allowed,
          denied_actions: denied,
          storage_limit_bytes: Math.round(Number(storage) * 1024 ** 3),
        }),
      )
    )
      setEdit(false);
  }
  return (
    <Section
      title="组织策略"
      description="组织限制优先于成员和部门授权。修改会影响当前任务的下一次权限检查。"
      action={
        <Button variant="secondary" disabled={!resource.data} onClick={open}>
          <SlidersHorizontal size={15} />
          编辑策略
        </Button>
      }
    >
      <ErrorBox message={resource.error} retry={resource.reload} />
      {resource.loading ? (
        <Loading />
      ) : (
        resource.data && (
          <div className="policy-summary">
            <div>
              <Shield size={24} />
              <h3>{resource.data.name}</h3>
              <small>策略版本 {resource.data.policy_revision}</small>
            </div>
            <dl>
              <div>
                <dt>可处理数据级别</dt>
                <dd>{resource.data.allowed_classifications.join(' / ')}</dd>
              </div>
              <div>
                <dt>额外禁止动作</dt>
                <dd>
                  {resource.data.denied_actions.length
                    ? resource.data.denied_actions.join('、')
                    : '未额外禁止；每次操作仍需要资源授权'}
                </dd>
              </div>
              <div>
                <dt>组织存储上限</dt>
                <dd>{(resource.data.storage_limit_bytes / 1024 ** 3).toFixed(2)} GiB</dd>
              </div>
            </dl>
          </div>
        )
      )}
      {edit && (
        <Modal title="修改组织策略" onClose={() => setEdit(false)}>
          <form className="form-stack" onSubmit={save}>
            <ErrorBox message={action.error} />
            <fieldset className="check-fieldset">
              <legend>允许的数据级别</legend>
              {['public', 'internal', 'confidential'].map((level) => (
                <label className="check-row" key={level}>
                  <input
                    type="checkbox"
                    checked={allowed.includes(level)}
                    onChange={(e) =>
                      setAllowed(e.target.checked ? [...allowed, level] : allowed.filter((l) => l !== level))
                    }
                  />
                  {level}
                </label>
              ))}
            </fieldset>
            <fieldset className="check-fieldset">
              <legend>额外禁止的动作</legend>
              {actions.map((a) => (
                <label className="check-row" key={a.id}>
                  <input
                    type="checkbox"
                    checked={denied.includes(a.id)}
                    onChange={(e) =>
                      setDenied(e.target.checked ? [...denied, a.id] : denied.filter((id) => id !== a.id))
                    }
                  />
                  {a.label}
                </label>
              ))}
            </fieldset>
            <Field label="组织存储上限（GiB）">
              <input
                type="number"
                min="0.001"
                max="1024"
                step="0.001"
                required
                value={storage}
                onChange={(e) => setStorage(e.target.value)}
              />
            </Field>
            <p className="small-note">
              扩大数据级别不代表模型供应商已经符合公司合规要求。调整前请完成相应的数据出口审查。
            </p>
            <div className="form-actions">
              <Button busy={action.busy} disabled={!allowed.length} type="submit">
                确认更新策略
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </Section>
  );
}
