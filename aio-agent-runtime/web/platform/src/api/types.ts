import type { components } from './generated';

export type Role = 'member' | 'org_admin' | 'operator' | 'auditor';
export interface Me {
  user_id: string;
  org_id: string;
  display_name: string;
  organization_name: string;
  role: Role;
  membership_revision: number;
  csrf_token: string;
  departments: Array<{ id: string; name: string; role: string }>;
  permissions: { organization_admin: boolean; operations: boolean; audit: boolean };
  capabilities: {
    file_upload: boolean;
    python_compute: boolean;
    mcp: boolean;
    knowledge: boolean;
    skill_publishing: boolean;
    team: boolean;
  };
}
export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}
export interface Project {
  id: string;
  name: string;
  revision: number;
  head_version?: number;
  can_manage?: boolean;
}
export interface Agent {
  id: string;
  name: string;
  version: string;
  engine: string;
  digest: string;
  status?: string;
  revision?: number;
  manifest?: Manifest;
  instruction?: string;
}
export interface Manifest {
  model: { id: string; digest: string };
  tools: Tool[];
  skills?: Array<{ id: string; digest: string }>;
  mcp_servers?: Array<{ id: string; digest: string }>;
  knowledge?: Array<{ id: string }>;
  run_budget: string;
  max_rounds: number;
  team?: { max_steps: number; max_step_rounds: number } | null;
}
export interface Session {
  id: string;
  title: string;
  project_id: string;
  agent_version_id: string;
  revision: number;
  updated_at: string;
}
export interface Message {
  seq: number;
  role: 'user' | 'assistant' | 'tool';
  run_id: string;
  content: { text?: string; redacted?: boolean };
}
export interface SessionDetail extends Session {
  mcp_server_ids?: string[];
  supported_modes?: Array<'single' | 'team'>;
  messages: Message[];
  runs: Array<{ id: string; state: RunState; created_at: string; error_code?: string }>;
}
export type RunState =
  | 'queued'
  | 'preparing'
  | 'running'
  | 'waiting_approval'
  | 'persisting'
  | 'cancel_requested'
  | 'recovery_required'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'timed_out';
