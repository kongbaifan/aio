import { useEffect, useId, useRef } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { AlertCircle, Check, LoaderCircle, X } from 'lucide-react';
import type { RunState } from '../api/types';

export function Button({
  children,
  variant = 'primary',
  busy = false,
  className = '',
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger';
  busy?: boolean;
}) {
  return (
    <button {...props} disabled={disabled || busy} className={`button button-${variant} ${className}`}>
      {busy && <LoaderCircle size={15} className="spin" aria-hidden="true" />}
      {children}
    </button>
  );
}
export function ErrorBox({ message, retry }: { message: string; retry?: () => void }) {
  if (!message) return null;
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={17} aria-hidden="true" />
      <span>{message}</span>
      {retry && <button onClick={retry}>重试</button>}
    </div>
  );
}
export function Loading({ label = '正在读取工作区…' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle size={20} className="spin" aria-hidden="true" />
      {label}
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-mark" aria-hidden="true">
        ＋
      </div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  description,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  description?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  const previous = useRef<HTMLElement | null>(null);
  useEffect(() => {
    previous.current = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute('open', '');
    return () => {
      dialog?.close?.();
      previous.current?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={id}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <div>
          <h2 id={id}>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        <button type="button" className="icon-button" aria-label="关闭对话框" onClick={onClose}>
          <X size={19} />
        </button>
      </header>
      <div className="modal-body">{children}</div>
    </dialog>
  );
}
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
type Tone = 'neutral' | 'blue' | 'green' | 'amber' | 'red';
// `satisfies` keeps the literal keys (so `BadgeState` stays precise) while the
// target type enforces two things the earlier gray-badge defect slipped past:
// every `RunState` must have an entry, and `tone` must be a real tone rather
// than a typo that CSS would silently drop.
export const BADGE_STATES = {
  queued: { label: '排队中', tone: 'neutral' },
  preparing: { label: '准备环境', tone: 'blue' },
  running: { label: '执行中', tone: 'blue' },
  waiting_approval: { label: '等待审批', tone: 'amber' },
  persisting: { label: '保存结果', tone: 'blue' },
  cancel_requested: { label: '停止处理中', tone: 'amber' },
  recovery_required: { label: '需要人工核对', tone: 'amber' },
  succeeded: { label: '已完成', tone: 'green' },
  failed: { label: '未完成', tone: 'red' },
  cancelled: { label: '已取消', tone: 'neutral' },
  timed_out: { label: '已超时', tone: 'red' },
  pending: { label: '待处理', tone: 'amber' },
  approved: { label: '已批准', tone: 'green' },
  rejected: { label: '已拒绝', tone: 'red' },
  denied: { label: '操作被拒绝', tone: 'red' },
  skipped: { label: '未执行', tone: 'neutral' },
  expired: { label: '已过期', tone: 'neutral' },
  active: { label: '已启用', tone: 'green' },
  disabled: { label: '已停用', tone: 'neutral' },
  invalidated: { label: '已失效', tone: 'neutral' },
  budget_exhausted: { label: '额度已承诺完', tone: 'red' },
  budget_warning: { label: '达到 80% 警戒线', tone: 'amber' },
  budget_enforced: { label: '限额生效', tone: 'green' },
  budget_recorded: { label: '仅记录用量', tone: 'neutral' },
} satisfies Record<RunState, { label: string; tone: Tone }> & Record<string, { label: string; tone: Tone }>;
export type BadgeState = keyof typeof BADGE_STATES;
// `state` stays `string` on purpose: run/approval/resource states arrive from the
// server and an unrecognised one must still render verbatim instead of being
// dropped or crashing the page. `tests/badges.test.tsx` pins the tone of every
// operationally meaningful key and scans callers so a hardcoded literal that is
// not in the map fails the suite.
export function Badge({ state }: { state: BadgeState | (string & {}) }) {
  const value: { label: string; tone: Tone } = BADGE_STATES[state as BadgeState] ?? {
    label: state,
    tone: 'neutral',
  };
  return (
    <span className={`badge badge-${value.tone}`}>
      <span aria-hidden="true" />
      {value.label}
    </span>
  );
}
export const TERMINAL = new Set<RunState>([
  'succeeded',
  'failed',
  'cancelled',
  'timed_out',
  'recovery_required',
]);
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="page-title">
      <div>
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </header>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice">
      <Check size={15} aria-hidden="true" />
      <span>{children}</span>
    </div>
  );
}
