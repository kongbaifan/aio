import { expect, it } from 'vitest';
import { money, remainingMoney } from '../src/money';

// Amounts arrive from the server as decimal strings. `Number()` cannot hold
// every such string exactly and `toFixed` rounds, so both can print a number
// that is not the amount the ledger recorded. These cases pin the rule that
// display never invents, drops or rounds a digit.
it('keeps every digit the server sent', () => {
  expect(money('1.999999')).toBe('1.999999');
  expect(money('2.000001')).toBe('2.000001');
  expect(money('1.500000')).toBe('1.500000');
  expect(money('1000000.000001')).toBe('1000000.000001');
});

it('never rounds a cap up the way toFixed(2) does', () => {
  // Number('9.999999').toFixed(2) === '10.00', which overstates the ceiling.
  expect(money('9.999999')).toBe('9.999999');
  // Number('0.000001').toFixed(2) === '0.00', which hides a real charge.
  expect(money('0.000001')).toBe('0.000001');
});

it('reports the scale the server chose rather than padding it to a familiar width', () => {
  // Trailing zeros state the precision that was recorded, so display neither adds
  // nor removes them: a bare "10" means the server sent an integral amount.
  expect(money('10')).toBe('10');
  expect(money('1.02')).toBe('1.02');
  expect(money('0')).toBe('0');
});

it('does not group thousands, so the figure stays copyable as a decimal', () => {
  expect(money('1000000.000000')).toBe('1000000.000000');
  expect(money('1000000.000000')).not.toContain(',');
});

it('shows an explicit fallback rather than NaN for an absent amount', () => {
  expect(money(null)).toBe('—');
  expect(money(undefined)).toBe('—');
  expect(money('', '未设置')).toBe('未设置');
});

it('falls back rather than presenting unparseable server text as an amount', () => {
  // Number('abc') is NaN, and printing "NaN" on a budget screen is worse than
  // saying nothing. Text that is not a decimal is not an amount, so it is not
  // rendered in an amount column at all.
  expect(money('abc')).toBe('—');
  expect(money('1.0.0')).toBe('—');
  expect(money('abc', '数据异常')).toBe('数据异常');
});

it('derives the remaining amount with exact decimal arithmetic', () => {
  expect(remainingMoney('10', '0.25', '1.02')).toBe('8.73');
  expect(remainingMoney('10.000000', '2.000001', '6.000000')).toBe('1.999999');
  // Binary floating point cannot represent these exactly; scaled integers can.
  expect(remainingMoney('0.3', '0.1', '0.1')).toBe('0.10');
  expect(remainingMoney('1000000.000001', '1000000', '0')).toBe('0.000001');
});

it('clamps an overcommitted pool at zero instead of showing negative headroom', () => {
  // Late or over-estimate supplier charges can push commitments past the cap.
  // That is a real state, but "you may still reserve -3" is not a true claim.
  expect(remainingMoney('10', '9', '4')).toBe('0.00');
});

it('refuses to derive a value it cannot represent exactly', () => {
  expect(remainingMoney('10', 'abc', '0')).toBeNull();
  expect(remainingMoney('10', '0.0000001', '0')).toBeNull();
});

it('shows a negative amount rather than disguising a corrupt row as an unset one', () => {
  // A pool cannot legitimately reach a negative figure: `aio_budget_pools` in
  // schema_v13.py constrains `hard_limit IS NULL OR hard_limit >= 0` and
  // `reserved >= 0 AND consumed >= opening_consumed AND opening_consumed >= 0`,
  // and the admin projection already floors `remaining` at zero. So a minus sign
  // means the data is wrong, not that the amount is small, and the useful answer
  // is to show it: routing it into the "no amount configured" fallback would
  // report a broken row as an unconfigured one and lose the evidence.
  expect(money('-5')).toBe('-5');
  expect(money('-0.000001')).toBe('-0.000001');
  expect(money('-5')).not.toBe('—');
});

it('treats blank server text as no amount, and zero as an amount', () => {
  // Blank is the absent case the fallback exists for. Zero is a configured
  // ceiling with nothing under it, so it must survive as a figure.
  expect(money('   ')).toBe('—');
  expect(money('\t\n')).toBe('—');
  expect(money('   ', '未设置')).toBe('未设置');
  expect(money('0', '未设置')).toBe('0');
  expect(money('0.000000', '未设置')).toBe('0.000000');
});

