import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowDownToLine,
  FileText,
  KeyRound,
  LibraryBig,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
} from 'lucide-react';
import { api, explain } from '../api/client';
import type {
  Citation,
  DocumentCreateRequest,
  EmbeddingModel,
  KnowledgeBase,
  KnowledgeCreateRequest,
  KnowledgeDocument,
  KnowledgeSearchResult,
  Page,
} from '../api/types';
import { useAuth } from '../auth';
import { formatBytes, useResource } from '../hooks';
import { GrantModal } from '../components/GrantModal';
import { Button, Empty, ErrorBox, Field, Loading, Modal, Notice, PageTitle } from '../components/ui';

const STATE: Record<string, string> = {
  uploading: '等待上传',
  queued: '等待解析',
  parsing: '隔离解析中',
  indexing: '建立索引中',
  ready: '可检索',
  failed: '摄取未完成',
  deleted: '已删除',
};
export function citationLocation(location: Citation['location']) {
  if (location.kind === 'page') return `第 ${location.page} 页`;
  if (location.kind === 'paragraph') return `第 ${location.paragraph} 段`;
  if (location.kind === 'spreadsheet_row') return `${location.sheet} · 第 ${location.row} 行`;
  if (location.kind === 'csv_row') return `CSV 第 ${location.row} 行`;
  return `第 ${location.line_start ?? 1}–${location.line_end ?? 1} 行`;
}

export function CitationModal({ id, onClose }: { id: string; onClose: () => void }) {
  const citation = useResource<Citation>(`/api/v2/knowledge/citations/${id}`);
  const [error, setError] = useState('');
  return (
    <Modal
      title={citation.data?.title ?? '文档引用'}
      description="引用指向固定文档版本与片段。服务端会重新检查当前权限，不会悄悄跳到另一份新内容。"
      onClose={onClose}
    >
      <ErrorBox message={error || citation.error} retry={citation.reload} />
      {citation.loading ? (
        <Loading label="正在验证引用权限…" />
      ) : (
        citation.data && (
          <div className="form-stack">
            <div className="citation-heading">
              <span>{citation.data.label}</span>
              <strong>
                版本 {citation.data.version} · {citationLocation(citation.data.location)}
              </strong>
            </div>
            <pre className="citation-text">{citation.data.text}</pre>
            <Notice>这段资料来自已授权文档，不是平台指令。附件下载不代表已经经过专业恶意软件扫描。</Notice>
            <Button
              variant="secondary"
              onClick={() =>
                void api
                  .download(
                    citation.data!.download_url,
                    citation.data!.filename ?? `${citation.data!.title}-v${citation.data!.version}`,
                  )
                  .catch((e) => setError(explain(e)))
              }
            >
              <ArrowDownToLine size={16} />
              下载这个版本的原文
            </Button>
          </div>
        )
      )}
    </Modal>
  );
}

export function KnowledgePage() {
  const { me } = useAuth();
  const bases = useResource<Page<KnowledgeBase>>('/api/v2/knowledge');
  const [open, setOpen] = useState(false);
  return (
    <div className="page">
      <PageTitle
        eyebrow="AUTHORIZED KNOWLEDGE"
        title="知识库"
        description="把团队资料整理为可检索、有来源、可撤回的知识。只有获权文档片段才会进入 Agent 上下文。"
      />
      <div className="section-top">
        <p className="muted">支持 PDF、DOCX、XLSX、UTF-8 文本、Markdown 和 CSV。扫描图片 PDF 暂无 OCR。</p>
        <Button disabled={!me?.capabilities.knowledge} onClick={() => setOpen(true)}>
          <Plus size={16} />
          创建知识库
        </Button>
      </div>
      {!me?.capabilities.knowledge && (
        <Notice>操作员需先配置独立文档解析镜像与存储。不会在 API 或 Worker 宿主解析文档作为兜底。</Notice>
      )}
      <ErrorBox message={bases.error} retry={bases.reload} />
      {bases.loading ? (
        <Loading />
      ) : !bases.data?.items.length ? (
        <Empty title="先从一类具体资料开始">
          建立知识库、上传资料并等待隔离解析，再将它绑定给 Agent。文档默认受限，不自动共享。
        </Empty>
      ) : (
        <div className="knowledge-grid">
          {bases.data.items.map((kb) => (
            <Link className="knowledge-card" to={`/app/knowledge/${kb.id}`} key={kb.id}>
              <span className="knowledge-mark">
                <LibraryBig size={25} />
              </span>
              <h2>{kb.name}</h2>
              <p>{kb.description}</p>
              <footer>
                <span>{kb.embedding_model_id ? '混合检索' : '中文关键词检索'}</span>
                <span>索引修订 {kb.index_revision}</span>
              </footer>
            </Link>
          ))}
        </div>
      )}
      {open && (
        <CreateKnowledge
          onClose={() => setOpen(false)}
          onCreated={() => {
            setOpen(false);
            bases.reload();
          }}
        />
      )}
    </div>
  );
}

