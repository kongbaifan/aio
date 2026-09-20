import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { render } from '@testing-library/react';
import { expect, it } from 'vitest';
import { Badge, BADGE_STATES } from '../src/components/ui';

function tone(state: string) {
  const { container } = render(<Badge state={state} />);
  return container.querySelector('.badge')!;
}

// The shared-budget defect was a badge whose state key missed the map and fell
// back to the neutral tone, so an over-limit pool looked like a normal one. The
// same silent fallback covers every other state, and no other suite pinned a
// tone. These are the states where the colour itself carries the operational
// meaning: red means someone must intervene, amber means it is not finished yet,
// green means it is genuinely live.
const OPERATIONAL: Array<[state: string, label: string, expected: string]> = [
  ['failed', '未完成', 'red'],
  ['timed_out', '已超时', 'red'],
  ['rejected', '已拒绝', 'red'],
  ['denied', '操作被拒绝', 'red'],
  ['waiting_approval', '等待审批', 'amber'],
  ['recovery_required', '需要人工核对', 'amber'],
  ['cancel_requested', '停止处理中', 'amber'],
  ['pending', '待处理', 'amber'],
  ['succeeded', '已完成', 'green'],
  ['approved', '已批准', 'green'],
  ['active', '已启用', 'green'],
  ['running', '执行中', 'blue'],
  ['queued', '排队中', 'neutral'],
  ['cancelled', '已取消', 'neutral'],
  ['disabled', '已停用', 'neutral'],
  // The four shared-budget states are where the defect actually surfaced, and
  // none of them had a tone pinned. Red says new paid work is being refused,
  // amber says the 80% line is crossed but spending still succeeds, green says a
  // ceiling is enforced and healthy, and only "recording usage without an extra
  // shared ceiling" is genuinely neutral.
  ['budget_exhausted', '额度已承诺完', 'red'],
  ['budget_warning', '达到 80% 警戒线', 'amber'],
  ['budget_enforced', '限额生效', 'green'],
  ['budget_recorded', '仅记录用量', 'neutral'],
  ['preparing', '准备环境', 'blue'],
  ['persisting', '保存结果', 'blue'],
  ['skipped', '未执行', 'neutral'],
  ['expired', '已过期', 'neutral'],
  ['invalidated', '已失效', 'neutral'],
];

it.each(OPERATIONAL)('renders %s as %s in the %s tone', (state, label, expected) => {
  const badge = tone(state);
  expect(badge).toHaveTextContent(label);
  expect(badge).toHaveClass(`badge-${expected}`);
});

it('never silently degrades an actionable state to the neutral tone', () => {
  for (const [state, , expected] of OPERATIONAL) {
    if (expected === 'neutral') continue;
    expect(tone(state), `${state} must not be grey`).not.toHaveClass('badge-neutral');
  }
});

it('pins a tone for every state in the map, so a new one cannot arrive untested', () => {
  // The list above is maintained by hand; this makes forgetting to extend it a
  // failure rather than a silent hole. That hole is exactly how the shared-budget
  // states shipped with no tone assertion at all.
  const pinned = new Set(OPERATIONAL.map(([state]) => state));
  const missing = Object.keys(BADGE_STATES).filter((state) => !pinned.has(state));
  expect(missing).toEqual([]);
});

it('agrees with the map on both label and tone for every pinned state', () => {
  // Guard the guard: if the table drifted from the map, the per-state assertions
  // above would be checking the table against itself via the same wrong value.
  for (const [state, label, expected] of OPERATIONAL) {
    const entry = BADGE_STATES[state as keyof typeof BADGE_STATES];
    expect(entry, `${state} must exist in BADGE_STATES`).toBeDefined();
    expect(entry.label, `${state} label`).toBe(label);
    expect(entry.tone, `${state} tone`).toBe(expected);
  }
});

it('gives a budget state passed as its Chinese label the neutral fallback, not its real tone', () => {
  // This is the shape of the fixed defect: the label was handed to `state`, missed
  // the map, and fell through to grey while still reading correctly on screen. So
  // a label assertion alone passes here. Pinning the tone is what distinguishes
  // the two, and the caller-scan test below is what keeps it from recurring.
  for (const [state, label] of OPERATIONAL) {
    const viaLabel = tone(label);
    expect(viaLabel, `${label} is not a state key`).toHaveClass('badge-neutral');
    if (BADGE_STATES[state as keyof typeof BADGE_STATES].tone !== 'neutral') {
      expect(viaLabel).not.toHaveClass(`badge-${BADGE_STATES[state as keyof typeof BADGE_STATES].tone}`);
    }
  }
});

it('still renders an unmapped server state verbatim rather than dropping it', () => {
  // Resource status and approval state arrive as server strings. An unknown one
  // must stay visible; hiding it would be worse than showing a grey chip.
  const badge = tone('some_future_server_state');
  expect(badge).toHaveTextContent('some_future_server_state');
  expect(badge).toHaveClass('badge-neutral');
});

// The original bug passed a Chinese label into `state`. No type can catch that
// while the prop must still accept server-provided strings, so pin it at the
// source instead: every literal handed to `<Badge state=...>` has to be a real
// key of the map.
function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? sources(path) : /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

it('passes only mapped keys as literal Badge states across the whole app', () => {
  const keys = new Set(Object.keys(BADGE_STATES));
  const found: Array<{ file: string; literal: string }> = [];
  for (const file of sources(join(import.meta.dirname, '..', 'src'))) {
    const code = readFileSync(file, 'utf8');
    // Take each <Badge ...> element and read only its `state` attribute, which
    // is either a quoted literal or an expression holding quoted literals.
    for (const element of code.matchAll(/<Badge\b[\s\S]*?\/>/g)) {
      const attribute = /state=(?:"([^"]*)"|\{([\s\S]*?)\}\s*(?:\/>|\n\s*[a-zA-Z-]+=))/.exec(element[0]);
      if (!attribute) continue;
      const literals =
        attribute[1] !== undefined
          ? [attribute[1]]
          : [...attribute[2].matchAll(/'([^']*)'/g)].map((m) => m[1]);
      for (const literal of literals) if (!keys.has(literal)) found.push({ file, literal });
    }
  }
  expect(found).toEqual([]);
  // Guard the guard: the scan has to actually be reading call sites.
  expect(sources(join(import.meta.dirname, '..', 'src')).length).toBeGreaterThan(10);
});