it('renders the amount without the whitespace the transport added around it', () => {
  expect(money(' 1.5 ')).toBe('1.5');
  expect(remainingMoney(' 10 ', '0', '0')).toBe('10.00');
});

it('prints a seventh decimal verbatim but refuses to compute with it', () => {
  // Section 1 caps transport at six decimals, so this row is already outside the
  // contract. Reproducing every digit keeps it diagnosable, and is still honest:
  // nothing was rounded. Headroom is different — it runs in integers scaled to
  // six decimals, so a seventh digit could only enter by being dropped. Null
  // sends the caller to the qualitative state instead of to a lossy number.
  expect(money('1.0000001')).toBe('1.0000001');
  expect(money('1.12345678901234567890')).toBe('1.12345678901234567890');
  expect(remainingMoney('1.0000001', '0', '0')).toBeNull();
  expect(remainingMoney('10', '0', '0.0000001')).toBeNull();
});

it('renders the contract ceiling and an over-ceiling row without clamping either', () => {
  // `0..1000000` (section 5) is validated when an administrator submits a limit;
  // it is not a display filter. `hard_limit` is Numeric(20,6), so a migrated or
  // legacy row can hold more than the API would now accept. Clamping or hiding
  // it would misstate the ceiling a pool is actually enforcing.
  expect(money('1000000')).toBe('1000000');
  expect(money('1000000.000000')).toBe('1000000.000000');
  expect(money('1000001')).toBe('1000001');
  expect(money('99999999999999.999999')).toBe('99999999999999.999999');
});

it('derives headroom at the ceiling without grouping or float drift', () => {
  // Number(1000000) - Number(999999.999999) is 1.0000000009313226e-6, which
  // toFixed(2) prints as "0.00" and hides the last millionth of the cap.
  expect(remainingMoney('1000000.000000', '999999.999999', '0')).toBe('0.000001');
  expect(remainingMoney('1000000', '0', '0')).toBe('1000000.00');
  expect(remainingMoney('1000000', '0', '0')).not.toContain(',');
});

it('separates a cap that is unconfigured from a cap of zero', () => {
  // Two different persisted states. `hard_limit=null` means this shared ceiling
  // was never enabled: usage is still projected and personal limits still apply
  // (section 1), so there is no headroom figure to state and the caller says so
  // in words. A stored `0` is an enabled ceiling with nothing left under it,
  // which is a number. Rendering both as "0" would claim a limit that does not
  // exist and make an unconfigured pool look exhausted.
  expect(remainingMoney(null, '0', '0')).toBeNull();
  expect(remainingMoney(undefined, '0', '0')).toBeNull();
  expect(remainingMoney('0', '0', '0')).toBe('0.00');
  expect(remainingMoney('0.000000', '0', '0')).toBe('0.000000');
  expect(remainingMoney('0', '0', '0')).not.toBe(remainingMoney(null, '0', '0'));
});

it('carries the widest input scale so no server digit is dropped', () => {
  // Six decimals anywhere in the inputs must reach the result...
  expect(remainingMoney('10', '0.123456', '0')).toBe('9.876544');
  expect(remainingMoney('10', '0', '0.000001')).toBe('9.999999');
  // ...and a coarser set of inputs is still widened to two places rather than
  // printed as a bare integer, so the figure reads as money.
  expect(remainingMoney('10', '0', '0.5')).toBe('9.50');
  expect(remainingMoney('10', '0.1', '0.02')).toBe('9.88');
  expect(remainingMoney('10', null, null)).toBe('10.00');
});

it('reports an exhausted pool at the scale its inputs used', () => {
  // Clamping at zero is not a reason to forget how precisely the pool was
  // measured: "0.000000" against a six-decimal ledger says the subtraction ran
  // at full precision, where a bare "0.00" would understate it.
  expect(remainingMoney('10', '9', '1.000000')).toBe('0.000000');
  expect(remainingMoney('10', '9', '1')).toBe('0.00');
});

it('does not read a blank consumed or reserved figure as zero', () => {
  // `?? '0'` defaults a genuinely absent value only. A blank string is missing
  // data, and scoring it as zero would overstate headroom by the entire unknown
  // amount — the one direction that lets a caller reserve money it does not have.
  expect(remainingMoney('10', '', '0')).toBeNull();
  expect(remainingMoney('10', '0', '   ')).toBeNull();
});
