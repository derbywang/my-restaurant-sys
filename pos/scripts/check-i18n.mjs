// Compares every locale file against en.json (the source of truth) and lists
// missing keys, extra keys and {{placeholder}} mismatches.
//
//   node scripts/check-i18n.mjs            # strict: ja zh ko (exit 1 on any difference); fr ar reported only
//   node scripts/check-i18n.mjs ja ko      # strict for the languages given
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const localesDir = join(dirname(fileURLToPath(import.meta.url)), '../src/i18n/locales');
const STRICT_DEFAULT = ['ja', 'zh', 'ko'];

const flatten = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([key, value]) =>
    value && typeof value === 'object' ? flatten(value, `${prefix}${key}.`) : [[`${prefix}${key}`, value]]
  );

const load = (lang) => new Map(flatten(JSON.parse(readFileSync(join(localesDir, `${lang}.json`), 'utf8'))));
const placeholders = (text) => (String(text).match(/\{\{\w+\}\}/g) ?? []).sort().join(',');

const strict = process.argv.length > 2 ? process.argv.slice(2) : STRICT_DEFAULT;
const languages = readdirSync(localesDir)
  .filter((file) => file.endsWith('.json'))
  .map((file) => file.replace(/\.json$/, ''))
  .filter((lang) => lang !== 'en');

const en = load('en');
let failed = false;

for (const lang of languages) {
  const locale = load(lang);
  const missing = [...en.keys()].filter((key) => !locale.has(key));
  const extra = [...locale.keys()].filter((key) => !en.has(key));
  const badPlaceholders = [...locale.keys()].filter(
    (key) => en.has(key) && placeholders(en.get(key)) !== placeholders(locale.get(key))
  );
  const nonStrings = [...locale.entries()].filter(([, value]) => typeof value !== 'string').map(([key]) => key);

  const isStrict = strict.includes(lang);
  const clean = !missing.length && !extra.length && !badPlaceholders.length && !nonStrings.length;
  console.log(`\n${lang}${isStrict ? '' : ' (not enforced)'}: ${clean ? 'OK' : 'DIFFERENCES'}  [${locale.size}/${en.size} keys]`);
  for (const [label, keys] of [
    ['missing', missing],
    ['extra', extra],
    ['placeholder mismatch', badPlaceholders],
    ['non-string value', nonStrings],
  ]) {
    if (keys.length) console.log(`  ${label} (${keys.length}):\n    ${keys.join('\n    ')}`);
  }
  if (isStrict && !clean) failed = true;
}

process.exit(failed ? 1 : 0);
