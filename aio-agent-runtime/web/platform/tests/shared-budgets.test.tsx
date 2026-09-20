import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../src/api/client';
import type { SharedBudget } from '../src/api/types';
import { SharedBudgets } from '../src/features/SharedBudgets';

const departmentId = '50000000-0000-4000-8000-000000000001';
const original: SharedBudget = {
  id: '60000000-0000-4000-8000-000000000001',
  scope: 'organization',
  department_id: null,
  display_name: '组织总额',
  currency: 'USD',
  hard_limit: '10.000000',
  consumed: '2.000001',
  reserved: '6.000000',
  remaining: '1.999999',
  warning: true,
  exhausted: false,
  revision: 7,
  created_at: '2026-09-14T00:00:00Z',
  opening_consumed: '0',
};

function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } });
}
function setup(conflict = false) {
  let item = { ...original };
  const requests: Array<{ path: string; body: Record<string, unknown> }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, init: RequestInit = {}) => {
      const path = String(input);
      if (init.method === 'PUT') {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        requests.push({ path, body });
        if (conflict) {
          conflict = false;
          item = { ...item, revision: 8, hard_limit: '11.000000' };
          return response({ error: { code: 'REVISION_CONFLICT' } }, 409);
        }
        return response({ ...item, revision: 8 });
      }
      return response({
        items: [
          item,
          {
            ...item,
            id: null,
            scope: 'department',
            department_id: departmentId,
            display_name: '销售',
            hard_limit: null,
            remaining: null,
            warning: false,
            revision: 0,
          },
        ],
      });
    }),
  );
  return requests;
}

// Renders an arbitrary set of pool rows so a single case can cover every badge
// tone at once; the shape stays the fixture above so only the fields under test
// vary between rows.
function setupRows(items: SharedBudget[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => response({ items })),
  );
}
function row(name: string) {
  return screen.getByText(name).closest('tr')!;
}
function cell(name: string, header: string) {
  const headers = Array.from(document.querySelectorAll('thead th')).map((th) => th.textContent);
  return row(name).querySelectorAll('td')[headers.indexOf(header)];
}
function badge(name: string) {
  return cell(name, '状态').querySelector('.badge')!;
}

beforeEach(() => {
  api.invalidate();
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value: function () {
      this.setAttribute('open', '');
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value: function () {
      this.removeAttribute('open');
    },
  });
});
afterEach(() => {
  api.invalidate();
  vi.unstubAllGlobals();
});

it('explains overlapping scopes and shows exact decimals, holds and warning state', async () => {
  setup();
  render(<SharedBudgets />);
  expect(await screen.findByText('组织总额')).toBeInTheDocument();
  expect(screen.getByText(/重叠金额不能相加当作总账/)).toBeInTheDocument();
  expect(screen.getByText('1.999999')).toBeInTheDocument();
  expect(screen.getByText('达到 80% 警戒线')).toBeInTheDocument();
  expect(screen.getByText('仅记录用量')).toBeInTheDocument();
  expect(screen.getByText('未设置附加上限')).toBeInTheDocument();
});

it('sends a decimal string and the displayed revision to the organization scope only', async () => {
  const requests = setup();
  render(<SharedBudgets />);
  await userEvent.click(await screen.findByRole('button', { name: '调整组织总额共享预算' }));
  await userEvent.clear(screen.getByLabelText('共享上限（USD）'));
  await userEvent.type(screen.getByLabelText('共享上限（USD）'), '12.000001');
  await userEvent.click(screen.getByRole('button', { name: '保存共享预算' }));
  await waitFor(() => expect(requests).toHaveLength(1));
  expect(requests[0]).toEqual({
    path: '/api/v2/admin/shared-budgets/organization',
    body: { expected_revision: 7, hard_limit: '12.000001' },
  });
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});

it('requires explicit confirmation to remove a cap and never submits a balance reset', async () => {
  const requests = setup();
  render(<SharedBudgets />);
  await userEvent.click(await screen.findByRole('button', { name: '调整销售共享预算' }));
  expect(screen.getByRole('button', { name: '保存共享预算' })).toBeDisabled();
  await userEvent.click(screen.getByLabelText(/我确认只移除附加限额/));
  await userEvent.click(screen.getByRole('button', { name: '保存共享预算' }));
  await waitFor(() => expect(requests).toHaveLength(1));
  expect(requests[0]).toEqual({
    path: `/api/v2/admin/shared-budgets/departments/${departmentId}`,
    body: { expected_revision: 0, hard_limit: null },
  });
});

