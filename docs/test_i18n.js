/* node docs/test_i18n.js — verify zh/vi parity and that every key used in the
   HTML actually exists in the dictionaries. */
const fs = require("fs");
const path = require("path");
const I18N = require("./i18n.js");
let fail = 0;
const err = m => { console.log("  FAIL " + m); fail++; };
const ok = m => console.log("  ok  " + m);

const zh = Object.keys(I18N.zh).sort();
const vi = Object.keys(I18N.vi).sort();
const onlyZh = zh.filter(k => !I18N.vi[k]);
const onlyVi = vi.filter(k => !I18N.zh[k]);
if (onlyZh.length) err("keys missing in vi: " + onlyZh.join(", ")); else ok("vi has all zh keys");
if (onlyVi.length) err("keys missing in zh: " + onlyVi.join(", ")); else ok("zh has all vi keys");

// check every {placeholder} in zh has a counterpart in vi (template parity)
for (const k of zh) {
  if (!I18N.vi[k]) continue;
  const ph = s => (String(s).match(/\{[a-z]+\}/g) || []).sort().join(",");
  if (ph(I18N.zh[k]) !== ph(I18N.vi[k])) err(`template vars differ for "${k}"`);
}
ok("template variables consistent");

function checkHtml(file) {
  const html = fs.readFileSync(path.join(__dirname, file), "utf-8");
  const used = new Set();
  for (const m of html.matchAll(/data-i18n(?:-ph)?="([^"]+)"/g)) used.add(m[1]);
  // only literal t('key') calls (skip dynamic t('prefix_'+x) concatenations)
  for (const m of html.matchAll(/\bt\('([a-z_0-9]+)'\s*[),]/g)) used.add(m[1]);
  const missing = [...used].filter(k => !I18N.zh[k]);
  if (missing.length) err(`${file}: keys used but not defined: ${missing.join(", ")}`);
  else ok(`${file}: all ${used.size} used keys exist`);
}
checkHtml("index.html");
checkHtml("../group_export/web/index.html");

// dynamic prefixes: ensure every reason_* and col_* key exists
const REASONS = ["no_username","ad_marketing","bot","scam_or_fake","deleted","no_photo",
  "not_premium","not_verified","low_activity","language","random_username"];
const COLS = ["username","full_name","user_id","message_count","is_premium","language_code","groups"];
const dynMissing = [
  ...REASONS.map(r => "reason_" + r),
  ...COLS.map(c => "col_" + c),
].filter(k => !I18N.zh[k] || !I18N.vi[k]);
if (dynMissing.length) err("dynamic keys missing: " + dynMissing.join(", "));
else ok("all reason_*/col_* keys present in both languages");

console.log(fail ? `\n${fail} failed` : "\ni18n OK");
process.exit(fail ? 1 : 0);