export interface Run {
  id: string;
  state: RunState;
  revision: number;
  generation: number;
  result: {
    answer?: string;
    partial_answer?: string;
    artifacts?: Array<{ artifact_id: string; path: string; bytes: number }>;
    citations?: Citation[];
  } | null;
  error_code: string | null;
  cleanup_state: string;
  created_at: string;
  finished_at: string | null;
  next_event_seq: number;
  mode?: 'single' | 'team';
  team?: RunTeam | null;
  workspace_checkpoint?: {
    id: string;
    state: 'preparing' | 'bound' | 'ready' | 'retiring' | 'purged';
    generation: number;
    engine_checkpoint_seq: number;
    file_count: number | null;
    bytes: number | null;
    preserved_state: 'filesystem_only';
    manager_acknowledged: boolean;
  } | null;
}
export interface RunTeam {
  stage: 'queued' | 'planning' | 'step' | 'synthesis' | 'completed' | 'stopped';
  current_step: number;
  plan_digest?: string | null;
  plan_checkpoint_seq?: number | null;
  steps: Array<{
    id: string;
    ordinal: number;
    title: string;
    task: string;
    tools: string[];
    state:
      | 'pending'
      | 'running'
      | 'succeeded'
      | 'failed'
      | 'denied'
      | 'skipped'
      | 'cancelled'
      | 'timed_out'
      | 'recovery_required';
    input_checkpoint_seq: number | null;
    output_checkpoint_seq: number | null;
    result: { answer: string; reason_codes: string[]; invocation_ids?: string[] } | null;
    started_at: string | null;
    finished_at: string | null;
  }>;
}
export interface Artifact {
  id: string;
  project_id: string;
  run_id: string | null;
  path: string;
  bytes: number;
  sha256: string;
  media_type: string;
  state: string;
  scan_state: string;
}
export interface Approval {
  id: string;
  run_id: string;
  state: string;
  revision: number;
  action_digest: string;
  expires_at: string;
  requested_by?: string;
}
export interface ApprovalDetail {
  approval_id: string;
  run_id: string;
  invocation_id: string;
  state: string;
  revision: number;
  action_digest: string;
  expires_at: string;
  summary: { tool: string; risk: string };
}
export interface Usage {
  configured: boolean;
  hard_limit: string;
  reserved: string;
  consumed: string;
  currency: string;
  unknown_calls?: number;
}
export interface Member {
  user_id: string;
  display_name: string;
  subject: string;
  role: Role;
  active: boolean;
  revision: number;
}
export interface Department {
  id: string;
  name: string;
  active: boolean;
  members: Array<{ user_id: string; display_name: string; role: string }>;
}
export interface Directory {
  members: Array<{ user_id: string; display_name: string }>;
  departments: Array<{ id: string; name: string }>;
}
export interface ResourceGrant {
  id: string;
  subject_type: 'user' | 'department';
  subject_id: string;
  action: string;
  expires_at: string | null;
}
export interface Grants {
  resource_id: string;
  kind: string;
  revision: number;
  available_actions: string[];
  items: ResourceGrant[];
}
export interface ModelConfig {
  id: string;
  provider: string;
  model: string;
  digest: string;
  published: boolean;
  status: string;
  revision: number;
  config: {
    name?: string;
    endpoint?: string;
    secret_env?: string;
    max_output_tokens?: number;
    max_call_charge?: string;
    input_price_per_million?: string;
    output_price_per_million?: string;
  };
}
export interface Tool {
  id: string;
  name: string;
  driver: string;
  risk: string;
  digest: string;
  status?: string;
  revision?: number;
  config?: {
    description?: string;
    sandbox_profile?: string;
    image_digest?: string;
    timeout_seconds?: number;
  };
  input_schema?: Record<string, unknown>;
}
export interface AdminOptions {
  connector_endpoints?: ConnectorEndpoint[];
  document_profiles?: Array<{ id: string; image_digest: string; max_timeout_seconds: number }>;
  model_allowed_origins: string[];
  model_secret_names: string[];
  sandbox_profiles: Array<{
    id: string;
    image_digest: string;
    max_timeout_seconds: number;
    runtime?: {
      manifest_digest: string;
      key_id: string;
      purpose: 'test' | 'production';
      manifest: { name: string; python: string; packages: Array<{ name: string; version: string }> };
    };
  }>;
  supported_drivers: string[];
  supported_engines: string[];
}
export interface Budget {
  id: string;
  owner_id: string;
  display_name: string;
  hard_limit: string;
  reserved: string;
  consumed: string;
  currency: string;
}
export type SharedBudgetUpdateRequest = components['schemas']['SharedBudgetUpdate'];
export interface SharedBudget {
  id: string | null;
  scope: 'organization' | 'department';
  department_id: string | null;
  display_name: string;
  currency: 'USD';
  hard_limit: string | null;
  reserved: string;
  consumed: string;
  remaining: string | null;
  warning: boolean;
  exhausted: boolean;
  revision: number;
  created_at: string | null;
  opening_consumed: string;
}
export interface AuditEvent {
  id: string;
  actor_id: string;
  action: string;
  resource_id: string;
  run_id: string | null;
  outcome: string;
  created_at: string;
}
export interface Operation {
  id: string;
  actor_id: string;
  project_id: string;
  state: RunState;
  generation: number;
  error_code: string | null;
  cleanup_state: string;
  created_at: string;
  job_state: string;
}
export interface OrganizationPolicy {
  name: string;
  policy_revision: number;
  allowed_classifications: string[];
  denied_actions: string[];
  storage_limit_bytes: number;
}
export interface RunEvent {
  run_id: string;
  seq: number;
  kind: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

// Request bodies are generated from the actual FastAPI/Pydantic schema.
// Response projections above remain explicit and are exercised by HTTP contract tests.
export type RunCreateRequest = components['schemas']['RunCreate'];
export type ModelCreateRequest = components['schemas']['ModelCreate'];
export type ToolCreateRequest = components['schemas']['ToolCreate'];
export type AgentCreateRequest = components['schemas']['AgentCreate'];
export type GrantCreateRequest = components['schemas']['GrantCreate'];
export type SkillPackageRequest = components['schemas']['SkillCreate']['package'];
export type SkillCreateRequest = components['schemas']['SkillCreate'];
export type SkillValidateRequest = components['schemas']['SkillValidate'];
export type SkillReviewRequest = components['schemas']['SkillReview'];
export type SkillArchivePrepareRequest = components['schemas']['SkillArchivePrepare'];
export type SkillArchiveRevisionRequest = components['schemas']['SkillArchiveRevision'];
export interface SkillArchiveConfig {
  available: boolean;
  formats: Array<'zip' | 'tar' | 'tar.gz'>;
  max_bytes: number;
  modes: string[];
  automatically_published: false;
}
export interface SkillArchiveImport {
  id: string;
  request_id: string;
  state:
    | 'awaiting_upload'
    | 'uploading'
    | 'queued'
    | 'leased'
    | 'stopping'
    | 'imported'
    | 'rejected'
    | 'cancelled';
  revision: number;
  archive_sha256: string;
  archive_size: number;
  archive_format: 'zip' | 'tar' | 'tar.gz';
  mode: 'manifest' | 'native_instruction_only';
  execution_profile: string;
  queue_expires_at: string;
  uploaded_at: string | null;
  created_at: string;
  finished_at: string | null;
  cleanup_state: 'pending' | 'confirmed';
  manager_acknowledged: boolean;
  error_code: string | null;
  purge_requested: boolean;
  archive_purged: boolean;
  skill_id: string | null;
  automatically_published: false;
  scan_report: { files: number; manual_source_license_review_required: true } | null;
}
export interface SkillVersion {
  id: string;
  name: string;
  version: string;
  digest: string;
  state: 'draft' | 'validating' | 'validated' | 'rejected' | 'published';
  revision: number;
  resource_status: 'active' | 'disabled';
  resource_revision: number;
  owner_id: string;
  reviewer_id: string | null;
  profile_id: string;
  image_digest: string;
  created_at: string;
  published_at: string | null;
  published_tools: Tool[];
  description?: string;
  package_schema_version?: number;
  dependencies?: Array<{ name: string; version: string }>;
  runtime_manifest_digest?: string | null;
}
export interface SkillDetail extends SkillVersion {
  package: SkillPackageRequest;
  file_manifest: Array<{ path: string; bytes: number; sha256: string }>;
  review_note: string | null;
  validations: Array<{
    id: string;
    state: 'queued' | 'leased' | 'stopping' | 'passed' | 'failed';
    cleanup_state: string;
    error_code: string | null;
    created_at: string;
    finished_at: string | null;
    results: Array<{ kind: string; passed: boolean; entrypoint?: string; case?: number }>;
  }>;
}

export interface ConnectorEndpoint {
  id: string;
  url: string;
  authentication: 'bearer' | 'none' | 'oauth2';
  oauth?: OAuthPolicy;
  transport?: 'http' | 'stdio';
  stdio?: {
    profile_id: string;
    image_digest: string;
    template_digest: string;
    credential_env?: string | null;
    network_profile?: 'none';
    input_policy?: 'none' | 'run_attachments';
  };
  digest: string;
  read_tools: string[];
  timeout_seconds: number;
}
export interface MCPServerVersion {
  id: string;
  name: string;
  version: string;
  endpoint_id: string;
  endpoint_digest: string;
  endpoint_url: string | null;
  authentication: 'bearer' | 'none' | 'oauth2' | null;
  oauth?: OAuthPolicy | null;
  transport?: 'http' | 'stdio' | null;
  stdio?: ConnectorEndpoint['stdio'] | null;
  endpoint_available: boolean;
  state: 'draft' | 'published';
  revision: number;
  digest: string | null;
  published_tools: Tool[];
  created_at: string;
}
export interface MCPConnection {
  id: string;
  server_id: string;
  name: string;
  scope: 'personal' | 'department';
  department_id: string | null;
  owner_id: string;
  state: 'pending' | 'active' | 'reauth_required' | 'revoked';
  credential_revision: number;
  resource_status: string;
  resource_revision: number;
  created_at: string;
  authorization?: { kind: 'oauth2'; issuer: string; subject: string | null; scopes: string[] } | null;
  credential_cleanup?: 'pending' | 'local' | 'confirmed' | 'unsupported' | 'unknown' | null;
}
export interface OAuthPolicy {
  issuer: string;
  authorization_endpoint: string;
  redirect_uri: string;
  client_id: string;
  scopes: string[];
  resource: string;
  require_issuer_response: boolean;
  config_digest: string;
}
export interface MCPDiscovery {
  id: string;
  state: 'running' | 'ready' | 'failed';
  error_code: string | null;
  result: {
    protocol_version: string;
    endpoint_digest: string;
    remote_session_closed: boolean;
    unapproved_tool_count: number;
    tools: Array<{
      name: string;
      description: string;
      input_schema: Record<string, unknown>;
      output_schema: Record<string, unknown> | null;
      annotations: unknown;
      digest: string;
    }>;
  } | null;
}
export type MCPServerCreateRequest = components['schemas']['ServerCreate'];
export type MCPConnectionCreateRequest = components['schemas']['ConnectionCreate'];
export type MCPCredentialPrepareRequest = components['schemas']['CredentialPrepare'];
export type MCPCredentialUploadRequest = components['schemas']['CredentialUpload'];
export type MCPServerPublishRequest = components['schemas']['ServerPublish'];

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  embedding_model_id: string | null;
  profile_id: string;
  image_digest: string;
  tool_id: string;
  index_revision: number;
  storage_limit_bytes: number;
  created_at: string;
  can_manage?: boolean;
  retrieval_mode?: 'lexical' | 'hybrid';
}
export interface DocumentVersion {
  id: string;
  number: number;
  filename: string;
  format: string;
  state: 'uploading' | 'queued' | 'parsing' | 'indexing' | 'ready' | 'failed' | 'deleted';
  source_bytes: number | null;
  warnings: string[];
  created_at: string;
}
export interface KnowledgeDocument {
  id: string;
  knowledge_id: string;
  title: string;
  owner_id: string;
  visibility: 'restricted' | 'inherited';
  state: string;
  current_version_id: string | null;
  revision: number;
  versions: DocumentVersion[];
  latest_job: {
    id: string;
    state: string;
    phase: string;
    generation: number;
    cleanup_state: string;
    export_acknowledged: boolean;
    error_code: string | null;
  } | null;
}
export interface Citation {
  id: string;
  label: string;
  document_id: string;
  version_id: string;
  title: string;
  filename?: string;
  version: number;
  location: Record<string, string | number>;
  text?: string;
  download_url: string;
}
export interface KnowledgeSearchResult {
  query_id: string;
  matches: Citation[];
  answerable: boolean;
  retrieval_mode: 'lexical' | 'hybrid';
  untrusted_reference_data: boolean;
}
export interface EmbeddingModel {
  id: string;
  name: string;
  model: string;
  config: {
    endpoint: string;
    secret_env: string;
    dimensions: number;
    input_price_per_million: string;
    max_call_charge: string;
    batch_size: number;
  };
  digest: string;
}
export type KnowledgeCreateRequest = components['schemas']['KnowledgeCreate'];
export type DocumentCreateRequest = components['schemas']['DocumentCreate'];
export type EmbeddingCreateRequest = components['schemas']['EmbeddingCreate'];
