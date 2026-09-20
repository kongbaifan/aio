import { useState } from 'react';
import type { FormEvent } from 'react';
import { KeyRound, Trash2, Users } from 'lucide-react';
import { api, explain } from '../api/client';
import type { Directory, Grants, GrantCreateRequest } from '../api/types';
import { useResource, formatDate, shortId } from '../hooks';
import { Button, ErrorBox, Field, Loading, Modal, Notice } from './ui';

const ACTIONS: Record<string, string> = {
  'project.read': '查看项目',
  'project.write': '在项目中执行任务',
  'project.members.manage': '管理项目成员',
  'agent.read': '查看 Agent',
  'agent.use': '使用 Agent',
  'tool.read': '查看工具',
  'tool.use': '调用工具',
  'model.read': '查看模型',
  'model.use': '使用模型',
  'skill.read': '阅读 Skill 包内容',
  'skill.use': '使用已发布 Skill',
  'skill.update': '管理本人 Skill 草稿',
  'mcp_server.read': '查看 MCP 服务定义',
  'mcp_server.use': '使用已发布 MCP 工具定义',
  'mcp_server.update': '管理 MCP 服务草稿',
  'connection.read': '查看连接信息（不含凭据）',
  'connection.use': '使用明确授权的连接身份',
  'knowledge.read': '查看知识库',
  'knowledge.search': '检索获权文档',
  'knowledge.update': '管理知识库内容',
  'document.read': '阅读这个受限文档',
  'document.update': '管理文档版本与可见性',
  'embedding_model.read': '查看嵌入模型配置',
  'embedding_model.use': '使用嵌入模型（计费）',
  'artifact.read': '查看文件信息',
  'artifact.download': '下载文件',
};
export function GrantModal({ id, name, onClose }: { id: string; name: string; onClose: () => void }) {
  const grants = useResource<Grants>(`/api/v2/resources/${id}/grants`);
  const directory = useResource<Directory>('/api/v2/directory');
  const [subjectType, setType] = useState<'user' | 'department'>('user');
  const [subject, setSubject] = useState('');
  const [actions, setActions] = useState<string[]>([]);
  const [expiry, setExpiry] = useState('');
  const [bundle, setBundle] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const targets =
    subjectType === 'user'
      ? directory.data?.members.map((m) => ({ id: m.user_id, name: m.display_name }))
      : directory.data?.departments;
  const labelFor = (type: string, id: string) =>
    type === 'user'
      ? (directory.data?.members.find((m) => m.user_id === id)?.display_name ?? shortId(id))
      : (directory.data?.departments.find((d) => d.id === id)?.name ?? shortId(id));
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!subject || !actions.length) return;
    setBusy(true);
    setError('');
    try {
      const payload: GrantCreateRequest = {
        subject_type: subjectType,
        subject_id: subject,
        actions,
        expires_at: expiry ? new Date(expiry).toISOString() : null,
        include_dependencies: grants.data?.kind === 'agent' && actions.includes('agent.use') && bundle,
      };
      await api.request(`/api/v2/resources/${id}/grants`, 'PUT', payload);
      grants.reload();
      setActions([]);
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  async function remove(grantId: string, type: string) {
    setBusy(true);
    setError('');
    try {
      await api.request(`/api/v2/resources/${id}/grants/${grantId}?subject_type=${type}`, 'DELETE');
      grants.reload();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={`授权 · ${name}`}
      description="授权在服务端执行。分享项目不会公开成员的私人对话。"
      onClose={onClose}
    >
      <ErrorBox message={error || grants.error || directory.error} />
      {grants.loading || directory.loading ? (
        <Loading />
      ) : (
        grants.data &&
        directory.data && (
          <>
            <form onSubmit={save} className="form-stack">
              <div className="form-grid">
                <Field label="授权范围">
                  <select
                    value={subjectType}
                    onChange={(e) => {
                      setType(e.target.value as 'user' | 'department');
                      setSubject('');
                    }}
                  >
                    <option value="user">指定成员</option>
                    <option value="department">整个部门</option>
                  </select>
                </Field>
                <Field label="接收对象">
                  <select required value={subject} onChange={(e) => setSubject(e.target.value)}>
                    <option value="">请选择…</option>
                    {targets?.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <fieldset className="check-fieldset">
                <legend>允许的操作</legend>
                {grants.data.available_actions
                  .filter((a) => a !== 'artifact.share')
                  .map((action) => (
                    <label key={action} className="check-row">
                      <input
                        type="checkbox"
                        checked={actions.includes(action)}
                        onChange={(e) =>
                          setActions(
                            e.target.checked ? [...actions, action] : actions.filter((a) => a !== action),
                          )
                        }
                      />
                      {ACTIONS[action] ?? action}
                    </label>
                  ))}
              </fieldset>
              {grants.data.kind === 'agent' && (
                <label className="check-row">
                  <input type="checkbox" checked={bundle} onChange={(e) => setBundle(e.target.checked)} />
                  同时授权此版本的模型、工具与知识能力依赖
                </label>
              )}
              {grants.data.kind === 'agent' && (
                <small className="muted">
                  依赖授权会独立留痕；不会共享个人连接或令牌。撤销 Agent 授权不会自动移除独立的依赖权限。
                </small>
              )}
              <Field label="到期时间（可选）">
                <input type="datetime-local" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
              </Field>
              <div className="form-actions">
                <Button type="submit" busy={busy} disabled={!subject || !actions.length}>
                  <KeyRound size={15} />
                  保存授权
                </Button>
              </div>
            </form>
            <div className="section-rule" />
            <h3 className="section-heading">
              <Users size={16} />
              现有授权
            </h3>
            {!grants.data.items.length ? (
              <Notice>尚无额外授权。资源默认仅拥有者可访问。</Notice>
            ) : (
              <ul className="grant-list">
                {grants.data.items.map((g) => (
                  <li key={g.id}>
                    <div>
                      <strong>{labelFor(g.subject_type, g.subject_id)}</strong>
                      <span>
                        {ACTIONS[g.action] ?? g.action} ·{' '}
                        {g.expires_at ? `至 ${formatDate(g.expires_at)}` : '未设到期'}
                      </span>
                    </div>
                    <button
                      className="icon-button danger-text"
                      disabled={busy}
                      aria-label={`撤销 ${labelFor(g.subject_type, g.subject_id)} 的 ${ACTIONS[g.action] ?? g.action}`}
                      onClick={() => void remove(g.id, g.subject_type)}
                    >
                      <Trash2 size={16} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )
      )}
    </Modal>
  );
}
