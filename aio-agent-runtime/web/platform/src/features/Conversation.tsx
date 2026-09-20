import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ArrowDownToLine,
  ArrowUp,
  Bot,
  Check,
  Clock3,
  FileText,
  Folder,
  Paperclip,
  Pencil,
  Radio,
  Square,
  Trash2,
  X,
} from 'lucide-react';
import { api, ApiError, explain } from '../api/client';
import type { Artifact, SessionDetail, RunCreateRequest, MCPConnection, Page } from '../api/types';
import { useAuth } from '../auth';
import { useRun } from '../run';
import { formatBytes, formatDate, shortId, useResource } from '../hooks';
import { useWorkspace } from '../components/Layout';
import { Badge, Button, Empty, ErrorBox, Field, Loading, Modal, TERMINAL } from '../components/ui';
import { TeamProgress } from './TeamProgress';

const EVENT_NAMES: Record<string, string> = {
  'run.queued': '任务已进入队列',
  'run.preparing': '准备执行环境',
  'run.started': '开始处理任务',
  'model.started': '模型正在生成',
  'model.completed': '模型回合已保存',
  'tool.planned': '准备调用工具',
  'tool.started': '执行工具',
  'tool.completed': '工具执行完成',
  'tool.failed': '工具未能完成',
  'tool.denied': '工具操作已拒绝',
  'approval.required': '等待人工审批',
  'approval.resolved': '审批结果已保存',
  'artifact.ready': '产物已发布',
  'usage.updated': '用量已更新',
  'run.completed': '任务已完成',
  'run.failed': '任务未完成',
  'run.cancel_requested': '正在停止任务',
  'run.cancelled': '任务已取消',
  'run.recovery_required': '需要核对外部执行结果',
  'run.timed_out': '任务已超时',
  'team.planning': '正在规划任务步骤',
  'team.plan.committed': '任务计划已保存',
  'team.step.started': '开始执行任务步骤',
  'team.step.completed': '步骤结果已保存',
  'team.synthesis.started': '正在汇总步骤结果',
  'team.stopped': '多步骤任务已停止',
  'workspace.checkpointing': '正在保存工作区文件',
  'workspace.checkpointed': '文件检查点已保存，旧环境已回收',
  'workspace.resume_ready': '新代次已校验工作区文件',
  'workspace.checkpoint_purged': '临时检查点已清理',
  'workspace.checkpoint_acknowledged': '执行节点导出缓存已清理',
  'stdio.preparing': '准备专属 MCP 进程',
  'stdio.stopped': 'MCP 进程已确认停止',
};
const CitationModal = lazy(() => import('./Knowledge').then((module) => ({ default: module.CitationModal })));
export function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export function Conversation() {
  const { sessionId } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { me } = useAuth();
  const workspace = useWorkspace();
  const history = useResource<SessionDetail>(sessionId ? `/api/v2/sessions/${sessionId}` : null);
  const runId = params.get('run') ?? history.data?.runs[0]?.id ?? null;
  const live = useRun(runId);
  const [message, setMessage] = useState('');
  const [files, setFiles] = useState<Artifact[]>([]);
  const [allowStdioAttachments, setAllowStdioAttachments] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [edit, setEdit] = useState<'rename' | 'archive' | null>(null);
  const [title, setTitle] = useState('');
  const [pendingRequest, setPendingRequest] = useState<{ key: string; body: RunCreateRequest } | null>(null);
  const connections = useResource<Page<MCPConnection>>(me?.capabilities.mcp ? '/api/v2/connections' : null);
  const [connectionBindings, setConnectionBindings] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<'single' | 'team'>('single');
  const [citationId, setCitationId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const settled = useRef('');
  const currentSession = useRef(sessionId);
  const activeRun = history.data?.runs.find((r) => !TERMINAL.has(r.state));
  const blocked = history.data?.runs.some((r) => r.state === 'recovery_required') ?? false;
  const active = Boolean(activeRun || (live.run && !TERMINAL.has(live.run.state)));
  useEffect(() => {
    setMessage('');
    setFiles([]);
    setAllowStdioAttachments(false);
    setError('');
    setBusy(false);
    setUploading(false);
    setPendingRequest(null);
    setConnectionBindings({});
    setMode('single');
    setCitationId(null);
    currentSession.current = sessionId;
    settled.current = '';
  }, [sessionId]);
  useEffect(() => {
    if (live.run && TERMINAL.has(live.run.state) && settled.current !== live.run.id) {
      settled.current = live.run.id;
      history.reload();
      workspace.refresh();
    }
  }, [live.run?.state, live.run?.id]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [live.draft, history.data?.messages.length]);
  async function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!history.data || busy || uploading || active || blocked || (!message.trim() && !pendingRequest))
      return;
    const sid = history.data.id;
    setBusy(true);
    setError('');
    const request = pendingRequest ?? {
      key: crypto.randomUUID(),
      body: {
        message,
        agent_version_id: history.data.agent_version_id,
        expected_session_revision: history.data.revision,
        input_artifact_ids: files.map((f) => f.id),
        allow_stdio_attachments: files.length > 0 && allowStdioAttachments,
        connection_bindings: connectionBindings,
        mode:
          me?.capabilities.team && history.data.supported_modes?.includes('team')
            ? mode
            : ('single' as const),
      },
    };
    setPendingRequest(request);
    try {
      const result = await api.request<{ run_id: string }>(
        `/api/v2/sessions/${sid}/runs`,
        'POST',
        request.body,
        { headers: { 'Idempotency-Key': request.key } },
      );
      if (currentSession.current !== sid) return;
      setMessage('');
      setFiles([]);
      setAllowStdioAttachments(false);
      setPendingRequest(null);
      setParams({ run: result.run_id });
      history.reload();
      workspace.refresh();
    } catch (error) {
      if (currentSession.current === sid) {
        setError(explain(error));
        if (error instanceof ApiError && error.status < 500) {
          setPendingRequest(null);
          if (error.status === 409) history.reload();
        }
      }
    } finally {
      if (currentSession.current === sid) setBusy(false);
    }
  }
  async function upload(selected: FileList | null) {
    if (!selected || !history.data) return;
    const sid = history.data.id;
    const pid = history.data.project_id;
    setUploading(true);
    setAllowStdioAttachments(false);
    setError('');
    try {
      if (files.length + selected.length > 32) throw new ApiError('PAYLOAD_TOO_LARGE', 413);
      for (const file of [...selected]) {
        if (file.size > 8 * 1024 * 1024) throw new ApiError('PAYLOAD_TOO_LARGE', 413);
        const slot = await api.request<{ content_url: string }>(`/api/v2/projects/${pid}/uploads`, 'POST', {
          path: file.name,
          max_bytes: file.size,
        });
        const artifact = await api.request<Artifact>(slot.content_url, 'PUT', undefined, {
          body: file,
          headers: { 'Content-Type': 'application/octet-stream' },
        });
        if (currentSession.current === sid)
          setFiles((old) => [...old.filter((f) => f.path !== artifact.path), artifact]);
      }
    } catch (error) {
      if (currentSession.current === sid) setError(explain(error));
    } finally {
      if (currentSession.current === sid) setUploading(false);
      if (fileInput.current) fileInput.current.value = '';
    }
  }
  async function stop() {
    const target = activeRun?.id ?? runId;
    if (!target) return;
    setBusy(true);
    setError('');
    try {
      await api.request(`/api/v2/runs/${target}/cancel`, 'POST');
      live.reconnect();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  async function editSession(event: FormEvent) {
    event.preventDefault();
    if (!history.data) return;
    setBusy(true);
    setError('');
    try {
      if (edit === 'rename') {
        await api.request(`/api/v2/sessions/${sessionId}`, 'PATCH', {
          name: title,
          expected_revision: history.data.revision,
        });
        history.reload();
      } else {
        await api.request(
          `/api/v2/sessions/${sessionId}?expected_revision=${history.data.revision}`,
          'DELETE',
        );
        navigate('/app');
      }
      setEdit(null);
      workspace.refresh();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  if (history.loading && !history.data) return <Loading label="正在打开对话…" />;
  if (history.error || !history.data)
    return (
      <div className="page">
        <ErrorBox message={history.error} retry={history.reload} />
      </div>
    );
  const session = history.data;
  const project = workspace.projects.find((p) => p.id === session.project_id);
  const transcript = session.messages.filter((m) => m.role !== 'tool');
  const alreadySaved = transcript.some((m) => m.role === 'assistant' && m.run_id === runId);
  return (
    <div className="conversation-page">
      <div className="conversation-top">
        <div>
          <span className="eyebrow">
            <Folder size={12} />
            {project?.name ?? '当前项目'}
          </span>
          <h1>{session.title}</h1>
        </div>
        <div className="row-actions">
          <button
            className="icon-button"
            aria-label="重命名对话"
            onClick={() => {
              setTitle(session.title);
              setEdit('rename');
            }}
          >
            <Pencil size={16} />
          </button>
          <button className="icon-button" aria-label="归档对话" onClick={() => setEdit('archive')}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      <div className="conversation-grid">
        <section className="chat-panel" aria-label="对话内容">
          <div className="messages">
            {!transcript.length && (
              <Empty title="从一个具体目标开始">说明你希望得到什么结果，也可以上传需要处理的文件。</Empty>
            )}
            {transcript.map((m) => (
              <article key={`${m.run_id}:${m.seq}`} className={`message message-${m.role}`}>
                <div className="message-role">
                  {m.role === 'user' ? (
                    <span className="mini-avatar">{me?.display_name.slice(0, 1)}</span>
                  ) : (
                    <Bot size={17} />
                  )}
                  <strong>{m.role === 'user' ? '你' : 'Agent'}</strong>
                  {m.content.redacted && <span className="muted">来源权限已改变</span>}
                </div>
                <Markdown text={m.content.text ?? ''} />
              </article>
            ))}
            {!alreadySaved && (live.draft || live.run?.result?.answer) && (
              <article className="message message-assistant">
                <div className="message-role">
                  <Bot size={17} />
                  <strong>Agent</strong>
                  {active && <span className="typing-dot" />}
                </div>
                <Markdown text={live.run?.result?.answer ?? live.draft} />
              </article>
            )}
            {active && live.run && !live.draft && (
              <div className="task-wait" role="status">
                <Radio size={16} />
                <Badge state={live.run!.state} />
                <span>任务在后台进行，关闭页面不会自动取消。</span>
              </div>
            )}
            {live.run?.state === 'recovery_required' && (
              <div className="notice warning">
                外部执行结果尚待核对。请联系已授权人员处理，不要重复提交相同操作。
              </div>
            )}
            {live.run?.error_code && (
              <div className="run-error">
                <strong>本次任务未完整完成</strong>
                <code>{live.run.error_code}</code>
                <span>结果以服务端记录为准。重新操作前请确认没有重复影响。</span>
              </div>
            )}
            {!!live.run?.result?.citations?.length && (
              <section className="answer-citations">
                <h3>本次检索的文档依据</h3>
                <p>这些引用由服务端绑定到实际文档版本，点击后重新验证访问权限。</p>
                {live.run.result.citations.map((citation) => (
                  <button key={citation.id} onClick={() => setCitationId(citation.id)}>
                    <FileText size={15} />
                    <span>
                      <strong>{citation.title}</strong>
                      <small>
                        {citation.label} · 版本 {citation.version}
                      </small>
                    </span>
                  </button>
                ))}
              </section>
            )}
            {Boolean(live.run?.result?.artifacts?.length) && (
              <div className="result-files">
                <h3>
                  <Check size={16} />
                  已发布文件
                </h3>
                {live.run?.result?.artifacts?.map((f) => (
                  <button
                    key={f.artifact_id}
                    onClick={() =>
                      void api
                        .download(
                          `/api/v2/artifacts/${f.artifact_id}/download`,
                          f.path.split('/').at(-1) ?? f.path,
                        )
                        .catch((e) => setError(explain(e)))
                    }
                  >
                    <FileText size={18} />
                    <span>
                      {f.path}
                      <small>{formatBytes(f.bytes)}</small>
                    </span>
                    <ArrowDownToLine size={16} />
                  </button>
                ))}
              </div>
            )}
            <div ref={bottom} />
          </div>
          <div className="composer-area">
            <ErrorBox message={error} />
            <ErrorBox message={live.error} retry={live.reconnect} />
            {files.length > 0 && (
              <div className="attachment-list">
                {files.map((file) => (
                  <span key={file.id}>
                    <FileText size={14} />
                    {file.path}
                    <button
                      aria-label={`移除 ${file.path}`}
                      disabled={busy || Boolean(pendingRequest)}
                      onClick={() => {
                        setFiles((old) => old.filter((f) => f.id !== file.id));
                        setAllowStdioAttachments(false);
                      }}
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <form className="composer" onSubmit={submit}>
              {files.length > 0 && !!session.mcp_server_ids?.length && (
                <fieldset className="check-fieldset" disabled={active || busy || Boolean(pendingRequest)}>
                  <legend>隔离 MCP 附件权限</legend>
                  <label className="check-row">
                    <input
                      type="checkbox"
                      aria-describedby="stdio-attachments-hint"
                      checked={allowStdioAttachments}
                      disabled={
                        active ||
                        busy ||
                        Boolean(pendingRequest) ||
                        files.reduce((total, file) => total + file.bytes, 0) > 4 * 1024 * 1024
                      }
                      onChange={(e) => setAllowStdioAttachments(e.target.checked)}
                    />
                    允许隔离 MCP 读取本次所选附件
                  </label>
                  <small id="stdio-attachments-hint">
                    默认不提供文件。仅操作员已批准读取附件的 stdio 模板可获得本次所选文件的私有副本； 最多 32
                    个、合计 4 MiB，不包含项目其他文件或宿主目录。
                  </small>
                </fieldset>
              )}
              {!!session.mcp_server_ids?.length && (
                <fieldset
                  className="connection-selector"
                  disabled={active || busy || Boolean(pendingRequest)}
                >
                  <legend>本次任务使用的 MCP 身份</legend>
                  {session.mcp_server_ids.map((serverId) => {
                    const available =
                      connections.data?.items.filter(
                        (c) =>
                          c.server_id === serverId && c.state === 'active' && c.resource_status === 'active',
                      ) ?? [];
                    return (
                      <Field key={serverId} label={`连接身份 · ${shortId(serverId)}`}>
                        <select
                          value={connectionBindings[serverId] ?? ''}
                          required={available.length !== 1}
                          onChange={(e) =>
                            setConnectionBindings((old) => {
                              const next = { ...old };
                              if (e.target.value) next[serverId] = e.target.value;
                              else delete next[serverId];
                              return next;
                            })
                          }
                        >
                          <option value="">
                            {available.length === 1
                              ? `自动使用：${available[0].name}`
                              : '请选择已通过检测的连接…'}
                          </option>
                          {available.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name} · {c.scope === 'personal' ? '我的个人身份' : '部门服务身份'}
                            </option>
                          ))}
                        </select>
                      </Field>
                    );
                  })}
                  <Link to="/app/connections">添加或检测我的连接</Link>
                  <ErrorBox message={connections.error} retry={connections.reload} />
                </fieldset>
              )}
              {me?.capabilities.team && session.supported_modes?.includes('team') && (
                <div className="composer-mode">
                  <Field label="执行方式" hint="多步骤模式使用同一份任务预算和隔离工作区，不是多人共用环境。">
                    <select
                      aria-label="执行方式"
                      value={mode}
                      disabled={busy || active || Boolean(pendingRequest)}
                      onChange={(e) => setMode(e.target.value as 'single' | 'team')}
                    >
                      <option value="single">直接执行</option>
                      <option value="team">多步骤协作 · 规划、执行、汇总</option>
                    </select>
                  </Field>
                </div>
              )}
              <label className="sr-only" htmlFor="task-message">
                任务内容
              </label>
              <textarea
                id="task-message"
                placeholder="描述你的目标，例如：分析这份数据，并生成一份结果报告。"
                value={message}
                maxLength={65536}
                disabled={busy || Boolean(pendingRequest)}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    void submit();
                  }
                }}
              />
              <div className="composer-toolbar">
                <div>
                  <input
                    ref={fileInput}
                    type="file"
                    multiple
                    className="sr-only"
                    tabIndex={-1}
                    onChange={(e) => void upload(e.target.files)}
                  />
                  <button
                    className="attach-button"
                    type="button"
                    disabled={
                      !me?.capabilities.file_upload || uploading || busy || active || Boolean(pendingRequest)
                    }
                    onClick={() => fileInput.current?.click()}
                  >
                    <Paperclip size={17} />
                    {uploading ? '正在上传…' : '添加文件'}
                  </button>
                  <span className="composer-shortcut">Ctrl / ⌘ + Enter</span>
                </div>
                {active ? (
                  <Button type="button" variant="secondary" busy={busy} onClick={() => void stop()}>
                    <Square size={13} />
                    停止任务
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    busy={busy}
                    disabled={blocked || uploading || (!message.trim() && !pendingRequest)}
                  >
                    {pendingRequest ? '重试同一提交' : '发送任务'}
                    <ArrowUp size={16} />
                  </Button>
                )}
              </div>
            </form>
            <p className="composer-note">文件仅作为当前任务的授权输入。AI 生成内容请核对后使用。</p>
          </div>
        </section>
        <aside className="run-inspector" aria-label="执行记录">
          <div className="inspector-heading">
            <h2>执行记录</h2>
            <span className={`connection-indicator ${live.connected ? 'connected' : ''}`} />
          </div>
          {session.runs.length > 0 && (
            <Field label="查看任务">
              <select
                aria-label="选择执行记录"
                value={runId ?? ''}
                onChange={(e) => setParams({ run: e.target.value })}
              >
                {session.runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {formatDate(r.created_at)} · {shortId(r.id)}
                  </option>
                ))}
              </select>
            </Field>
          )}
          {live.run ? (
            <>
              <div className="run-summary">
                <Badge state={live.run.state} />
                <code>{shortId(live.run.id)}</code>
                <dl>
                  <div>
                    <dt>开始</dt>
                    <dd>{formatDate(live.run.created_at)}</dd>
                  </div>
                  <div>
                    <dt>执行代次</dt>
                    <dd>{live.run.generation || '等待分配'}</dd>
                  </div>
                  <div>
                    <dt>执行环境</dt>
                    <dd>
                      {live.run.cleanup_state === 'clean'
                        ? '已回收'
                        : live.run.cleanup_state === 'not_allocated'
                          ? '未分配'
                          : live.run.cleanup_state}
                    </dd>
                  </div>
                </dl>
              </div>
              {live.run.workspace_checkpoint && (
                <p className="team-hint">
                  工作区检查点 · {live.run.workspace_checkpoint.file_count ?? '待确认'} 个文件
                  {live.run.workspace_checkpoint.bytes !== null &&
                    ` · ${formatBytes(live.run.workspace_checkpoint.bytes)}`}
                  。 仅保留文件，不保留后台进程和内存状态。
                </p>
              )}
              {live.run.team && <TeamProgress team={live.run.team} runState={live.run.state} />}
              <ol className="timeline">
                {live.events
                  .filter((e) => !['answer.delta', 'team.output.delta'].includes(e.kind))
                  .map((e) => (
                    <li key={e.seq}>
                      <span className="timeline-dot" />
                      <div>
                        <strong>{EVENT_NAMES[e.kind] ?? e.kind}</strong>
                        <time>{formatDate(e.timestamp)}</time>
                        {typeof e.payload.reason_code === 'string' && <code>{e.payload.reason_code}</code>}
                      </div>
                    </li>
                  ))}
              </ol>
              {live.run.state === 'waiting_approval' && (
                <Link className="button button-secondary" to="/app/approvals">
                  前往审批中心
                  <ArrowUp size={14} />
                </Link>
              )}
            </>
          ) : (
            <div className="inspector-empty">
              <Clock3 size={24} />
              <p>提交任务后，这里会显示每一步执行进展。</p>
            </div>
          )}
          <div className="inspector-foot">
            <span>记录来自服务端</span>
            <p>断线后可重新连接；任务结果与权限以当前服务端状态为准。</p>
          </div>
        </aside>
      </div>
      {edit && (
        <Modal title={edit === 'rename' ? '重命名对话' : '归档这段对话？'} onClose={() => setEdit(null)}>
          <form className="form-stack" onSubmit={editSession}>
            <ErrorBox message={error} />
            {edit === 'rename' ? (
              <Field label="对话名称">
                <input required value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
              </Field>
            ) : (
              <p>归档不会删除审计与执行事实。有未结束或待核对任务时不能归档。</p>
            )}
            <div className="form-actions">
              <Button type="button" variant="secondary" onClick={() => setEdit(null)}>
                返回
              </Button>
              <Button type="submit" variant={edit === 'archive' ? 'danger' : 'primary'} busy={busy}>
                {edit === 'rename' ? '保存' : '确认归档'}
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {citationId && (
        <Suspense fallback={<Loading label="正在打开文档引用…" />}>
          <CitationModal id={citationId} onClose={() => setCitationId(null)} />
        </Suspense>
      )}
    </div>
  );
}
