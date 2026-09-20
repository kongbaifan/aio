import type { Me, RunEvent } from './types';

const MESSAGES: Record<string, string> = {
  AUTH_REQUIRED: '登录已过期，请重新登录。',
  ADMIN_FORBIDDEN: '当前账号没有这项管理权限。',
  RESOURCE_NOT_FOUND: '内容不存在，或你没有访问权限。',
  POLICY_DENIED: '组织策略不允许此操作。',
  CSRF_DENIED: '会话验证失效，请刷新页面后重试。',
  REVISION_CONFLICT: '内容已被更新，请刷新后再保存。',
  SESSION_BUSY: '此对话还有未结束的任务，请先处理。',
  PROJECT_BUSY: '项目正在被其他任务写入，请稍后再试。',
  PROJECT_BLOCKED: '项目有未核对的执行结果，请联系管理员。',
  QUOTA_EXCEEDED: '可用额度不足，请联系管理员调整。',
  SHARED_BUDGET_EXCEEDED:
    '组织或任务所属部门的共享预算不足。不会自动换部门或透支，请联系组织管理员核对额度与预留。',
  RUN_BUDGET_EXCEEDED: '本次任务的统一预算已不足，不会额外调用模型进行汇总。',
  AGENT_BUDGET_INVALID: '任务预算不足以覆盖这个 Agent 的最低模型调用次数。',
  TEAM_NOT_ENABLED: '这个 Agent 版本尚未开放多步骤模式，请使用直接执行或联系管理员。',
  TEAM_POLICY_INVALID: '多步骤配置无法覆盖规划、执行和汇总，请管理员发布修正后的版本。',
  TEAM_PLAN_INVALID: '模型没有返回有效的受限任务计划，任务已停止，没有降级执行其他计划。',
  TEAM_TOOL_NOT_ALLOWED: '模型请求了当前步骤权限以外的工具，任务已停止。',
  TEAM_STAGE_TOOLS_FORBIDDEN: '规划或汇总阶段尝试调用工具，已被平台阻止。',
  TEAM_STEPS_INCOMPLETE: '部分步骤未完成，已保留实际步骤状态与汇总结果。',
  WORKSPACE_CHECKPOINT_INVALID: '工作区检查点未通过校验，已停止恢复，不会重新执行旧步骤。',
  WORKSPACE_CHECKPOINT_CONFLICT: '工作区交接状态已经变化，请刷新任务记录后处理。',
  WORKSPACE_CHECKPOINT_REQUIRED: '工作区尚未安全保存，不能释放执行环境后继续运行。',
  WORKSPACE_PROFILE_CHANGED: '恢复工作区不能改用其他镜像或执行配置。',
  PROCESS_STATE_LOST: '旧环境没有可用的文件检查点，或仍未确认停止，需要核对后再处理。',
  STORAGE_QUOTA_EXCEEDED: '组织或项目存储额度不足。',
  PAYLOAD_TOO_LARGE: '内容超过了大小限制。',
  TOOL_EXECUTOR_UNAVAILABLE: '这项工具尚未配置可用的隔离执行器。',
  MANAGER_UNAVAILABLE: '隔离执行服务暂时不可用。',
  MODEL_CONFIGURATION_DENIED: '模型地址或密钥引用不在部署允许列表中。',
  SANDBOX_PROFILE_DENIED: '该执行环境或超时时间未经部署管理员允许。',
  LAST_ADMIN_REQUIRED: '不能移除组织最后一位有效管理员。',
  MEMBER_EXISTS: '该身份已登记，请编辑现有成员。',
  BUDGET_BELOW_COMMITTED: '额度不能低于已使用和已预留的金额。',
  INVALID_REQUEST: '填写内容不符合要求，请检查后重试。',
  ACTION_CHANGED: '待审批的操作内容已改变，需要重新确认。',
  APPROVAL_EXPIRED: '审批已过期，不能继续批准。',
  SEPARATION_OF_DUTIES: '这项操作需要另一位已授权人员确认。',
  EXTERNAL_OUTCOME_UNKNOWN: '外部操作结果尚未确认，请勿重复执行。',
  EXECUTION_UNAVAILABLE: '需要先配置可用的隔离执行服务，不会回退到服务器本地运行。',
  SKILL_VERSION_EXISTS: '这个 Skill 名称和版本已存在。请刷新查看；内容变更需要新版本号。',
  SKILL_NOT_VALIDATED: '隔离验证和环境清理必须确认完成，才能发布这个版本。',
  REVIEWER_REQUIRED: '请选择另一位有效的组织管理员作为审核人。',
  SKILL_STATE_CONFLICT: 'Skill 状态已改变，请刷新后选择当前允许的操作。',
  SKILL_STORAGE_QUOTA: '组织 Skill 存储额度不足，请联系部署管理员。',
  SKILL_VALIDATION_QUOTA: '这个固定版本已达到验证次数上限，请检查后以新版本提交。',
  SKILL_UNAVAILABLE: 'Skill 尚未发布、已停用，或使用权限已改变。',
  SKILL_COMMAND_TOO_LARGE: '代码与参数超过单次隔离调用的字节限制，请精简能力包。',
  INVALID_TOOL_SCHEMA: '输入输出 schema 超过受支持的有界规范，不能使用递归或回溯正则校验。',
  CONNECTOR_UNAVAILABLE: '独立连接器网关暂时不可用，不会回退到服务器本地执行。',
  CONNECTOR_ENDPOINT_CHANGED: '这个端点已改变或不在操作员允许列表中，请联系管理员。',
  CONNECTION_SELECTION_REQUIRED: '请为此 Agent 选择一个已通过检测的个人或部门连接。',
  CONNECTION_UNAVAILABLE: '连接未通过检测、凭据已失效或使用权限已变化。',
  CONNECTION_IDENTITY_CHANGED: '连接身份已更换。旧任务不能使用新凭据继续，也不能复用旧身份的数据。',
  CONNECTION_SCOPE_INVALID: '连接不属于这个 Agent 的服务版本或当前使用范围。',
  CREDENTIAL_PENDING: '已有凭据配置正在等待完成，请刷新后继续，或等待票据过期后重试。',
  CREDENTIAL_CONFLICT: '该凭据票据已绑定不同内容，不能覆盖。请撤销并重新创建连接。',
  CREDENTIAL_TICKET_EXPIRED: '凭据配置票据已过期，请刷新连接并重新配置。',
  MCP_AUTH_REQUIRED: '源系统未接受这个凭据，请检查只读令牌和访问范围。',
  OAUTH_REQUIRED: '这个服务需要使用已配置的 OAuth 授权流程，不能直接粘贴令牌。',
  OAUTH_SESSION_MISMATCH: '授权不是由当前登录会话发起的，请重新开始授权。',
  OAUTH_FLOW_EXPIRED: '授权窗口已过期，请从连接页面重新开始。',
  OAUTH_FLOW_USED: '这次授权意图已结束，请刷新连接状态或发起新的授权。',
  OAUTH_CALLBACK_REPLAY: '授权回调与已保存的请求不一致，已拒绝重复兑换。',
  OAUTH_ISSUER_MISMATCH: '授权服务器与已批准配置不一致，连接未被激活。',
  OAUTH_ACCESS_DENIED: '你没有同意这次外部授权，连接尚未激活。',
  OAUTH_REAUTH_REQUIRED: '外部授权已失效或刷新结果无法确认，请重新授权；不会自动重复业务操作。',
  OAUTH_SCOPE_MISMATCH: '源系统返回的权限范围与批准范围不一致，已停止接入。',
  OAUTH_GATEWAY_RESPONSE_INVALID: '授权地址或回执不符合部署配置，已阻止跳转。',
  OAUTH_CALLBACK_CONFIGURATION_INVALID: '管理员登记的回调地址不属于当前平台，请联系部署人员。',
  STDIO_EXECUTOR_UNAVAILABLE: '尚未配置专属 MCP stdio 执行器，不会改在服务器宿主运行。',
  STDIO_INPUT_QUOTA_EXCEEDED: '隔离 MCP 的附件上限为 32 个、合计 4 MiB。请减少本次所选文件后重新创建任务。',
  STDIO_INPUT_STORAGE_UNAVAILABLE: '隔离 MCP 的私有附件存储尚未配置，不会改为读取服务器目录。',
  STDIO_INPUT_MANIFEST_MISMATCH: '本次任务的附件清单或授权已变化，未继续传递文件。',
  SKILL_RUNTIME_REQUIRED: '请为此能力包选择操作员已批准的签名依赖环境。',
  SKILL_IMPORT_UNAVAILABLE: '归档扫描环境或私有存储尚未配置，不会退回宿主解压。',
  SKILL_IMPORT_PROFILE_UNAVAILABLE: '导入时固定的批准环境已不可用，请联系运维。',
  SKILL_IMPORT_CANCELLED: '归档导入已取消，正在保留或确认安全清理状态。',
  SKILL_IMPORT_EXPIRED: '归档上传或等待扫描已过期，请查看原记录后创建新导入。',
  SKILL_IMPORT_QUOTA: '原始归档隔离区已达到数量或存储上限，请先清理不再需要的归档。',
  SKILL_IMPORT_PACKAGE_INVALID: '归档元数据不符合 Skill 包规范，请核对入口、引用、测试和依赖声明。',
  SKILL_IMPORT_RESULT_INVALID: '隔离扫描结果未通过完整性验证，未创建 Skill。',
  SKILL_IMPORT_UNCONFIRMED: '导入结果尚未确认，不会自动发布或重新执行原动作。',
  SKILL_IMPORT_INTERRUPTED: '导入工作进程中断；先等待环境清理，再重新提交需要的归档。',
  ARCHIVE_UPLOAD_MISMATCH: '上传字节与预先固定的大小或 SHA-256 不一致。',
  ARCHIVE_PATH_INVALID: '归档含越界、隐藏配置、控制字符或不规范路径。',
  ARCHIVE_ROOT_INVALID: '请上传单个 Skill：根目录或唯一一层目录内应有 skill.json 或 SKILL.md。',
  ARCHIVE_MEMBER_CONFLICT: '归档包含重复路径、大小写别名或文件/目录冲突。',
  ARCHIVE_NODE_INVALID: '归档不能包含链接、设备、稀疏文件或加密成员。',
  ARCHIVE_FILE_TYPE_DENIED: '当前导入接受 UTF-8 文本 Skill；不接收二进制资产。',
  ARCHIVE_EXPANSION_LIMIT: '归档展开大小或压缩比例超过安全上限。',
  ARCHIVE_PACKAGE_LIMIT: '展开后的能力包超过 256 KiB，请减少内容或引用。',
  ARCHIVE_FILE_LIMIT: '归档文件数量或单文件大小超过能力包限制。',
  ARCHIVE_REFERENCE_LIMIT: '原生文件夹引用数量或大小超限，请用 skill.json 明确声明需要的引用。',
  ARCHIVE_INVALID: '隔离解析器拒绝了归档；请检查格式、内容和目录结构。',
  ARCHIVE_METADATA_CONFLICT: 'skill.json 不应包含内联 files，原生文件夹模式也不能同时包含该描述文件。',
  ARCHIVE_TRAILING_DATA: '归档含未声明的前后附加数据或不支持的包装格式。',
  CREDENTIAL_SHAPED_CONTENT: '包中检测到疑似凭据，请移除真实密钥并经人工复核。',
  SKILL_RUNTIME_MISMATCH: '能力包固定的环境摘要与所选镜像不一致，不能自动换环境。',
  SKILL_DEPENDENCY_MISMATCH: '能力包要求的精确依赖版本不在所选环境中，请选择匹配环境或发布新版本。',
  RUNTIME_PROFILE_WITHDRAWN: '运行时批准已撤回，后续执行被阻止；不会改用宿主 Python。',
  AGENT_RUNTIME_CONFLICT: '当前任务共享一个主计算工作区，所选计算工具与 Skill 必须使用同一固定环境。',
  STDIO_SESSION_LOST: 'MCP 进程状态已丢失，不能自动重启后重放原操作。',
  STDIO_CLEANUP_UNCONFIRMED: 'MCP 进程尚未确认停止，执行记录将保持待核对状态。',
  STDIO_NODE_MISMATCH: 'MCP 执行单元不属于当前节点，已阻止跨节点错误接管。',
  MCP_TOOL_DEFINITION_CHANGED: '远端工具定义与已批准版本不一致，已停止调用，请管理员审核新版本。',
  MCP_TOOL_NOT_APPROVED: '这个工具不在操作员允许的只读操作列表中。',
  MCP_READONLY_REQUIRED: '发布前必须确认源系统账号具备真正的只读权限。',
  PERSONAL_CREDENTIAL_SHARING_DENIED: '不能把个人令牌分享给其他账号。请配置明确的部门服务身份。',
  PARSER_PROFILE_UNAVAILABLE: '文档解析环境未获部署允许，不能改在服务器本地解析。',
  KNOWLEDGE_STORAGE_UNAVAILABLE: '知识库存储或隔离解析服务尚未配置。',
  KNOWLEDGE_SOURCE_CHANGED: '引用文档已更新、删除或权限已改变，旧来源不能继续使用。',
  DOCUMENT_ACCESS_DENIED: '当前没有读取这个文档的权限。',
  DOCUMENT_BUSY: '已有文档版本正在摄取，请等待完成或处理失败任务。',
  DOCUMENT_FORMAT_UNSUPPORTED: '当前不支持这个文档格式。',
  DOCUMENT_ACTIVE_CONTENT: '文档包含不允许的宏、脚本或嵌入活动内容。',
  DOCUMENT_NO_EXTRACTABLE_TEXT: '文档没有可提取文本；扫描图片 PDF 暂无 OCR，请提供文本版本。',
  DOCUMENT_PARSE_FAILED: '文档未通过隔离解析，请检查格式或导出为支持的文本格式。',
  DOCUMENT_ARCHIVE_LIMIT: '文档解压大小或压缩比例超过安全上限。',
  DOCUMENT_ENCODING_UNSUPPORTED: '请将文本或 CSV 导出为 UTF-8 编码。',
  INGESTION_RETRY_BLOCKED: '请先确认环境清理和未知请求状态，再重试摄取。',
  EMBEDDING_OUTCOME_UNKNOWN: '嵌入请求的结果或费用尚未确认，系统不会自动重新请求。',
  EMBEDDING_DIMENSION_MISMATCH: '返回向量维度与固定模型配置不一致，索引不会被发布。',
  EMBEDDING_RESULT_UNAVAILABLE: '混合检索没有可用的获权向量结果，未静默降级为其他检索。',
  EMBEDDING_RETRY_BLOCKED: '该嵌入请求已发送或需要核对，不能盲目重复计费请求。',
};
export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    public requestId = '',
    message?: string,
  ) {
    super(MESSAGES[code] ?? message ?? '请求未完成，请稍后重试。');
    this.name = 'ApiError';
  }
}
export class StaleResponseError extends Error {
  constructor() {
    super('Discarded a response from an obsolete identity');
    this.name = 'StaleResponseError';
  }
}
export function isAbort(error: unknown): boolean {
  return error instanceof StaleResponseError || (error instanceof Error && error.name === 'AbortError');
}
export function explain(error: unknown): string {
  return error instanceof ApiError ? error.message : '连接暂时不可用。操作是否完成请以服务端状态为准。';
}