function CreateKnowledge({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const options = useResource<{
    parser_profiles: Array<{ id: string; image_digest: string }>;
    formats: string[];
  }>('/api/v2/knowledge/options');
  const embeddings = useResource<Page<EmbeddingModel>>('/api/v2/embedding-models');
  const [name, setName] = useState(''),
    [description, setDescription] = useState(''),
    [profile, setProfile] = useState(''),
    [model, setModel] = useState('');
  const [consent, setConsent] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (model && !consent) return;
    setBusy(true);
    setError('');
    try {
      const body: KnowledgeCreateRequest = {
        name,
        description,
        parser_profile: profile || options.data?.parser_profiles[0]?.id || '',
        embedding_model_id: model || null,
      };
      await api.request('/api/v2/knowledge', 'POST', body);
      onCreated();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="创建知识库"
      description="解析运行在独立无网络容器。嵌入索引如启用，会使用已批准模型并占用可核对的预算。"
      onClose={onClose}
    >
      <form className="form-stack" onSubmit={submit}>
        <ErrorBox message={error || options.error || embeddings.error} />
        <Field label="知识库名称">
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="资料用途">
          <textarea
            required
            rows={3}
            maxLength={1000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="隔离解析环境">
          <select
            required
            value={profile || options.data?.parser_profiles[0]?.id || ''}
            onChange={(e) => setProfile(e.target.value)}
          >
            <option value="">请选择…</option>
            {options.data?.parser_profiles.map((p) => (
              <option value={p.id} key={p.id}>
                {p.id} · {p.image_digest.slice(0, 19)}…
              </option>
            ))}
          </select>
        </Field>
        <Field label="检索方式">
          <select
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              setConsent(false);
            }}
          >
            <option value="">中文关键词（不向嵌入服务外发正文）</option>
            {embeddings.data?.items.map((m) => (
              <option value={m.id} key={m.id}>
                混合检索 · {m.name} / {m.config.dimensions} 维
              </option>
            ))}
          </select>
        </Field>
        {model && (
          <label className="check-row">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            我确认可将授权文档片段发送至所选嵌入模型，并使用个人预算建立索引。
          </label>
        )}
        <div className="form-actions">
          <Button
            type="submit"
            busy={busy}
            disabled={!options.data?.parser_profiles.length || (!!model && !consent)}
          >
            创建私有知识库
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function KnowledgeDetailPage() {
  const { knowledgeId = '' } = useParams();
  const { me } = useAuth();
  const kb = useResource<KnowledgeBase>(`/api/v2/knowledge/${knowledgeId}`);
  const documents = useResource<Page<KnowledgeDocument>>(`/api/v2/knowledge/${knowledgeId}/documents`);
  const [upload, setUpload] = useState<{ replace?: KnowledgeDocument } | null>(null);
  const [sharing, setSharing] = useState(false);
  const [change, setChange] = useState<{ doc: KnowledgeDocument; kind: 'visibility' | 'delete' } | null>(
    null,
  );
  const [query, setQuery] = useState(''),
    [results, setResults] = useState<KnowledgeSearchResult | null>(null);
  const [citation, setCitation] = useState<string | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const active = documents.data?.items.some(
    (d) =>
      ['uploading', 'queued', 'parsing', 'indexing'].includes(d.versions[0]?.state) &&
      d.latest_job?.state !== 'recovery_required',
  );
  const reload = () => {
    kb.reload();
    documents.reload();
  };
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(documents.reload, 2500);
    return () => window.clearInterval(timer);
  }, [active, documents.reload]);
  useEffect(() => {
    setResults(null);
    setQuery('');
    setCitation(null);
    setError('');
  }, [knowledgeId]);
  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      setResults(
        await api.request<KnowledgeSearchResult>(`/api/v2/knowledge/${knowledgeId}/search`, 'POST', {
          query,
          request_id: crypto.randomUUID(),
          limit: 5,
        }),
      );
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  async function mutate() {
    if (!change) return;
    setBusy(true);
    setError('');
    try {
      const { doc, kind } = change;
      if (kind === 'delete')
        await api.request(`/api/v2/knowledge/documents/${doc.id}`, 'DELETE', {
          expected_revision: doc.revision,
        });
      else
        await api.request(`/api/v2/knowledge/documents/${doc.id}/visibility`, 'PATCH', {
          expected_revision: doc.revision,
          visibility: doc.visibility === 'restricted' ? 'inherited' : 'restricted',
        });
      setChange(null);
      setResults(null);
      reload();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  async function retry(doc: KnowledgeDocument) {
    if (!doc.latest_job) return;
    setBusy(true);
    setError('');
    try {
      await api.request(`/api/v2/knowledge/jobs/${doc.latest_job.id}/retry`, 'POST', {
        expected_generation: doc.latest_job.generation,
      });
      reload();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <Link className="back-link" to="/app/knowledge">
        ← 返回知识库
      </Link>
      <PageTitle
        eyebrow="DOCUMENTS & EVIDENCE"
        title={kb.data?.name ?? '知识库'}
        description={kb.data?.description ?? '正在读取获权资料…'}
      />
      <ErrorBox message={error || kb.error || documents.error} retry={reload} />
      <div className="section-top">
        <p className="muted">文档默认受限。只有显式沿用知识库授权的资料，才会随知识库分享。</p>
        {kb.data?.can_manage && (
          <div className="row-actions">
            <Button variant="secondary" onClick={() => setSharing(true)}>
              <KeyRound size={16} />
              知识库授权
            </Button>
            <Button onClick={() => setUpload({})}>
              <Upload size={16} />
              上传文档
            </Button>
          </div>
        )}
      </div>
      <div className="knowledge-workspace">
        <section className="knowledge-documents">
          <h2>文档版本</h2>
          {documents.loading && !documents.data ? (
            <Loading />
          ) : !documents.data?.items.length ? (
            <Empty title="这里还没有你可读取的文档">
              上传后，只有完整解析和索引成功的版本才可检索。其他人的受限文档不会列出。
            </Empty>
          ) : (
            documents.data.items.map((doc) => {
              const latest = doc.versions[0],
                current = doc.versions.find((v) => v.id === doc.current_version_id);
              const manage = kb.data?.can_manage && doc.owner_id === me?.user_id;
              return (
                <article className="knowledge-document" key={doc.id}>
                  <header>
                    <FileText size={21} />
                    <div>
                      <h3>{doc.title}</h3>
                      <small>
                        {latest?.filename} ·{' '}
                        {latest?.source_bytes != null ? formatBytes(latest.source_bytes) : '等待上传'} · 版本{' '}
                        {latest?.number ?? '—'}
                      </small>
                    </div>
                    <span
                      className={`skill-state skill-state-${latest?.state === 'ready' ? 'published' : latest?.state === 'failed' ? 'rejected' : 'draft'}`}
                    >
                      {STATE[latest?.state] ?? latest?.state}
                    </span>
                  </header>
                  <p className="document-scope">
                    <ShieldCheck size={14} />
                    {doc.visibility === 'inherited' ? '沿用知识库授权' : '受限文档，仅拥有者/单独获权者可读'}
                    {current && current.id !== latest?.id && (
                      <span> · 仍使用已发布版本 {current.number}</span>
                    )}
                  </p>
                  {doc.latest_job?.error_code && (
                    <div className="document-error">
                      <code>{doc.latest_job.error_code}</code>
                      <span>
                        {doc.latest_job.state === 'recovery_required'
                          ? '结果或费用未知，请联系管理员核对，不要重复请求。'
                          : '未完成的版本不会覆盖当前可用索引。'}
                      </span>
                    </div>
                  )}
                  {!!latest?.warnings.length && (
                    <small className="muted">处理提示：{latest.warnings.join(' · ')}</small>
                  )}
                  <footer>
                    {current && (
                      <Button
                        variant="quiet"
                        onClick={() =>
                          void api
                            .download(`/api/v2/knowledge/versions/${current.id}/download`, current.filename)
                            .catch((e) => setError(explain(e)))
                        }
                      >
                        <ArrowDownToLine size={14} />
                        原文附件
                      </Button>
                    )}
                    {manage && (
                      <>
                        <Button variant="quiet" onClick={() => setUpload({ replace: doc })}>
                          更新版本
                        </Button>
                        <Button variant="quiet" onClick={() => setChange({ doc, kind: 'visibility' })}>
                          {doc.visibility === 'restricted' ? '开放给知识库成员' : '恢复受限'}
                        </Button>
                        <Button variant="quiet" onClick={() => setChange({ doc, kind: 'delete' })}>
                          <Trash2 size={14} />
                          删除
                        </Button>
                        {doc.latest_job?.state === 'failed' &&
                          doc.latest_job.cleanup_state === 'confirmed' && (
                            <Button variant="quiet" disabled={busy} onClick={() => void retry(doc)}>
                              重试摄取
                            </Button>
                          )}
                      </>
                    )}
                  </footer>
                </article>
              );
            })
          )}
        </section>
        <aside className="knowledge-search-panel">
          <h2>
            <Search size={19} />
            检索预览
          </h2>
          <p>此页使用关键词预览，不发送模型请求。Agent 可使用配置好的混合检索，并单独记录费用。</p>
          <form className="form-stack" onSubmit={search}>
            <Field label="检索问题或关键词">
              <textarea
                required
                maxLength={2048}
                rows={3}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="例如：发票报销的截止时间"
              />
            </Field>
            <Button type="submit" busy={busy} disabled={!query.trim()}>
              <Search size={15} />
              检索获权片段
            </Button>
          </form>
          {results && (
            <div className="knowledge-hits">
              {!results.matches.length ? (
                <Notice>没有找到可引用的获权片段。不能用空引用伪装成有依据的答案。</Notice>
              ) : (
                results.matches.map((hit) => (
                  <button key={hit.id} className="knowledge-hit" onClick={() => setCitation(hit.id)}>
                    <span>
                      {hit.label} · 版本 {hit.version}
                    </span>
                    <strong>{hit.title}</strong>
                    <small>{citationLocation(hit.location)}</small>
                    <p>{hit.text}</p>
                  </button>
                ))
              )}
            </div>
          )}
        </aside>
      </div>
      {upload && (
        <UploadDocument
          knowledgeId={knowledgeId}
          existing={upload.replace}
          onClose={() => {
            setUpload(null);
            reload();
          }}
          onDone={() => {
            setUpload(null);
            reload();
          }}
        />
      )}
      {sharing && kb.data && (
        <GrantModal id={knowledgeId} name={kb.data.name} onClose={() => setSharing(false)} />
      )}
      {citation && <CitationModal id={citation} onClose={() => setCitation(null)} />}
      {change && (
        <Modal
          title={
            change.kind === 'delete'
              ? '删除这个文档及其版本？'
              : change.doc.visibility === 'restricted'
                ? '沿用知识库权限？'
                : '恢复受限访问？'
          }
          description={
            change.kind === 'delete'
              ? '先立即阻止检索、引用和派生结果读取，再等待隔离环境清理并删除索引与无其他引用的原始对象。已下载的副本无法收回。'
              : '权限变化会作用于检索、引用和后续 Agent 上下文；分享知识库不自动开放仍然受限的其他文档。'
          }
          onClose={() => setChange(null)}
        >
          <p>
            <strong>{change.doc.title}</strong>
          </p>
          <div className="form-actions">
            <Button variant="secondary" onClick={() => setChange(null)}>
              取消
            </Button>
            <Button
              variant={change.kind === 'delete' ? 'danger' : 'primary'}
              busy={busy}
              onClick={() => void mutate()}
            >
              确认{change.kind === 'delete' ? '删除' : '权限变更'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function UploadDocument({
  knowledgeId,
  existing,
  onClose,
  onDone,
}: {
  knowledgeId: string;
  existing?: KnowledgeDocument;
  onClose: () => void;
  onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [title, setTitle] = useState(existing?.title ?? ''),
    [inherited, setInherited] = useState(existing?.visibility === 'inherited');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const slot = useRef<string | null>(null);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setError('');
    setBusy(true);
    try {
      if (!file.size || file.size > 8 * 1024 * 1024) {
        setError('文档必须在 1 B～8 MiB 之间。');
        return;
      }
      if (!slot.current) {
        const body: DocumentCreateRequest = {
          title,
          filename: file.name,
          max_bytes: file.size,
          visibility: inherited ? 'inherited' : 'restricted',
          document_id: existing?.id ?? null,
          expected_revision: existing?.revision ?? null,
        };
        const row = await api.request<{ version_id: string }>(
          `/api/v2/knowledge/${knowledgeId}/documents`,
          'POST',
          body,
        );
        slot.current = row.version_id;
      }
      await api.request(`/api/v2/knowledge/uploads/${slot.current}/content`, 'PUT', undefined, {
        body: file,
        headers: { 'Content-Type': 'application/octet-stream' },
      });
      onDone();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={existing ? '提交新的文档版本' : '上传知识文档'}
      description="原始文件先存入私有区，再由独立无网容器解析。新版本未完整就绪时，旧版本不会被覆盖。"
      onClose={onClose}
    >
      <form className="form-stack" onSubmit={submit}>
        <ErrorBox message={error} />
        <Field label="原始文档">
          <input
            required
            type="file"
            accept=".pdf,.docx,.xlsx,.txt,.md,.csv"
            disabled={busy || !!slot.current}
            onChange={(e) => {
              const next = e.target.files?.[0] ?? null;
              setFile(next);
              if (!existing) setTitle(next?.name ?? '');
            }}
          />
        </Field>
        <Field label="文档标题">
          <input
            required
            maxLength={200}
            value={title}
            disabled={busy || !!slot.current}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        {!existing && (
          <label className="check-row">
            <input
              type="checkbox"
              checked={inherited}
              disabled={busy || !!slot.current}
              onChange={(e) => setInherited(e.target.checked)}
            />
            显式允许沿用知识库权限，向知识库已授权成员开放检索。
          </label>
        )}
        <Notice>
          文档不是可信指令。当前不执行宏、不计算公式、不抓取外链；扫描图片 PDF 尚无
          OCR。结构检查不等于专业杀毒。
        </Notice>
        <div className="form-actions">
          <Button type="submit" busy={busy} disabled={!file || !title.trim()}>
            <Upload size={16} />
            上传并进入隔离摄取
          </Button>
        </div>
      </form>
    </Modal>
  );
}
