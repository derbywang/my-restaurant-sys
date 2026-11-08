import { describe, expect, it, vi } from 'vitest';
import { chooseLanguage } from './choose-language';

describe('chooseLanguage', () => {
  it('saves the language that was picked', async () => {
    const onSelect = vi.fn().mockResolvedValue(undefined);
    const ok = await chooseLanguage({ code: 'zh', onSelect, onFailure: vi.fn() });
    expect(ok).toBe(true);
    expect(onSelect).toHaveBeenCalledWith('zh');
  });

  // Two windows of the same account: one switched the server to zh, this one still shows ja. Picking ja here must
  // save ja, not do nothing (the old menu skipped it because it equalled the language the page showed).
  it('saves the language even when it is the one the page shows', async () => {
    const onSelect = vi.fn().mockResolvedValue(undefined);
    const ok = await chooseLanguage({ code: 'ja', onSelect, onFailure: vi.fn() });
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith('ja');
    expect(ok).toBe(true);
  });

  it('reports a failed save and does not claim success', async () => {
    const boom = new Error('offline');
    const onFailure = vi.fn();
    const ok = await chooseLanguage({ code: 'zh', onSelect: vi.fn().mockRejectedValue(boom), onFailure });
    expect(ok).toBe(false);
    expect(onFailure).toHaveBeenCalledWith(boom);
  });

  it('reports a failed save of the language the page shows too', async () => {
    const onFailure = vi.fn();
    const ok = await chooseLanguage({ code: 'ja', onSelect: vi.fn().mockRejectedValue(new Error('x')), onFailure });
    expect(ok).toBe(false);
    expect(onFailure).toHaveBeenCalledTimes(1);
  });
});