export class ApiClient extends EventTarget {
  private epoch = 0;
  private identity = '';
  private csrf = '';
  private controllers = new Set<AbortController>();
  bind(me: Me) {
    const identity = `${me.org_id}:${me.user_id}`;
    if (identity !== this.identity) {
      this.invalidate();
      this.identity = identity;
    }
    this.csrf = me.csrf_token;
  }
  invalidate() {
    this.epoch++;
    this.identity = '';
    this.csrf = '';
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
  }
  private async open(
    path: string,
    method: string,
    data?: unknown,
    options: { signal?: AbortSignal; body?: BodyInit; headers?: HeadersInit } = {},
  ) {
    if (!path.startsWith('/api/') && !path.startsWith('/auth/'))
      throw new Error('API path must be same-origin');
    const epoch = this.epoch;
    const controller = new AbortController();
    this.controllers.add(controller);
    const abort = () => controller.abort();
    if (options.signal?.aborted) abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    const headers = new Headers(options.headers);
    if (!['GET', 'HEAD'].includes(method)) headers.set('X-CSRF-Token', this.csrf);
    let body = options.body;
    if (data !== undefined) {
      headers.set('Content-Type', 'application/json');
      body = JSON.stringify(data);
    }
    const cleanup = () => {
      this.controllers.delete(controller);
      options.signal?.removeEventListener('abort', abort);
    };
    try {
      const response = await fetch(path, {
        method,
        body,
        headers,
        credentials: 'same-origin',
        signal: controller.signal,
        cache: 'no-store',
      });
      if (epoch !== this.epoch) throw new StaleResponseError();
      if (!response.ok) {
        let error: { code?: string; request_id?: string } = {};
        try {
          error = (await response.json()).error ?? {};
        } catch {
          /* Do not expose raw HTML/tracebacks. */
        }
        if (epoch !== this.epoch) throw new StaleResponseError();
        if (response.status === 401) {
          this.invalidate();
          this.dispatchEvent(new Event('auth-lost'));
        }
        throw new ApiError(error.code ?? 'REQUEST_FAILED', response.status, error.request_id);
      }
      return { response, cleanup, current: () => epoch === this.epoch };
    } catch (error) {
      cleanup();
      throw error;
    }
  }
  async request<T>(
    path: string,
    method = 'GET',
    data?: unknown,
    options: { signal?: AbortSignal; body?: BodyInit; headers?: HeadersInit } = {},
  ): Promise<T> {
    const { response, cleanup, current } = await this.open(path, method, data, options);
    try {
      const result: unknown = response.status === 204 ? null : await response.json();
      if (!current()) throw new StaleResponseError();
      return result as T;
    } finally {
      cleanup();
    }
  }
  async download(path: string, filename: string, signal?: AbortSignal) {
    const { response, cleanup, current } = await this.open(path, 'GET', undefined, { signal });
    try {
      const blob = await response.blob();
      if (!current()) throw new StaleResponseError();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.rel = 'noopener';
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } finally {
      cleanup();
    }
  }
  async events(runId: string, after: number, signal: AbortSignal, onEvent: (event: RunEvent) => void) {
    const { response, cleanup, current } = await this.open(
      `/api/v2/runs/${encodeURIComponent(runId)}/events`,
      'GET',
      undefined,
      { signal, headers: { 'Last-Event-ID': `${runId}:${after}` } },
    );
    try {
      if (!response.body) throw new ApiError('STREAM_UNAVAILABLE', 502);
      await parseEvents(
        response.body,
        runId,
        after,
        (event) => {
          if (!current()) throw new StaleResponseError();
          onEvent(event);
        },
        signal,
      );
    } finally {
      cleanup();
    }
  }
}

