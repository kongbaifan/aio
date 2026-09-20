import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  ArrowDownToLine,
  Check,
  FileText,
  Folder,
  FolderPlus,
  KeyRound,
  RefreshCw,
  ShieldCheck,
  Wallet,
} from 'lucide-react';
import { api, explain } from '../api/client';
import type { Approval, ApprovalDetail, Artifact, Page, Project, Usage } from '../api/types';
import { formatBytes, formatDate, shortId, useResource } from '../hooks';
import { money, remainingMoney } from '../money';
import { useWorkspace } from '../components/Layout';
import { GrantModal } from '../components/GrantModal';
import { Badge, Button, Empty, ErrorBox, Field, Loading, Modal, Notice, PageTitle } from '../components/ui';

export function Files() {
  const workspace = useWorkspace();
  const [selected, setSelected] = useState('');
  const projectId = selected || workspace.projects[0]?.id || '';
  const files = useResource<Page<Artifact>>(projectId ? `/api/v2/projects/${projectId}/files` : null);
  const project = useResource<Project>(projectId ? `/api/v2/projects/${projectId}` : null);
  const [grant, setGrant] = useState(false);
  const [create, setCreate] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function createProject(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const p = await api.request<Project>('/api/v2/projects', 'POST', { name });
      workspace.refresh();
      setSelected(p.id);
      setCreate(false);
      setName('');
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <PageTitle
        eyebrow="PROJECT FILES"
        title="项目文件"
        description="上传资料与已发布产物集中保存在项目中。只有当前有权访问的文件会出现在这里。"
        action={
          <Button variant="secondary" onClick={() => setCreate(true)}>
            <FolderPlus size={16} />
            新建项目
          </Button>
        }
      />
      <div className="file-toolbar">
        <label>
          <Folder size={17} />
          <span className="sr-only">选择项目</span>
          <select value={projectId} onChange={(e) => setSelected(e.target.value)}>
            {workspace.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
            {!workspace.projects.length && <option value="">暂无项目</option>}
          </select>
        </label>
        <div>
          {project.data?.can_manage && (
            <Button variant="quiet" onClick={() => setGrant(true)}>
              <KeyRound size={15} />
              项目授权
            </Button>
          )}
          <button className="icon-button" aria-label="刷新文件" onClick={files.reload}>
            <RefreshCw size={17} />
          </button>
        </div>
      </div>
      <ErrorBox
        message={error || files.error || project.error}
        retry={files.error ? files.reload : undefined}
      />
      {files.loading ? (
        <Loading />
      ) : !files.data?.items.length ? (
        <Empty title={projectId ? '项目还没有文件' : '先创建一个项目'}>
          在对话中上传文件，或让 Agent 生成结果后，文件会出现在这里。
        </Empty>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>文件名称</th>
                <th>来源</th>
                <th>大小</th>
                <th>访问方式</th>
                <th>
                  <span className="sr-only">操作</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {files.data.items.map((file) => (
                <tr key={file.id}>
                  <td>
                    <div className="file-name">
                      <span>
                        <FileText size={19} />
                      </span>
                      <div>
                        <strong>{file.path}</strong>
                        <small>{shortId(file.id)}</small>
                      </div>
                    </div>
                  </td>
                  <td>{file.run_id ? '任务产物' : '上传资料'}</td>
                  <td className="mono">{formatBytes(file.bytes)}</td>
                  <td>
                    <span className="attachment-label">
                      <ShieldCheck size={13} />
                      授权附件
                    </span>
                  </td>
                  <td>
                    <Button
                      variant="quiet"
                      onClick={() =>
                        void api
                          .download(
                            `/api/v2/artifacts/${file.id}/download`,
                            file.path.split('/').at(-1) ?? file.path,
                          )
                          .catch((e) => setError(explain(e)))
                      }
                    >
                      <ArrowDownToLine size={15} />
                      下载
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Notice>
        文件以附件形式下载，不在页面中执行 HTML 或 Office 内容。来源权限改变后，派生文件也会重新校验。
      </Notice>
      {grant && project.data && (
        <GrantModal id={project.data.id} name={project.data.name} onClose={() => setGrant(false)} />
      )}
      {create && (
        <Modal title="新建私有项目" onClose={() => setCreate(false)}>
          <form className="form-stack" onSubmit={createProject}>
            <Field label="项目名称">
              <input value={name} required maxLength={200} onChange={(e) => setName(e.target.value)} />
            </Field>
            <ErrorBox message={error} />
            <div className="form-actions">
              <Button busy={busy} type="submit">
                创建项目
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

export function Approvals() {
  const list = useResource<Page<Approval>>('/api/v2/approvals');
  const [selected, setSelected] = useState<Approval | null>(null);
  const detail = useResource<ApprovalDetail>(selected ? `/api/v2/approvals/${selected.id}` : null);
  const [decision, setDecision] = useState<'approve' | 'reject' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function decide() {
    if (!detail.data || !decision) return;
    setBusy(true);
    setError('');
    try {
      await api.request(`/api/v2/approvals/${detail.data.approval_id}/decision`, 'POST', {
        expected_revision: detail.data.revision,
        action_digest: detail.data.action_digest,
        decision,
      });
      setDecision(null);
      detail.reload();
      list.reload();
    } catch (error) {
      setError(explain(error));
      detail.reload();
    } finally {
      setBusy(false);
    }
  }
  const pending = list.data?.items.filter((a) => a.state === 'pending').length ?? 0;
  return (
    <div className="page">
      <PageTitle
        eyebrow="HUMAN REVIEW"
        title="待办审批"
        description="这里只显示你有权查看或处理的具体动作。批准一次操作不会赋予 Agent 永久权限。"
        action={<span className="count-label">{pending} 项待处理</span>}
      />
      <ErrorBox message={list.error} retry={list.reload} />
      {list.loading ? (
        <Loading />
      ) : !list.data?.items.length ? (
        <Empty title="目前没有待办审批">需要你确认的操作会在这里列出。普通计算任务按组织策略执行。</Empty>
      ) : (
        <div className="approval-grid">
          <div className="approval-list">
            {list.data.items.map((item) => (
              <button
                key={item.id}
                className={`approval-row ${selected?.id === item.id ? 'selected' : ''}`}
                onClick={() => {
                  setSelected(item);
                  setError('');
                  setDecision(null);
                }}
              >
                <ShieldCheck size={20} />
                <div>
                  <strong>工具操作确认</strong>
                  <small>
                    任务 {shortId(item.run_id)} · 截止 {formatDate(item.expires_at)}
                  </small>
                </div>
                <Badge state={item.state} />
              </button>
            ))}
          </div>
          <section className="approval-detail">
            {!selected ? (
              <Empty title="选择一项审批">先核对动作、版本和有效期，再决定是否批准。</Empty>
            ) : detail.loading ? (
              <Loading />
            ) : detail.error ? (
              <ErrorBox message={detail.error} retry={detail.reload} />
            ) : (
              detail.data && (
                <>
                  <span className="eyebrow">ACTION REVIEW</span>
                  <h2>{detail.data.summary.tool}</h2>
                  <Badge state={detail.data.state} />
                  <dl className="details-list">
                    <div>
                      <dt>风险等级</dt>
                      <dd>{detail.data.summary.risk}</dd>
                    </div>
                    <div>
                      <dt>任务 ID</dt>
                      <dd className="mono">{shortId(detail.data.run_id)}</dd>
                    </div>
                    <div>
                      <dt>有效期</dt>
                      <dd>{formatDate(detail.data.expires_at)}</dd>
                    </div>
                    <div>
                      <dt>动作摘要</dt>
                      <dd className="digest">{detail.data.action_digest}</dd>
                    </div>
                  </dl>
                  <p className="small-note">
                    审批绑定这份动作的内容摘要。参数、代码、输入或身份发生变化时，原审批不能继续使用。
                  </p>
                  <ErrorBox message={error} />
                  {detail.data.state === 'pending' && (
                    <div className="form-actions">
                      <Button variant="secondary" onClick={() => setDecision('reject')}>
                        拒绝操作
                      </Button>
                      <Button onClick={() => setDecision('approve')}>
                        <Check size={16} />
                        确认批准
                      </Button>
                    </div>
                  )}
                </>
              )
            )}
          </section>
        </div>
      )}
      {decision && (
        <Modal
          title={decision === 'approve' ? '确认批准这个动作？' : '拒绝这个动作？'}
          description="请只处理你已核对业务影响且有权审批的操作。"
          onClose={() => setDecision(null)}
        >
          <ErrorBox message={error} />
          <p>你的决定将记录在服务端。已过期、已变化或已被处理的审批会被拒绝。</p>
          <div className="form-actions">
            <Button variant="secondary" onClick={() => setDecision(null)}>
              返回核对
            </Button>
            <Button
              variant={decision === 'reject' ? 'danger' : 'primary'}
              busy={busy}
              onClick={() => void decide()}
            >
              {decision === 'approve' ? '批准这次操作' : '拒绝这次操作'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

export function UsagePage() {
  const usage = useResource<Usage>('/api/v2/usage');
  return (
    <div className="page usage-page">
      <PageTitle
        eyebrow="USAGE & BUDGET"
        title="我的用量"
        description="区分已经发生的费用、任务预留与待核对用量，避免把未知费用当成免费。"
      />
      <ErrorBox message={usage.error} retry={usage.reload} />
      {usage.loading ? (
        <Loading />
      ) : (
        usage.data && (
          <>
            <div className="usage-heading">
              <span className="usage-icon">
                <Wallet size={25} />
              </span>
              <div>
                <strong>{usage.data.configured ? '个人任务预算' : '尚未配置任务预算'}</strong>
                <p>
                  {usage.data.configured
                    ? '所有金额按当前记账币种展示。'
                    : '请联系组织管理员分配额度后再发起任务。'}
                </p>
              </div>
              <span className="currency-label">{usage.data.currency}</span>
            </div>
            <div className="usage-ledger">
              <div>
                <span>总额度</span>
                <strong>{money(usage.data.hard_limit)}</strong>
                <small>管理员配置的上限</small>
              </div>
              <div>
                <span>已记账</span>
                <strong>{money(usage.data.consumed)}</strong>
                <small>已确认并记入账本</small>
              </div>
              <div>
                <span>任务预留</span>
                <strong>{money(usage.data.reserved)}</strong>
                <small>包含未完成或待核对的费用</small>
              </div>
              <div>
                <span>可用额度</span>
                <strong>
                  {remainingMoney(usage.data.hard_limit, usage.data.consumed, usage.data.reserved) ?? '—'}
                </strong>
                <small>不代表外部供应商最终账单</small>
              </div>
            </div>
            <section className="usage-explanation">
              <h2>为什么有费用预留？</h2>
              <p>
                每个任务在执行前预留预算。已确认费用在结束时结算；供应商没有返回完整用量时，会保留待核对额度，之后追加核对，不直接清零。
              </p>
              <div className="small-note">
                <ClockIcon />
                当前待核对模型调用：<strong>{usage.data.unknown_calls ?? 0}</strong>
              </div>
            </section>
          </>
        )
      )}
    </div>
  );
}
function ClockIcon() {
  return <span className="status-dot amber" aria-hidden="true" />;
}