it('keeps conflicts visible and reloads the current revision before another explicit edit', async () => {
  const requests = setup(true);
  render(<SharedBudgets />);
  await userEvent.click(await screen.findByRole('button', { name: '调整组织总额共享预算' }));
  await userEvent.click(screen.getByRole('button', { name: '保存共享预算' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/状态已变化|刷新/);
  expect(requests).toHaveLength(1);
  await userEvent.click(screen.getByRole('button', { name: '关闭并刷新' }));
  await screen.findByText('11.000000');
  await userEvent.click(screen.getByRole('button', { name: '调整组织总额共享预算' }));
  await userEvent.click(screen.getByRole('button', { name: '保存共享预算' }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[1].body.expected_revision).toBe(8);
});

it('colours each pool state so exhausted and warning rows are never rendered as neutral', async () => {
  // The server only ever raises `exhausted` on top of `warning`, so the
  // exhausted row also carries warning: true to prove precedence.
  setupRows([
    {
      ...original,
      display_name: '已承诺完组织',
      hard_limit: '10.000000',
      consumed: '4.000000',
      reserved: '6.000000',
      remaining: '0',
      warning: true,
      exhausted: true,
    },
    { ...original, display_name: '警戒线部门', scope: 'department', department_id: departmentId },
    {
      ...original,
      display_name: '限额生效部门',
      scope: 'department',
      department_id: '50000000-0000-4000-8000-000000000002',
      consumed: '1.000000',
      reserved: '0.000000',
      remaining: '9.000000',
      warning: false,
      exhausted: false,
    },
    {
      ...original,
      display_name: '仅记录部门',
      scope: 'department',
      department_id: '50000000-0000-4000-8000-000000000003',
      hard_limit: null,
      remaining: null,
      warning: false,
      exhausted: false,
    },
  ]);
  render(<SharedBudgets />);
  expect(await screen.findByText('已承诺完组织')).toBeInTheDocument();

  expect(badge('已承诺完组织')).toHaveTextContent('额度已承诺完');
  expect(badge('已承诺完组织')).toHaveClass('badge-red');
  expect(badge('警戒线部门')).toHaveTextContent('达到 80% 警戒线');
  expect(badge('警戒线部门')).toHaveClass('badge-amber');
  expect(badge('限额生效部门')).toHaveTextContent('限额生效');
  expect(badge('限额生效部门')).toHaveClass('badge-green');
  expect(badge('仅记录部门')).toHaveTextContent('仅记录用量');
  expect(badge('仅记录部门')).toHaveClass('badge-neutral');

  // The regression itself: unmapped states fell through to the neutral tone, so
  // an over-limit pool looked exactly like an unconstrained one.
  expect(badge('已承诺完组织')).not.toHaveClass('badge-neutral');
  expect(badge('警戒线部门')).not.toHaveClass('badge-neutral');
});

it('shows the migrated opening consumption apart from the running total and stays silent at zero', async () => {
  setupRows([
    {
      ...original,
      display_name: '有既有消费组织',
      consumed: '2.000001',
      opening_consumed: '1.500000',
    },
    {
      ...original,
      display_name: '无既有消费部门',
      scope: 'department',
      department_id: departmentId,
      consumed: '2.000001',
      opening_consumed: '0',
    },
  ]);
  render(<SharedBudgets />);
  expect(await screen.findByText('有既有消费组织')).toBeInTheDocument();

  const migrated = cell('有既有消费组织', '已消费');
  // Both numbers are present, and the opening share sits in its own note rather
  // than replacing or being folded into the total.
  expect(migrated).toHaveTextContent('2.000001');
  const note = migrated.querySelector('.small-note')!;
  expect(note).toHaveTextContent('含启用前既有消费 1.500000');
  expect(note).not.toHaveTextContent('2.000001');
  // Six decimals survive; nothing rounds 1.500000 down to 1.5.
  expect(note.textContent).toContain('1.500000');

  const plain = cell('无既有消费部门', '已消费');
  expect(plain).toHaveTextContent('2.000001');
  expect(plain.querySelector('.small-note')).toBeNull();
  expect(screen.queryAllByText(/含启用前既有消费/)).toHaveLength(1);
});
