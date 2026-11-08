import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../i18n', () => ({ t: (key: string) => `[${key}]` }));
vi.mock('@ury/ui', () => ({ Spinner: () => createElement('div', null, 'SPINNER') }));
vi.mock('react-router-dom', () => ({ Navigate: ({ to }: { to: string }) => createElement('div', null, `REDIRECT:${to}`) }));

import { DashboardGuardView } from './DashboardGuardView';
import { NO_PERMISSIONS } from '../lib/pos-permissions';

// The dashboard page stands in as a component that records that it was rendered (it would call the sales API).
const render = (permissions: Parameters<typeof DashboardGuardView>[0]['permissions'], gaveUp: boolean) => {
  const dashboard = vi.fn(() => createElement('div', null, 'SALES'));
  const html = renderToStaticMarkup(
    createElement(DashboardGuardView, { permissions, gaveUp, children: createElement(dashboard) }),
  );
  return { html, dashboard };
};

describe('DashboardGuardView', () => {
  it('waiting for the permissions: a spinner, not the page', () => {
    const { html, dashboard } = render(null, false);
    expect(html).toContain('SPINNER');
    expect(dashboard).not.toHaveBeenCalled();
  });

  it('permissions did not arrive in time: the notice and a reload button, not the page, no sales request', () => {
    const { html, dashboard } = render(null, true);
    expect(html).toContain('[pos.permissions_unavailable]');
    expect(html).toContain('<button');
    expect(html).toContain('[pos.reload_page]');
    expect(html).not.toContain('SALES');
    expect(dashboard).not.toHaveBeenCalled();
  });

  it('may see the sales: the page', () => {
    const { html, dashboard } = render({ ...NO_PERMISSIONS, view_dashboard: true }, false);
    expect(html).toContain('SALES');
    expect(dashboard).toHaveBeenCalled();
  });

  it('may not (a waiter): sent to the waiter screen, not the page', () => {
    const { html, dashboard } = render({ ...NO_PERMISSIONS, view_dashboard: false }, true);
    expect(html).toContain('REDIRECT:/order');
    expect(dashboard).not.toHaveBeenCalled();
  });

  it('permissions that arrive after the wait still count', () => {
    const { html } = render({ ...NO_PERMISSIONS, view_dashboard: true }, true);
    expect(html).toContain('SALES');
  });
});
