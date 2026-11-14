import { describe, expect, it } from 'vitest';
import ja from './locales/ja.json';

/** The cashier "opens the register" (レジ開け) everywhere on the opening screen, not "opens the shop" (開店). */
describe('the Japanese opening screen says レジ開け', () => {
  const opening = ja.pos_opening as Record<string, unknown>;

  it('has no 開店 in its texts', () => {
    const offenders = Object.entries(opening).filter(
      ([, value]) => typeof value === 'string' && (value as string).includes('開店')
    );
    expect(offenders).toEqual([]);
  });

  it('names the labels of the screen レジ開け', () => {
    expect(opening.session_details).toBe('レジ開け情報');
    expect(opening.opening_balance).toBe('レジ開け時の釣銭準備金');
    expect(opening.opening_amount).toBe('レジ開け金額');
  });

  it('quotes the zero-balance button as it is written on the button', () => {
    expect(String(opening.zero_balance_warning)).toContain(`「${opening.confirm_zero_balance}」`);
  });
});
