import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// A staff member picks the table by its name on the card. When the name was cut to "MD..." (a badge, a
// button and a menu share the row) the wrong table was opened. The name must wrap, not be cut.
const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

describe('the table name on a card', () => {
  it('is never cut with an ellipsis on the table page', () => {
    const source = read('./TableCard.tsx');
    const name = source.match(/<span[^>]*>\s*\{table\.name\}\s*<\/span>/);
    expect(name).not.toBeNull();
    expect(name![0]).not.toMatch(/truncate/);
    expect(name![0]).toMatch(/break-words/);
  });

  it('is never cut with an ellipsis on the captain\'s table list', () => {
    const source = read('../captain/components/CaptainTableCard.tsx');
    const name = source.match(/<span[^>]*>\s*\{table\.name\}\s*<\/span>/);
    expect(name).not.toBeNull();
    expect(name![0]).not.toMatch(/truncate/);
    expect(name![0]).toMatch(/break-words/);
  });
});
