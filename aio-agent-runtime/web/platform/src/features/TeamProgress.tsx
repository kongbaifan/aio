import type { RunState, RunTeam } from '../api/types';
import { Badge } from '../components/ui';

const STAGES: Record<RunTeam['stage'], string> = {
  queued: '等待规划',
  planning: '正在规划',
  step: '执行步骤',
  synthesis: '正在汇总',
  completed: '编排已结束',
  stopped: '编排已停止',
};

export function TeamProgress({ team, runState }: { team: RunTeam; runState: RunState }) {
  return (
    <section className="team-progress" aria-label="团队步骤">
      <header>
        <h3>多步骤任务</h3>
        <span>{STAGES[team.stage]}</span>
      </header>
      <p className="team-hint">同一任务内顺序执行，权限与预算不因步骤增加而扩大。</p>
      {!team.steps.length && <p className="muted">计划尚未提交，暂无已执行步骤。</p>}
      <ol>
        {team.steps.map((step) => (
          <li key={step.id}>
            <details
              open={
                step.state === 'running' || ['failed', 'denied', 'recovery_required'].includes(step.state)
              }
            >
              <summary>
                <span>
                  {step.ordinal}. {step.title}
                </span>
                <Badge
                  state={
                    step.state === 'running' && runState === 'waiting_approval'
                      ? 'waiting_approval'
                      : step.state
                  }
                />
              </summary>
              <p>{step.task}</p>
              <p className="team-scope">
                {step.tools.length ? `工具范围：${step.tools.join('、')}` : '仅处理文字，不调用工具'}
              </p>
              {step.result?.reason_codes.map((code) => (
                <code className="team-reason" key={code}>
                  {code}
                </code>
              ))}
              {step.result?.answer && <p className="team-output">{step.result.answer}</p>}
              {step.output_checkpoint_seq !== null && (
                <small>结果已保存 · 检查点 {step.output_checkpoint_seq}</small>
              )}
            </details>
          </li>
        ))}
      </ol>
      {team.stage === 'stopped' && (
        <p className="team-hint">未执行的步骤不会自动重跑；需要核对的结果请交由有权限的人员处理。</p>
      )}
    </section>
  );
}
