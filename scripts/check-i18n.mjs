// Compares every locale file of each app against that app's en.json (the source
// of truth) and lists missing keys, extra keys and {{placeholder}} mismatches.
//
//   node scripts/check-i18n.mjs                  # all apps; ja zh ko must match en exactly (exit 1 otherwise)
//   node scripts/check-i18n.mjs pos              # one app (pos | frontend)
//   node scripts/check-i18n.mjs pos --lang ja ko # restrict the enforced languages
//
// Other locale files (pos: fr, ar) are reported but not enforced.
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const APPS = ['pos', 'frontend'];
const STRICT_DEFAULT = ['ja', 'zh', 'ko'];

const args = process.argv.slice(2);
const langIndex = args.indexOf('--lang');
const strict = langIndex >= 0 ? args.slice(langIndex + 1) : STRICT_DEFAULT;
const requested = (langIndex >= 0 ? args.slice(0, langIndex) : args).filter(Boolean);
const apps = requested.length ? requested : APPS;

const flatten = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([key, value]) =>
    value && typeof value === 'object' ? flatten(value, `${prefix}${key}.`) : [[`${prefix}${key}`, value]]
  );
const placeholders = (text) => (String(text).match(/\{\{\w+\}\}/g) ?? []).sort().join(',');

let failed = false;

for (const app of apps) {
  const localesDir = join(root, app, 'src/i18n/locales');
  if (!existsSync(localesDir)) {
    console.log(`\n[${app}] no locales directory: ${localesDir}`);
    failed = true;
    continue;
  }
  const load = (lang) =>
    new Map(flatten(JSON.parse(readFileSync(join(localesDir, `${lang}.json`), 'utf8'))));
  const languages = readdirSync(localesDir)
    .filter((file) => file.endsWith('.json'))
    .map((file) => file.replace(/\.json$/, ''))
    .filter((lang) => lang !== 'en');

  const en = load('en');
  console.log(`\n[${app}] en: ${en.size} keys`);

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
    console.log(`  ${lang}${isStrict ? '' : ' (not enforced)'}: ${clean ? 'OK' : 'DIFFERENCES'}  [${locale.size}/${en.size} keys]`);
    for (const [label, keys] of [
      ['missing', missing],
      ['extra', extra],
      ['placeholder mismatch', badPlaceholders],
      ['non-string value', nonStrings],
    ]) {
      if (keys.length) console.log(`    ${label} (${keys.length}):\n      ${keys.join('\n      ')}`);
    }
    if (isStrict && !clean) failed = true;
  }

  // An enforced language with no file at all is also a failure.
  for (const lang of strict) {
    if (lang !== 'en' && !languages.includes(lang)) {
      console.log(`  ${lang}: MISSING FILE`);
      failed = true;
    }
  }
}

process.exit(failed ? 1 : 0);
