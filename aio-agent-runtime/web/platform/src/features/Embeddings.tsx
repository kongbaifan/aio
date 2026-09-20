import { useState } from 'react';
import type { FormEvent } from 'react';
import { Plus } from 'lucide-react';
import { api, explain } from '../api/client';
import type { AdminOptions, EmbeddingCreateRequest, EmbeddingModel, Page } from '../api/types';
import { useAuth } from '../auth';
import { shortId, useResource } from '../hooks';
import { Button, Empty, ErrorBox, Field, Loading, Modal, Notice } from '../components/ui';

interface UsageHold {
  id: string;
  requested_by: string;
  job_id: string | null;
  run_id: string | null;
  state: string;
  max_charge: string;
}

export function EmbeddingAdmin() {
  const { me } = useAuth();
  const models = useResource<Page<EmbeddingModel>>('/api/v2/embedding-models');
  const options = useResource<AdminOptions>('/api/v2/admin/options');
  const usage = useResource<Page<UsageHold>>('/api/v2/admin/embedding-calls');
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [hold, setHold] = useState<UsageHold | null>(null),
    [amount, setAmount] = useState(''),
    [evidence, setEvidence] = useState('');
  const [form, setForm] = useState({
    name: '',
    model: '',
    endpoint: '',
    secret_env: '',
    dimensions: 1536,
    input_price_per_million: '0.10',
    max_call_charge: '0.01',
    batch_size: 32,
  });
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.request('/api/v2/admin/embedding-models', 'POST', form satisfies EmbeddingCreateRequest);
      setOpen(false);
      models.reload();
    } catch (error) {
      setError(explain(error));
    } finally {
      setBusy(false);
    }
  }
  async function reconcile(event: FormEvent) {
    event.preventDefault();
    if (!hold) return;
    setBusy(true);
    setError('');
    try {
      await api.request(`/api/v2/admin/embedding-calls/${hold.id}/reconcile`, 'POST', {
        amount,
        evidence_ref: evidence,
      });
      setHold(null);
      usage.reload();
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
          <h2>嵌入模型与费用核对</h2>
          <p>配置固定维度和单次计费上限。只引用 Worker 的获准密钥名称，不把密钥交给文档解析器。</p>
        </div>
        <Button
          disabled={!options.data?.model_allowed_origins.length || !options.data?.model_secret_names.length}
          onClick={() => {
            setForm({
              ...form,
              endpoint: (options.data?.model_allowed_origins[0] ?? '') + '/v1/embeddings',
              secret_env: options.data?.model_secret_names[0] ?? '',
            });
            setOpen(true);
          }}
        >
          <Plus size={16} />
          登记嵌入模型
        </Button>
      </div>
      <ErrorBox message={error || models.error || usage.error || options.error} />
      {models.loading ? (
        <Loading />
      ) : !models.data?.items.length ? (
        <Empty title="尚无获权的嵌入模型">
          知识库仍可使用中文关键词检索。需要语义召回时，再配置并明确批准数据外发。
        </Empty>
      ) : (
        <div className="agent-admin-grid">
          {models.data.items.map((model) => (
            <article className="agent-admin-card" key={model.id}>
              <h3>{model.name}</h3>
              <p>
                {model.model} · {model.config.dimensions} 维 · {model.config.batch_size} 条/批
              </p>
              <small className="muted">
                单次上限 ${model.config.max_call_charge} · 每百万输入 token $
                {model.config.input_price_per_million}
              </small>
              <code>{model.config.endpoint}</code>
            </article>
          ))}
        </div>
      )}
      <h3 className="section-heading">待核对费用</h3>
      <Notice>
        响应不明不等于免费，也不等于请求未发生。系统保留额度，不自动重新请求。核对金额需要另一位管理员及外部依据。
      </Notice>
      {usage.data?.items.length ? (
        <ul className="embedding-holds">
          {usage.data.items.map((row) => (
            <li key={row.id}>
              <div>
                <strong>
                  {shortId(row.id)} · {row.state === 'unknown' ? '结果/费用未确认' : '结果已知，usage 未返回'}
                </strong>
                <small>
                  保留上限 ${row.max_charge} · 请求人 {shortId(row.requested_by)}
                </small>
              </div>
              <Button
                variant="secondary"
                disabled={row.requested_by === me?.user_id}
                onClick={() => {
                  setHold(row);
                  setAmount('');
                  setEvidence('');
                }}
              >
                录入核对依据
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">暂无待核对的嵌入调用。</p>
      )}
      {open && (
        <Modal
          title="登记固定嵌入模型"
          description="地址和 Secret 变量名必须在部署允许列表中。改变模型或维度应创建新的配置版本，不能混入旧索引。"
          onClose={() => setOpen(false)}
        >
          <form className="form-stack" onSubmit={create}>
            <ErrorBox message={error} />
            <div className="form-grid">
              <Field label="显示名称">
                <input
                  required
                  value={form.name}
                  maxLength={100}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="模型标识">
                <input
                  required
                  value={form.model}
                  maxLength={128}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                />
              </Field>
            </div>
            <Field label="Embedding HTTPS 端点">
              <input
                required
                type="url"
                value={form.endpoint}
                onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
              />
            </Field>
            <Field label="获准密钥变量名">
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
              <Field label="向量维度">
                <input
                  type="number"
                  required
                  min={1}
                  max={3072}
                  value={form.dimensions}
                  onChange={(e) => setForm({ ...form, dimensions: Number(e.target.value) })}
                />
              </Field>
              <Field label="每批文本数">
                <input
                  type="number"
                  required
                  min={1}
                  max={64}
                  value={form.batch_size}
                  onChange={(e) => setForm({ ...form, batch_size: Number(e.target.value) })}
                />
              </Field>
            </div>
            <div className="form-grid">
              <Field label="每百万输入 token（USD）">
                <input
                  type="number"
                  required
                  min={0}
                  max={10000}
                  step="0.000001"
                  value={form.input_price_per_million}
                  onChange={(e) => setForm({ ...form, input_price_per_million: e.target.value })}
                />
              </Field>
              <Field label="单次费用上限（USD）">
                <input
                  type="number"
                  required
                  min="0.000001"
                  max={100}
                  step="0.000001"
                  value={form.max_call_charge}
                  onChange={(e) => setForm({ ...form, max_call_charge: e.target.value })}
                />
              </Field>
            </div>
            <div className="form-actions">
              <Button type="submit" busy={busy}>
                保存嵌入模型配置
              </Button>
            </div>
          </form>
        </Modal>
      )}
      {hold && (
        <Modal
          title="核对嵌入请求费用"
          description="这是追加记账，不是重新请求模型。结果丢失的请求不会因费用核对而自动变成已完成索引。"
          onClose={() => setHold(null)}
        >
          <form className="form-stack" onSubmit={reconcile}>
            <ErrorBox message={error} />
            <Field label="确认实际金额（USD）">
              <input
                type="number"
                min="0"
                max="100"
                step="0.000001"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </Field>
            <Field label="核对依据编号">
              <input
                required
                maxLength={256}
                value={evidence}
                onChange={(e) => setEvidence(e.target.value)}
              />
            </Field>
            <div className="form-actions">
              <Button type="submit" busy={busy}>
                记录依据并结算保留额度
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
