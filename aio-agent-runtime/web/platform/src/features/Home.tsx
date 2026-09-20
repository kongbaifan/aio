import { useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Bot,
  Check,
  FileText,
  FolderPlus,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { useAuth } from '../auth';
import { api, explain } from '../api/client';
import type { Agent, Page, Project, Session } from '../api/types';
import { useResource } from '../hooks';
import { useWorkspace } from '../components/Layout';
import { Button, Empty, ErrorBox, Field, Loading, Modal, PageTitle } from '../components/ui';

export function Login() {
  const config = useResource<{
    organization_id: string | null;
    organization_label: string;
    authentication: string;
  }>('/api/public/login');
  const { error, refresh } = useAuth();
  const [org, setOrg] = useState('');
  const [invalid, setInvalid] = useState('');
  function login(event: FormEvent) {
    event.preventDefault();
    const id = config.data?.organization_id || org;
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
      setInvalid('请输入管理员提供的组织 ID。');
      return;
    }
    window.location.assign(`/auth/login?org_id=${encodeURIComponent(id)}`);
  }
  return (
    <div className="login-screen">
      <section className="login-story">
        <div className="brand login-brand">
          <span className="brand-symbol">
            a<span>i</span>o
          </span>
          <strong>共同工作台</strong>
        </div>
        <span className="eyebrow">ONE PORTAL. YOUR WORKSPACE.</span>
        <h1>
          让工作一起向前。
          <br />
          <em>让边界始终清楚。</em>
        </h1>
        <p>
          从问题到结果，在同一个工作台完成。
          <br />
          统一使用团队配置的 Agent，保留每次任务的进展与产物。
        </p>
        <div className="login-workflow">
          <span>
            <Bot size={20} />
            选择 Agent
          </span>
          <i />
          <span>
            <FileText size={20} />
            提交任务
          </span>
          <i />
          <span>
            <Check size={20} />
            查看结果
          </span>
        </div>
        <div className="login-caption">
          <ShieldCheck size={16} />
          统一管理能力 · 按权限访问数据
        </div>
      </section>
      <section className="login-access">
        <form onSubmit={login} className="login-card">
          <span className="login-icon">
            <LockKeyhole size={23} />
          </span>
          <span className="eyebrow">企业入口</span>
          <h2>欢迎回到工作台</h2>
          <p>{config.data?.organization_label ?? '使用企业身份登录，进入你的工作空间。'}</p>
          <ErrorBox
            message={invalid || error || config.error}
            retry={error ? () => void refresh() : config.error ? config.reload : undefined}
          />
          {!config.data?.organization_id && (
            <Field label="组织 ID" hint="首次使用请向管理员获取；登录密码仅在企业身份提供方输入。">
              <input
                value={org}
                onChange={(e) => setOrg(e.target.value)}
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                autoComplete="off"
                required
              />
            </Field>
          )}
          <Button type="submit" disabled={config.loading}>
            使用企业 SSO 登录
            <ArrowRight size={17} />
          </Button>
          <p className="login-fine">本页面不收集企业密码。登录后，仅显示已授予你的 Agent、项目与文件。</p>
        </form>
        <small className="muted">AIO Agent Runtime · 企业工作台</small>
      </section>
    </div>
  );
}

