import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Cable,
  CheckCircle2,
  KeyRound,
  PlugZap,
  Plus,
  RefreshCw,
  ShieldCheck,
  Unplug,
  Users,
} from 'lucide-react';
import { api, ApiError, explain } from '../api/client';
import type {
  AdminOptions,
  Directory,
  MCPConnection,
  MCPConnectionCreateRequest,
  MCPCredentialPrepareRequest,
  MCPCredentialUploadRequest,
  MCPDiscovery,
  MCPServerCreateRequest,
  MCPServerPublishRequest,
  MCPServerVersion,
  Page,
} from '../api/types';
import { useAuth } from '../auth';
import { formatDate, shortId, useResource } from '../hooks';
import { Button, Empty, ErrorBox, Field, Loading, Modal, Notice, PageTitle } from '../components/ui';

const STATE: Record<MCPConnection['state'], string> = {
  pending: '等待连接检测',
  active: '已通过连接检测',
  reauth_required: '需要重新授权',
  revoked: '已撤销',
};

export function MCPAdmin() {
  const { me } = useAuth();
  const servers = useResource<Page<MCPServerVersion>>('/api/v2/admin/mcp/servers');
  const options = useResource<AdminOptions>('/api/v2/admin/options');
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', version: '1.0.0', endpoint_id: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.request('/api/v2/admin/mcp/servers', 'POST', form satisfies MCPServerCreateRequest);
      servers.reload();
      setOpen(false);
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="admin-section">
      <div className="section-top">
        <div>
          <h2>MCP 服务版本</h2>
          <p>统一配置工具定义，使用者各自连接身份。发布一个服务不代表共享发布人的令牌。</p>
        </div>
        <Button
          disabled={!me?.capabilities.mcp || !options.data?.connector_endpoints?.length}
          onClick={() => {
            setForm({
              name: '',
              version: '1.0.0',
              endpoint_id: options.data?.connector_endpoints?.[0]?.id ?? '',
            });
            setOpen(true);
          }}
        >
          <Plus size={16} />
          登记 MCP 服务
        </Button>
      </div>
      <Notice>
        支持 Streamable HTTP（2025-06-18）及配置后的专属 stdio 容器。stdio 当前无网络，不能在宿主机启动程序。
        真实外部写仍未启用；工具的 readOnly 注解不代替源系统权限。
      </Notice>
      {!me?.capabilities.mcp && (
        <Notice>需要先部署独立连接器网关并配置允许端点；不会改用 API 进程运行第三方 MCP 或任意命令。</Notice>
      )}
      <ErrorBox message={error || servers.error || options.error} retry={servers.reload} />
      {servers.loading ? (
        <Loading />
      ) : !servers.data?.items.length ? (
        <Empty title="先登记一个受控服务">
          操作员在部署配置中批准真实端点和工具名称，然后在这里发现、检查并发布具体版本。
        </Empty>
      ) : (
        <div className="skill-catalog">
          {servers.data.items.map((server) => (
            <article className="skill-card" key={server.id}>
              <header>
                <span className="skill-icon">
                  <Cable size={22} />
                </span>
                <div>
                  <h3>{server.name}</h3>
                  <small>
                    v{server.version} · {server.endpoint_id}
                  </small>
                </div>
                <span className={`skill-state skill-state-${server.state}`}>
                  {server.state === 'published' ? '已发布' : '待发现与审核'}
                </span>
              </header>
              <div className="connection-endpoint">
                <code>{server.endpoint_url ?? '此端点已被操作员撤回'}</code>
                <small>
                  {server.published_tools.length} 个固定工具 · {formatDate(server.created_at)}
                </small>
              </div>
              <footer>
                <Link className="button button-secondary" to={`/app/connections?server=${server.id}`}>
                  <PlugZap size={15} />
                  配置身份与发现工具
                </Link>
              </footer>
            </article>
          ))}
        </div>
      )}
      {open && (
        <Modal
          title="登记 MCP 服务版本"
          description="仅可选择部署批准的端点。不接受任意 URL、启动命令、环境变量或宿主路径。"
          onClose={() => setOpen(false)}
        >
          <form className="form-stack" onSubmit={create}>
            <ErrorBox message={error} />
            <Field label="服务名称">
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
            <Field label="操作员允许端点">
              <select
                required
                value={form.endpoint_id}
                onChange={(e) => setForm({ ...form, endpoint_id: e.target.value })}
              >
                <option value="">请选择…</option>
                {options.data?.connector_endpoints?.map((endpoint) => (
                  <option key={endpoint.id} value={endpoint.id}>
                    {endpoint.id} · {endpoint.url}
                  </option>
                ))}
              </select>
            </Field>
            <div className="form-actions">
              <Button busy={busy} type="submit">
                保存服务草稿
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}

export function ConnectionsPage() {
  const { me } = useAuth();
  const [params] = useSearchParams();
  const connections = useResource<Page<MCPConnection>>('/api/v2/connections');
  const servers = useResource<Page<MCPServerVersion>>(
    me?.permissions.organization_admin ? '/api/v2/admin/mcp/servers' : '/api/v2/mcp/servers',
  );
  const [creating, setCreating] = useState(false);
  const [credential, setCredential] = useState<MCPConnection | null>(null);
  const [revoke, setRevoke] = useState<MCPConnection | null>(null);
  const [discovery, setDiscovery] = useState<{ server: MCPServerVersion; result: MCPDiscovery } | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const names = new Map(servers.data?.items.map((s) => [s.id, s]));
  const refresh = () => {
    connections.reload();
    servers.reload();
  };
  async function discover(connection: MCPConnection) {
    setBusy(connection.id);
    setError('');
    try {
      const result = await api.request<MCPDiscovery>(
        `/api/v2/connections/${connection.id}/discover`,
        'POST',
        { request_id: crypto.randomUUID() },
      );
      const server = names.get(connection.server_id);
      if (server) setDiscovery({ server, result });
      refresh();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy('');
    }
  }
  async function revokeConnection() {
    if (!revoke) return;
    setBusy(revoke.id);
    setError('');
    try {
      await api.request(`/api/v2/connections/${revoke.id}`, 'DELETE');
      setRevoke(null);
      refresh();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy('');
    }
  }
  return (
    <div className="page">
      <PageTitle
        eyebrow="CONNECTED CAPABILITIES"
        title="我的连接"
        description="接入自己的源系统身份，或使用部门明确配置的服务身份。凭据仅存入独立网关，不交给模型或计算沙箱。"
      />
      <div className="section-top">
        <p className="muted">个人连接不可通过分享 Agent 转给别人。部门连接由组织管理员配置与维护。</p>
        <Button
          disabled={!me?.capabilities.mcp || !servers.data?.items.some((s) => s.endpoint_available)}
          onClick={() => setCreating(true)}
        >
          <Plus size={16} />
          添加连接
        </Button>
      </div>
      {!me?.capabilities.mcp && (
        <Notice>连接器服务尚未配置或已关闭。已有连接可撤销；不会使用宿主机命令作为替代执行器。</Notice>
      )}
      <ErrorBox message={error || connections.error || servers.error} retry={refresh} />
      {params.get('oauth') && <Notice>已返回授权页面。是否连接成功，请以下方服务端检测状态为准。</Notice>}
      {params.get('oauth_error') && (
        <ErrorBox message={explain(new ApiError(params.get('oauth_error')!, 409))} />
      )}
      {connections.loading ? (
        <Loading label="正在读取你的连接…" />
      ) : !connections.data?.items.length ? (
        <Empty title="还没有配置连接">
          管理员发布 MCP 服务后，你可以使用自己的只读凭据连接。没有可选服务时请联系管理员。
        </Empty>
      ) : (
        <div className="skill-catalog">
          {connections.data.items.map((connection) => {
            const server = names.get(connection.server_id);
            const canManage =
              connection.owner_id === me?.user_id ||
              (connection.scope === 'department' && me?.permissions.organization_admin);
            return (
              <article className="skill-card" key={connection.id}>
                <header>
                  <span className="skill-icon">
                    {connection.scope === 'personal' ? <KeyRound size={22} /> : <Users size={22} />}
                  </span>
                  <div>
                    <h3>{connection.name}</h3>
                    <small>
                      {server?.name ?? shortId(connection.server_id)} ·{' '}
                      {connection.scope === 'personal' ? '个人身份，不共享凭据' : '部门服务身份'}
                    </small>
                  </div>
                  <span
                    className={`skill-state skill-state-${connection.state === 'active' ? 'published' : connection.state === 'revoked' ? 'rejected' : 'draft'}`}
                  >
                    {STATE[connection.state]}
                  </span>
                </header>
                <div className="connection-endpoint">
                  <code>{server?.endpoint_url ?? '端点不可用或尚未授权'}</code>
                  <small>凭据身份版本 {connection.credential_revision} · 不显示令牌原文</small>
                  {server?.transport === 'stdio' && (
                    <small>
                      专属 stdio 进程 · 无网络 · 不与其他用户共享 HOME /
                      工作目录。该进程及同单元代码可读取注入的凭据。
                      {server.stdio?.input_policy === 'run_attachments' &&
                        ' 本模板允许附件输入，但还需要使用者在每次任务中单独勾选；仅复制所选附件（合计不超过 4 MiB）。'}
                    </small>
                  )}
                  {connection.authorization && (
                    <small>
                      OAuth：{connection.authorization.issuer} ·{' '}
                      {connection.authorization.subject ?? '源系统授权标识，未提供可验证的用户 ID'}
                    </small>
                  )}
                  {connection.credential_cleanup && (
                    <small>
                      {
                        {
                          pending: '平台已拒绝调用，凭据清理中',
                          local: '平台凭据已清理；源系统令牌需单独撤销',
                          confirmed: '授权服务器已确认令牌撤销',
                          unsupported: '平台凭据已清理；源系统不支持自动撤销',
                          unknown: '平台已断开；请在源系统核对未确认的授权',
                        }[connection.credential_cleanup]
                      }
                    </small>
                  )}
                </div>
                <footer>
                  {connection.state !== 'revoked' && (
                    <>
                      {canManage && (
                        <Button
                          variant="secondary"
                          disabled={!me?.capabilities.mcp || !server?.endpoint_available}
                          onClick={() => setCredential(connection)}
                        >
                          <KeyRound size={15} />
                          {server?.authentication === 'oauth2'
                            ? connection.credential_revision
                              ? '重新 OAuth 授权'
                              : '使用 OAuth 授权'
                            : connection.credential_revision
                              ? '更换凭据'
                              : '配置凭据'}
                        </Button>
                      )}
                      <Button
                        variant="quiet"
                        busy={busy === connection.id}
                        disabled={!connection.credential_revision || !me?.capabilities.mcp}
                        onClick={() => void discover(connection)}
                      >
                        <RefreshCw size={15} />
                        检测并发现工具
                      </Button>
                      {canManage && (
                        <Button variant="quiet" onClick={() => setRevoke(connection)}>
                          <Unplug size={15} />
                          撤销连接
                        </Button>
                      )}
                    </>
                  )}
                </footer>
              </article>
            );
          })}
        </div>
      )}
      {creating && (
        <CreateConnection
          servers={servers.data?.items ?? []}
          preferred={params.get('server')}
          onClose={() => setCreating(false)}
          onCreated={(row) => {
            setCreating(false);
            refresh();
            setCredential(row);
          }}
        />
      )}
      {credential && names.get(credential.server_id)?.authentication === 'oauth2' ? (
        <OAuthModal
          connection={credential}
          server={names.get(credential.server_id)!}
          onClose={() => {
            setCredential(null);
            refresh();
          }}
        />
      ) : (
        credential && (
          <CredentialModal
            connection={credential}
            server={names.get(credential.server_id)}
            onClose={() => {
              setCredential(null);
              refresh();
            }}
            onConnected={(result) => {
              const server = names.get(credential.server_id);
              setCredential(null);
              refresh();
              if (server) setDiscovery({ server, result });
            }}
          />
        )
      )}
      {discovery && (
        <DiscoveryModal
          server={discovery.server}
          discovery={discovery.result}
          onClose={() => {
            setDiscovery(null);
            refresh();
          }}
        />
      )}
      {revoke && (
        <Modal
          title="撤销这个连接？"
          description="平台会立即拒绝新调用，相关连接来源的任务和产物也可能不再可读。网关凭据在后台删除；这不等于已在源系统撤销令牌。"
          onClose={() => setRevoke(null)}
        >
          <p>
            <strong>{revoke.name}</strong> · {revoke.scope === 'personal' ? '个人连接' : '整个部门的服务身份'}
          </p>
          <div className="form-actions">
            <Button variant="secondary" onClick={() => setRevoke(null)}>
              保留连接
            </Button>
            <Button variant="danger" busy={busy === revoke.id} onClick={() => void revokeConnection()}>
              确认撤销连接
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function CreateConnection({
  servers,
  preferred,
  onClose,
  onCreated,
}: {
  servers: MCPServerVersion[];
  preferred: string | null;
  onClose: () => void;
  onCreated: (row: MCPConnection) => void;
}) {
  const { me } = useAuth();
  const directory = useResource<Directory>(me?.permissions.organization_admin ? '/api/v2/directory' : null);
  const [form, setForm] = useState<MCPConnectionCreateRequest>({
    name: '',
    server_id: servers.some((s) => s.id === preferred) ? preferred! : (servers[0]?.id ?? ''),
    scope: 'personal',
    department_id: null,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const server = servers.find((s) => s.id === form.server_id);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const row = await api.request<MCPConnection>('/api/v2/connections', 'POST', form);
      onCreated(row);
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="添加 MCP 连接"
      description="连接定义与具体账号分开管理。不会自动使用发布人的个人凭据。"
      onClose={onClose}
    >
      <form className="form-stack" onSubmit={submit}>
        <ErrorBox message={error || directory.error} />
        <Field label="连接名称">
          <input
            required
            maxLength={100}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </Field>
        <Field label="已批准的 MCP 服务版本">
          <select
            required
            value={form.server_id}
            onChange={(e) => setForm({ ...form, server_id: e.target.value })}
          >
            <option value="">请选择…</option>
            {servers.map((s) => (
              <option key={s.id} value={s.id} disabled={!s.endpoint_available}>
                {s.name} · v{s.version} {s.state === 'draft' ? '（待审核草稿）' : ''}
              </option>
            ))}
          </select>
        </Field>
        <div className="connection-destination">
          <ShieldCheck size={18} />
          <div>
            <strong>固定目标地址</strong>
            <code>{server?.endpoint_url ?? '未选择可用服务'}</code>
          </div>
        </div>
        {me?.permissions.organization_admin && (
          <Field label="身份使用范围">
            <select
              value={form.scope}
              onChange={(e) =>
                setForm({
                  ...form,
                  scope: e.target.value as 'personal' | 'department',
                  department_id: e.target.value === 'personal' ? null : '',
                })
              }
            >
              <option value="personal">我的个人身份</option>
              <option value="department">明确共享的部门服务身份</option>
            </select>
          </Field>
        )}
        {form.scope === 'department' && (
          <>
            <Notice>
              部门成员将共同使用这个服务账号。请使用专门的只读服务凭据，不要把个人账号借给整个部门。
            </Notice>
            <Field label="共享部门">
              <select
                required
                value={form.department_id ?? ''}
                onChange={(e) => setForm({ ...form, department_id: e.target.value })}
              >
                <option value="">请选择…</option>
                {directory.data?.departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}
        <div className="form-actions">
          <Button type="submit" busy={busy} disabled={!server?.endpoint_available}>
            创建连接
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function OAuthModal({
  connection,
  server,
  onClose,
}: {
  connection: MCPConnection;
  server: MCPServerVersion;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [url, setUrl] = useState('');
  const requestId = useRef(crypto.randomUUID());
  const policy = server.oauth;
  async function start() {
    setBusy(true);
    setError('');
    try {
      if (!policy) throw new ApiError('OAUTH_CALLBACK_CONFIGURATION_INVALID', 409);
      const result = await api.request<{ authorization_url: string }>(
        `/api/v2/connections/${connection.id}/oauth`,
        'POST',
        {
          expected_revision: connection.resource_revision,
          request_id: requestId.current,
        } satisfies MCPCredentialPrepareRequest,
      );
      const received = new URL(result.authorization_url),
        expected = new URL(policy.authorization_endpoint);
      if (
        received.origin !== expected.origin ||
        received.pathname !== expected.pathname ||
        received.hash ||
        received.username ||
        received.password
      ) {
        throw new ApiError('OAUTH_GATEWAY_RESPONSE_INVALID', 502);
      }
      setUrl(result.authorization_url);
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="授权 MCP 连接"
      onClose={onClose}
      description="只在批准的源系统页面授权。平台登录令牌不会透传；access/refresh token 不进入浏览器或模型。"
    >
      <p>
        <strong>{connection.name}</strong> ·{' '}
        {connection.scope === 'personal' ? '仅此个人连接' : '部门服务身份，请使用专用账号'}
      </p>
      <p className="muted">授权服务器：{policy?.issuer ?? '尚未配置'}</p>
      <p>请求的最小权限：{policy?.scopes.join('、') ?? '未配置'}</p>
      <ErrorBox message={error} />
      <div className="form-actions">
        <Button variant="secondary" onClick={onClose}>
          返回
        </Button>
        {url ? (
          <a className="button button-primary" href={url} rel="noreferrer">
            前往授权服务器
          </a>
        ) : (
          <Button busy={busy} disabled={!policy} onClick={() => void start()}>
            生成安全授权链接
          </Button>
        )}
      </div>
    </Modal>
  );
}

function CredentialModal({
  connection,
  server,
  onClose,
  onConnected,
}: {
  connection: MCPConnection;
  server?: MCPServerVersion;
  onClose: () => void;
  onConnected: (result: MCPDiscovery) => void;
}) {
  const [secret, setSecret] = useState('');
  const [revision, setRevision] = useState(connection.resource_revision);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const requestId = useRef(crypto.randomUUID());
  const binding = useRef<string | null>(null);
  const anonymous = server?.authentication === 'none';
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      if (!binding.current) {
        const body: MCPCredentialPrepareRequest = {
          expected_revision: revision,
          request_id: requestId.current,
        };
        const prepared = await api.request<{ binding_id: string }>(
          `/api/v2/connections/${connection.id}/credentials`,
          'POST',
          body,
        );
        binding.current = prepared.binding_id;
      }
      const body: MCPCredentialUploadRequest = { secret: anonymous ? '' : secret };
      const updated = await api.request<MCPConnection>(
        `/api/v2/connections/${connection.id}/credentials/${binding.current}`,
        'PUT',
        body,
      );
      setRevision(updated.resource_revision);
      binding.current = null;
      requestId.current = crypto.randomUUID();
      setSecret('');
      const result = await api.request<MCPDiscovery>(
        `/api/v2/connections/${connection.id}/discover`,
        'POST',
        { request_id: crypto.randomUUID() },
      );
      onConnected(result);
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
      setSecret('');
    }
  }
  return (
    <Modal
      title={anonymous ? '检测匿名连接' : '配置 MCP 凭据'}
      description="凭据通过平台转交独立加密网关，不写入平台数据库、浏览器本地存储、模型上下文或计算沙箱。"
      onClose={onClose}
    >
      <form className="form-stack" onSubmit={submit}>
        {server?.transport === 'stdio' && (
          <Notice>
            此凭据将短期注入专属 MCP
            进程。该进程及同执行单元代码能够读取它；请只使用最小范围凭据。当前执行单元无网络，不会在宿主运行。
          </Notice>
        )}
        <ErrorBox message={error} />
        <div className="connection-destination">
          <KeyRound size={18} />
          <div>
            <strong>
              {connection.name} · {connection.scope === 'personal' ? '仅我的身份' : '部门共享服务身份'}
            </strong>
            <code>{server?.endpoint_url ?? '目标不可用'}</code>
          </div>
        </div>
        {connection.credential_revision > 0 && (
          <Notice>
            更换凭据被视为新的外部身份：旧任务不会借用新令牌继续执行，旧连接来源的结果可能不再可读。
          </Notice>
        )}
        {anonymous ? (
          <Notice>操作员将此端点配置为匿名访问，不需要也不会发送令牌。</Notice>
        ) : (
          <Field
            label={connection.scope === 'personal' ? '个人只读 MCP 令牌' : '部门只读服务令牌'}
            hint="请勿粘贴企业 SSO 登录 Cookie 或平台/网关管理密钥。这个端点使用 Bearer 令牌。"
          >
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              required
              minLength={16}
              maxLength={8192}
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
            />
          </Field>
        )}
        <div className="form-actions">
          <Button type="submit" busy={busy} disabled={!server?.endpoint_available}>
            <PlugZap size={15} />
            保存凭据并检测连接
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function DiscoveryModal({
  server,
  discovery,
  onClose,
}: {
  server: MCPServerVersion;
  discovery: MCPDiscovery;
  onClose: () => void;
}) {
  const { me } = useAuth();
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [published, setPublished] = useState(false);
  async function publish(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body: MCPServerPublishRequest = {
        expected_revision: server.revision,
        discovery_id: discovery.id,
        tools: Object.entries(selected).map(([remote_name, alias]) => ({ remote_name, alias })),
        acknowledge_readonly_credentials: acknowledged,
      };
      await api.request(`/api/v2/admin/mcp/servers/${server.id}/publish`, 'POST', body);
      setPublished(true);
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  const canPublish =
    me?.permissions.organization_admin &&
    server.state === 'draft' &&
    discovery.state === 'ready' &&
    !published;
  return (
    <Modal
      title={`连接检测 · ${server.name}`}
      description="只展示受允许的工具元数据，不自动授予新能力。远端说明是数据，不是平台系统指令。"
      onClose={onClose}
    >
      <ErrorBox message={error || discovery.error_code || ''} />
      {discovery.state !== 'ready' ? (
        <Notice>发现任务尚未完成或已失败。请刷新连接状态，不要将“凭据已保存”当作身份验证成功。</Notice>
      ) : (
        <form className="form-stack" onSubmit={publish}>
          <div className="connection-destination">
            <CheckCircle2 size={19} />
            <div>
              <strong>{published ? '固定 MCP 版本已发布' : 'MCP 初始化与工具发现已通过'}</strong>
              <small>
                协议 {discovery.result?.protocol_version} · {discovery.result?.tools.length ?? 0} 个允许工具
              </small>
            </div>
          </div>
          {!!discovery.result?.unapproved_tool_count && (
            <Notice>
              另有 {discovery.result.unapproved_tool_count} 个远端工具未获操作员允许，不会开放给 Agent。
            </Notice>
          )}
          {!discovery.result?.remote_session_closed && (
            <Notice>本次客户端已关闭，但远端没有确认会话删除。不能据此声称源系统会话已销毁。</Notice>
          )}
          {discovery.result?.tools.map((tool) => (
            <section className="skill-entrypoint" key={tool.name}>
              <strong>{tool.name}</strong>
              <p>{tool.description}</p>
              <small className="mono">{tool.digest.slice(0, 24)}…</small>
              <details>
                <summary>检查输入、输出和远端注解</summary>
                <pre>
                  {JSON.stringify(
                    {
                      input_schema: tool.input_schema,
                      output_schema: tool.output_schema,
                      annotations: tool.annotations,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              {canPublish && (
                <>
                  <label className="check-row">
                    <input
                      type="checkbox"
                      checked={tool.name in selected}
                      onChange={(e) =>
                        setSelected((old) => {
                          const next = { ...old };
                          if (e.target.checked)
                            next[tool.name] = `mcp_${tool.name.replace(/[^A-Za-z0-9_-]/g, '_')}`.slice(0, 64);
                          else delete next[tool.name];
                          return next;
                        })
                      }
                    />
                    将这个工具加入固定发布版本
                  </label>
                  {tool.name in selected && (
                    <Field label={`Agent 工具别名 · ${tool.name}`}>
                      <input
                        required
                        pattern="[A-Za-z][A-Za-z0-9_-]{0,63}"
                        maxLength={64}
                        value={selected[tool.name]}
                        onChange={(e) => setSelected({ ...selected, [tool.name]: e.target.value })}
                      />
                    </Field>
                  )}
                </>
              )}
            </section>
          ))}
          {canPublish && (
            <>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(e) => setAcknowledged(e.target.checked)}
                />
                我已确认源系统使用只读权限；工具的 readOnly 注解不是权限证明。
              </label>
              <Button type="submit" busy={busy} disabled={!acknowledged || !Object.keys(selected).length}>
                发布选中的固定工具
              </Button>
            </>
          )}
          {(published || server.state === 'published') && (
            <Notice>
              在 Agent 管理页选择这个 MCP
              服务版本，再显式授权工具/服务依赖。使用者仍需自己的连接或已获权的部门服务连接。
            </Notice>
          )}
        </form>
      )}
    </Modal>
  );
}