export async function parseEvents(
  stream: ReadableStream<Uint8Array>,
  runId: string,
  after: number,
  emit: (event: RunEvent) => void,
  signal?: AbortSignal,
) {
  const reader = stream.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '',
    last = after;
  const abort = () => {
    void reader.cancel();
  };
  signal?.addEventListener('abort', abort, { once: true });
  try {
    while (!signal?.aborted) {
      const item = await reader.read();
      if (item.done) break;
      buffer += decoder.decode(item.value, { stream: true });
      if (buffer.length > 1024 * 1024) throw new ApiError('STREAM_FRAME_TOO_LARGE', 502);
      for (;;) {
        const match = /\r?\n\r?\n/.exec(buffer);
        if (!match) break;
        const frame = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const lines = frame.split(/\r?\n/);
        const data = lines
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).trimStart())
          .join('\n');
        if (!data) continue;
        const payload: unknown = JSON.parse(data);
        if (!payload || typeof payload !== 'object') throw new ApiError('STREAM_PROTOCOL_INVALID', 502);
        const obj = payload as {
          schema_version?: unknown;
          run_id?: unknown;
          seq?: unknown;
          timestamp?: unknown;
          payload?: unknown;
        };
        if (
          obj.schema_version !== 1 ||
          obj.run_id !== runId ||
          typeof obj.seq !== 'number' ||
          !Number.isSafeInteger(obj.seq) ||
          obj.seq < 1 ||
          typeof obj.timestamp !== 'string' ||
          !obj.payload ||
          typeof obj.payload !== 'object' ||
          Array.isArray(obj.payload)
        )
          throw new ApiError('STREAM_PROTOCOL_INVALID', 502);
        if (obj.seq <= last) continue;
        if (obj.seq !== last + 1) throw new ApiError('STREAM_CURSOR_GAP', 409);
        const id = lines
          .find((l) => l.startsWith('id:'))
          ?.slice(3)
          .trim();
        if (id !== `${runId}:${obj.seq}`) throw new ApiError('STREAM_PROTOCOL_INVALID', 502);
        const kind = lines
          .find((l) => l.startsWith('event:'))
          ?.slice(6)
          .trim();
        if (!kind || kind.length > 64) throw new ApiError('STREAM_PROTOCOL_INVALID', 502);
        last = obj.seq;
        emit({
          run_id: runId,
          seq: obj.seq,
          kind,
          timestamp: obj.timestamp,
          payload: obj.payload as Record<string, unknown>,
        });
      }
    }
    decoder.decode();
  } finally {
    signal?.removeEventListener('abort', abort);
    try {
      await reader.cancel();
    } catch {
      /* stream already closed */
    }
    reader.releaseLock();
  }
}
export const api = new ApiClient();