export function Home() {
  const { me } = useAuth();
  const workspace = useWorkspace();
  const agents = useResource<Page<Agent>>('/api/v2/agents');
  const [selected, setSelected] = useState<Agent | null>(null);
  const [project, setProject] = useState('');
  const [projectName, setProjectName] = useState('我的工作项目');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  async function start(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    setBusy(true);
    setError('');
    try {
      let id = project;
      if (!id) {
        const created = await api.request<Project>('/api/v2/projects', 'POST', { name: projectName });
        id = created.id;
      }
      const session = await api.request<Session>('/api/v2/sessions', 'POST', {
        project_id: id,
        agent_version_id: selected.id,
        title: `${selected.name} · 新任务`,
      });
      workspace.refresh();
      navigate(`/app/sessions/${session.id}`);
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page home-page">
      <PageTitle
        eyebrow="YOUR WORKSPACE"
        title={`你好，${me?.display_name ?? '同事'}`}
        description="选择一个已授权的 Agent，开始今天的任务。"
      />
      <section className="workspace-intro">
        <div>
          <span className="intro-label">
            <Sparkles size={14} />
            从一个具体问题开始
          </span>
          <h2>
            把问题变成
            <br />
            <span>可追踪的工作。</span>
          </h2>
          <p>准备资料，交代目标。执行进展、待办审批和结果文件，都留在同一处。</p>
        </div>
        <div className="intro-track" aria-label="任务流程">
          <div>
            <span className="track-icon">
              <Bot size={19} />
            </span>
            <div>
              <strong>选择合适的 Agent</strong>
              <p>使用团队已配置、已授权的能力</p>
            </div>
          </div>
          <div>
            <span className="track-icon">
              <FileText size={19} />
            </span>
            <div>
              <strong>给出目标与资料</strong>
              <p>文件只进入对应项目的任务范围</p>
            </div>
          </div>
          <div>
            <span className="track-icon">
              <Check size={19} />
            </span>
            <div>
              <strong>核对并带走结果</strong>
              <p>查看轨迹、引用与可下载的产物</p>
            </div>
          </div>
        </div>
      </section>
      <div className="section-top">
        <div>
          <h2>可用 Agent</h2>
          <p>这里只显示当前账号有权使用的已发布版本。</p>
        </div>
        <span className="count-label">{agents.data?.items.length ?? '—'} 个可用</span>
      </div>
      <ErrorBox message={agents.error} retry={agents.reload} />
      {agents.loading ? (
        <Loading />
      ) : !agents.data?.items.length ? (
        <Empty
          title="还没有分配 Agent"
          action={
            me?.permissions.organization_admin ? (
              <Link className="button button-primary" to="/app/admin/agents">
                配置第一个 Agent
                <ArrowRight size={16} />
              </Link>
            ) : undefined
          }
        >
          请联系组织管理员，为你或所在部门授予 Agent 及其依赖能力。
        </Empty>
      ) : (
        <div className="agent-grid">
          {agents.data.items.map((agent, index) => (
            <button
              key={agent.id}
              className="agent-card"
              onClick={() => {
                setSelected(agent);
                setProject(workspace.projects[0]?.id ?? '');
                setError('');
              }}
            >
              <div className={`agent-glyph agent-glyph-${index % 3}`}>
                <Bot size={24} />
              </div>
              <span className="agent-version">v{agent.version}</span>
              <h3>{agent.name}</h3>
              <p>在项目中创建独立对话，使用此发布版本处理你的任务。</p>
              <div className="agent-card-footer">
                <span>
                  <ShieldCheck size={13} />
                  已获得使用权限
                </span>
                <ArrowRight size={17} />
              </div>
            </button>
          ))}
        </div>
      )}
      <div className="home-note">
        <LockKeyhole size={17} />
        <p>
          <strong>共享能力，不混用工作数据。</strong> 项目分享和私人对话分别授权。新的任务会重新检查当前权限。
        </p>
      </div>
      {selected && (
        <Modal
          title={`开始 · ${selected.name}`}
          description="选择项目来保存任务文件；对话仍默认属于你自己。"
          onClose={() => setSelected(null)}
        >
          <form onSubmit={start} className="form-stack">
            <ErrorBox message={error} />
            <Field label="任务项目">
              <select value={project} onChange={(e) => setProject(e.target.value)}>
                <option value="">＋ 新建私有项目</option>
                {workspace.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
            {!project && (
              <Field label="项目名称">
                <input
                  required
                  maxLength={200}
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                />
              </Field>
            )}
            <div className="small-note">
              <FolderPlus size={16} />
              新项目不自动共享给其他成员。
            </div>
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={() => setSelected(null)}>
                取消
              </Button>
              <Button type="submit" busy={busy}>
                进入对话
                <ArrowRight size={16} />
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
