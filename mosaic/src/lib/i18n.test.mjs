// Run with `yarn test`. The words of the kitchen screen in ja / zh / ko / en; dish names are not
// translated (they come from the ticket). Terms follow docs/design/i18n-design.md chapter 12.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  DEFAULT_LANGUAGE,
  LANGUAGES,
  MESSAGES,
  hasMessage,
  localeOf,
  normalizeLanguage,
  translate,
} from "./i18n.js";

const here = (path) => new URL(path, import.meta.url);
const read = (path) => readFileSync(here(path), "utf8");

test("the screen speaks ja, zh, ko and en, and Japanese is the default", () => {
  assert.deepEqual(LANGUAGES, ["ja", "zh", "ko", "en"]);
  assert.equal(DEFAULT_LANGUAGE, "ja");
});

test("every language has exactly the keys of English, and no empty text", () => {
  const keys = Object.keys(MESSAGES.en).sort();
  for (const lang of LANGUAGES) {
    assert.deepEqual(Object.keys(MESSAGES[lang]).sort(), keys, lang);
    for (const [key, text] of Object.entries(MESSAGES[lang])) {
      assert.ok(typeof text === "string" && text.trim() !== "", `${lang}.${key}`);
    }
  }
});

test("the parameters of a text are the same in every language", () => {
  const params = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
  for (const [key, english] of Object.entries(MESSAGES.en)) {
    for (const lang of LANGUAGES) {
      assert.equal(params(MESSAGES[lang][key]), params(english), `${lang}.${key}`);
    }
  }
});

test("the text is in the language asked for", () => {
  assert.equal(translate("ja", "kot.serve"), "提供");
  assert.equal(translate("en", "kot.serve"), "Serve");
  assert.notEqual(translate("zh", "kot.serve"), translate("ja", "kot.serve"));
  assert.notEqual(translate("ko", "kot.serve"), translate("en", "kot.serve"));
});

test("a missing text is shown in English, and a text nobody has as its key", () => {
  const original = MESSAGES.ko["kot.serve"];
  delete MESSAGES.ko["kot.serve"];
  try {
    assert.equal(translate("ko", "kot.serve"), MESSAGES.en["kot.serve"]);
    assert.equal(hasMessage("ko", "kot.serve"), true); // English has it
  } finally {
    MESSAGES.ko["kot.serve"] = original;
  }
  assert.equal(translate("ja", "no.such.key"), "no.such.key");
  assert.equal(hasMessage("ja", "no.such.key"), false);
});

test("parameters are filled in, every one of them", () => {
  assert.match(translate("ja", "kot.no_active_orders", { production: "寿司場" }), /寿司場/);
  assert.match(translate("en", "kot.old_qty", { qty: 3 }), /3/);
  assert.doesNotMatch(translate("ko", "kot.old_qty", { qty: 3 }), /\{/);
});

test("the language of the user becomes a language of the screen", () => {
  assert.equal(normalizeLanguage("ko"), "ko");
  assert.equal(normalizeLanguage("zh-TW"), "zh");
  assert.equal(normalizeLanguage("en-GB"), "en");
  assert.equal(normalizeLanguage("fr"), "ja");
  assert.equal(normalizeLanguage(undefined), "ja");
  assert.equal(normalizeLanguage(""), "ja");
});

test("the clock is written the way the language writes it", () => {
  assert.equal(localeOf("ja"), "ja-JP");
  assert.equal(localeOf("zh"), "zh-CN");
  assert.equal(localeOf("ko"), "ko-KR");
  assert.equal(localeOf("en"), "en-US");
  assert.equal(localeOf("fr"), "ja-JP");
});

test("the terms of the glossary (i18n-design.md chapter 12)", () => {
  const dup = (lang) => translate(lang, "kot.duplicate");
  assert.match(dup("ja"), /厨房伝票/);
  assert.match(dup("ja"), /担当/);
  assert.match(dup("zh"), /厨房单/);
  assert.match(dup("zh"), /服务员/);
  assert.match(dup("ko"), /주방 전표/);
  assert.match(dup("ko"), /담당/);
  assert.equal(translate("ja", "kot.table"), "テーブル");
  assert.equal(translate("zh", "kot.table"), "桌台");
  assert.equal(translate("ko", "kot.table"), "테이블");
  assert.equal(translate("ja", "production.unit"), "キッチン");
  assert.equal(translate("zh", "production.unit"), "出品厨房");
  assert.equal(translate("ko", "production.unit"), "주방");
  assert.equal(translate("ja", "app.title"), "キッチンディスプレイ");
  assert.equal(translate("zh", "app.title"), "厨房显示屏");
  assert.equal(translate("ko", "app.title"), "주방 디스플레이");
  // a lone total is 合計 / 合计 / 합계
  assert.equal(translate("ja", "production.total"), "合計");
});

test("the status of a ticket is translated when the ticket says it (the type comes from the server)", () => {
  assert.equal(hasMessage("ja", "kot.type.Cancelled"), true);
  assert.equal(hasMessage("ja", "kot.type.Partially cancelled"), true);
  assert.equal(translate("ja", "kot.type.Cancelled"), "取消");
});

// --- the screens use it: no English written into a template ---------------------------------

const SCREENS = [
  "../components/kot.vue",
  "../components/Header.vue",
  "../components/production/ProductionCard.vue",
  "../components/production/ProductionDashboard.vue",
  "../views/Login.vue",
];

function visibleText(source) {
  return source
    .replace(/<script[\s\S]*?<\/script>/g, "")
    .replace(/<style[\s\S]*?<\/style>/g, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/"[^"]*"/g, '""') // attribute values (they may hold `=>` and `>`)
    .replace(/'[^']*'/g, "''")
    .replace(/\{\{[\s\S]*?\}\}/g, "")
    .replace(/<[^>]*>/g, "\n");
}

for (const screen of SCREENS) {
  test(`${screen} has no English text of its own`, () => {
    const words = visibleText(read(screen))
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => /[A-Za-z]{3,}/.test(line));
    assert.deepEqual(words, []);
  });
}

test("the messages in the script are translated too", () => {
  const kot = read("../components/kot.vue");
  for (const text of ["You are online", "You are Offline", "Table/Takeaway info unavailable", "'N/A'"]) {
    assert.ok(!kot.includes(text), text);
  }
  assert.ok(!read("../components/Header.vue").includes('"User"'));
});

test("the fonts include Japanese, Chinese and Korean faces", () => {
  const config = read("../../tailwind.config.js");
  for (const face of ["Noto Sans JP", "Noto Sans SC", "Noto Sans KR"]) {
    assert.ok(config.includes(face), face);
  }
});

test("the word Table is kept apart from the table name by a margin, whatever the language (Vue drops the space after {{ }})", () => {
  const kot = read("../components/kot.vue");
  const label = kot.match(/<span[^>]*class="([^"]*)"\s*>\{\{ \$t\('kot\.table'\) \}\}/);
  assert.ok(label, "the label of the table name");
  assert.match(label[1], /\bmr-1\b/);
});
