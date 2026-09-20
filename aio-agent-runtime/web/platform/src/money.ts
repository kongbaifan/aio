// Money on this platform is a server-side decimal, transported as a string, and
// carries at most six fractional digits (see platform-shared-budget-contract.md
// section 1). Two habits corrupt that:
//
//   Number('1.000000000000000001')  // -> 1        binary float cannot hold it
//   Number(x).toFixed(2)            // -> rounds a financial fact for display
//
// So amounts that are facts are never parsed at all: they are rendered exactly
// as the server sent them. Only a value we must *derive* (headroom) is computed,
// and that is done in scaled integers via BigInt so no rounding can occur.

/** Largest fractional precision the billing contract permits. */
const SCALE = 6;
const DECIMAL = /^-?\d+(?:\.\d+)?$/;

function parse(value: string): { units: bigint; scale: number } | null {
  const text = value.trim();
  if (!DECIMAL.test(text)) return null;
  const [whole, fraction = ''] = text.replace('-', '').split('.');
  // More precision than the contract allows is not silently truncated; the
  // caller is told it cannot be represented rather than shown a rounded number.
  if (fraction.length > SCALE) return null;
  const units = BigInt(whole + fraction.padEnd(SCALE, '0'));
  return { units: text.startsWith('-') ? -units : units, scale: fraction.length };
}

function render(units: bigint, scale: number): string {
  const negative = units < 0n;
  const digits = (negative ? -units : units).toString().padStart(SCALE + 1, '0');
  const whole = digits.slice(0, -SCALE);
  const fraction = digits.slice(-SCALE).slice(0, Math.max(scale, 0));
  return `${negative ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}`;
}

/**
 * Render a server decimal string for display without altering its value.
 *
 * The string is passed through verbatim, so `1.999999` stays `1.999999` and a
 * migrated `1.500000` is not shortened to `1.5` — trailing zeros are themselves
 * a statement about the precision that was recorded. `null`, `undefined` and
 * blank mean "no amount configured", which is a real persisted state and gets
 * the caller's wording rather than a fabricated `0`.
 */
export function money(value: string | null | undefined, fallback = '—'): string {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  if (!text || !DECIMAL.test(text)) return fallback;
  return text;
}

/**
 * Headroom still available for new reservations: `limit - consumed - reserved`.
 *
 * Returns `null` when any input is absent or carries precision this contract
 * cannot represent, so callers show the qualitative state instead of a number
 * they cannot stand behind. The result is clamped at zero: external late or
 * over-estimate charges can legitimately push commitments past the cap, but
 * "you may still reserve a negative amount" is not a true statement about it.
 * The scale is the widest scale the server used, minimum two, so no input digit
 * is ever dropped.
 */
export function remainingMoney(
  limit: string | null | undefined,
  consumed: string | null | undefined,
  reserved: string | null | undefined,
): string | null {
  if (limit === null || limit === undefined) return null;
  const parts = [limit, consumed ?? '0', reserved ?? '0'].map((value) => parse(String(value)));
  if (parts.some((part) => part === null)) return null;
  const [cap, spent, held] = parts as Array<{ units: bigint; scale: number }>;
  const left = cap.units - spent.units - held.units;
  const scale = Math.max(2, cap.scale, spent.scale, held.scale);
  return render(left > 0n ? left : 0n, scale);
}
