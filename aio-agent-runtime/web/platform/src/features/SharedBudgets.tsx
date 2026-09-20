import { useState } from 'react';
import type { FormEvent } from 'react';
import { Pencil, RefreshCw } from 'lucide-react';
import { api, explain } from '../api/client';
import type { Page, SharedBudget, SharedBudgetUpdateRequest } from '../api/types';
import { useResource } from '../hooks';
import { Badge, Button, ErrorBox, Field, Loading, Modal, Notice } from '../components/ui';

export function SharedBudgets() {
  const resource = useResource<Page<SharedBudget>>('/api/v2/admin/shared-budgets');
  const [selected, setSelected] = useState<SharedBudget | null>(null);
  const [limit, setLimit] = useState('10');
  const [enabled, setEnabled] = useState(true);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  function edit(row: SharedBudget) {
    setSelected(row);
    // A missing cap is a real persisted state, not an invitation to submit a
    // default amount. Keep it disabled until the administrator opts in.
    setLimit(row.hard_limit ?? '');
    setEnabled(row.hard_limit !== null);
    setConfirmed(false);
    setError('');
  }
  function close() {
    if (busy) return;
    setSelected(null);
    resource.reload();
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!selected || busy || (!enabled && !confirmed)) return;
    setBusy(true);
    setError('');
    try {
      const target =
        selected.scope === 'organization' ? 'organization' : `departments/${selected.department_id}`;
      const body = {
        expected_revision: selected.revision,
        hard_limit: enabled ? limit : null,
      } satisfies SharedBudgetUpdateRequest;
      await api.request(`/api/v2/admin/shared-budgets/${target}`, 'PUT', body);
      setSelected(null);
      resource.reload();
    } catch (failure) {
      setError(explain(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="admin-section" aria-label="组织与部门共享预算">
      <div className="section-top">
        <div>
          <h2>组织与部门共享预算</h2>
          <p>个人预算之外的附加硬上限；预留、已消费和未知费用占额不会因调动部门或修改限额而消失。</p>
        </div>
        <Button variant="quiet" onClick={resource.reload}>
          <RefreshCw size={16} />
          刷新汇总
        </Button>
      </div>
      <Notice>
        同一笔费用同时约束组织及任务提交时的全部有效部门，这些重叠金额不能相加当作总账。按 USD
        累计，不是月度自动充值；预留包含尚待核对的未知费用。
      </Notice>
      <ErrorBox message={resource.error} retry={resource.reload} />
      {resource.loading ? (
        <Loading />
      ) : (
        resource.data && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>范围</th>
                  <th>累计上限（USD）</th>
                  <th>已消费</th>
                  <th>已预留</th>
                  <th>可新增预留</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {resource.data.items.map((row) => (
                  <tr key={row.department_id ?? 'organization'}>
                    <td>
                      <strong>{row.display_name}</strong>
                      <div className="small-note">{row.scope === 'organization' ? '组织' : '部门'}</div>
                    </td>
                    <td className="mono">{row.hard_limit ?? '未设置附加上限'}</td>
                    <td className="mono">
                      {row.consumed}
                      {Number(row.opening_consumed) > 0 && (
                        <div className="small-note">含启用前既有消费 {row.opening_consumed}</div>
                      )}
                    </td>
                    <td className="mono">{row.reserved}</td>
                    <td className="mono">{row.remaining ?? '仍受个人预算约束'}</td>
                    <td>
                      <Badge
                        state={
                          row.exhausted
                            ? 'budget_exhausted'
                            : row.warning
                              ? 'budget_warning'
                              : row.hard_limit === null
                                ? 'budget_recorded'
                                : 'budget_enforced'
                        }
                      />
                    </td>
                    <td>
                      <Button
                        variant="quiet"
                        aria-label={`调整${row.display_name}共享预算`}
                        onClick={() => edit(row)}
                      >
                        <Pencil size={14} />
                        调整上限
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {selected && (
        <Modal title={`设置${selected.display_name}共享预算`} onClose={close}>
          <form className="form-stack" onSubmit={save}>
            <ErrorBox message={error} />
            <p className="small-note">
              已消费 {selected.consumed} USD，已预留 {selected.reserved}{' '}
              USD。新的上限不能低于这两项的合计；并发变动以服务器复核为准。
            </p>
            <label>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => {
                  setEnabled(e.target.checked);
                  setConfirmed(false);
                }}
              />
              启用共享上限
            </label>
            {enabled ? (
              <Field label="共享上限（USD）">
                <input
                  aria-label="共享上限（USD）"
                  type="number"
                  required
                  min="0"
                  max="1000000"
                  step="0.000001"
                  value={limit}
                  onChange={(e) => setLimit(e.target.value)}
                />
              </Field>
            ) : (
              <label>
                <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                我确认只移除附加限额，不清空消费、预留或审计记录
              </label>
            )}
            <div className="form-actions">
              <Button busy={busy} disabled={!enabled && !confirmed} type="submit">
                保存共享预算
              </Button>
              <Button type="button" variant="quiet" disabled={busy} onClick={close}>
                关闭并刷新
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
