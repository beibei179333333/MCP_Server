/* node docs/test_core.js  — offline tests for the browser core logic */
const GE = require("./core.js");
let pass = 0, fail = 0;
function eq(a, b, msg) {
  const A = JSON.stringify(a), B = JSON.stringify(b);
  if (A === B) { pass++; console.log("  ok  " + msg); }
  else { fail++; console.log("  FAIL " + msg + "\n    got " + A + "\n    exp " + B); }
}
function ok(cond, msg) { eq(!!cond, true, msg); }

// link parsing
eq(GE.parseGroupLink("https://t.me/somegroup"), "somegroup", "link: t.me/handle");
eq(GE.parseGroupLink("https://t.me/somegroup/123"), "somegroup", "link: with extra path");
eq(GE.parseGroupLink("@somegroup"), "somegroup", "link: @handle");
eq(GE.parseGroupLink("-1001234567890"), "-1001234567890", "link: numeric id");
eq(GE.parseGroupLink("t.me/+AbCdEf123"), "+AbCdEf123", "link: invite +hash");
eq(GE.parseGroupLink("https://t.me/joinchat/AbCdEf"), "joinchat/AbCdEf", "link: joinchat");
eq(GE.parseGroupLink("not a link !!! 中文"), "", "link: garbage -> empty");
{
  const r = GE.parseMany("https://t.me/g1\n@g1\n-100123, t.me/g2\nbad line!!!");
  eq(r.groups, ["g1", "-100123", "g2"], "parseMany dedup");
  eq(r.skipped, ["bad line!!!"], "parseMany skip");
}

// normalize varied fields
{
  const a = GE.normalizeMember({ userId: 111, userName: "@Alice", firstName: "Al" });
  eq(a.user_id, "111", "normalize id");
  eq(a.username, "Alice", "normalize @ stripped");
  eq(a.full_name, "Al", "normalize full from first");
  const b = GE.normalizeMember({ id: "222", name: "Bob Builder", messages: "57" });
  eq([b.user_id, b.full_name, b.message_count], ["222", "Bob Builder", 57], "normalize alt fields");
}

// dedup + merge + groups union
{
  const recs = [
    GE.normalizeMember({ id: 1, username: "ada", first_name: "Ada" }, "G1"),
    GE.normalizeMember({ id: 1, last_name: "Lovelace", message_count: 10 }, "G2"),
    GE.normalizeMember({ id: 2, username: "linus" }, "G1"),
    GE.normalizeMember({ id: 2, username: "linus" }, "G1"),
  ];
  const { kept, stats } = GE.runPipeline(recs, { filterAds: false });
  eq([stats.seen, stats.unique, stats.merged], [4, 2, 2], "dedup counts");
  const ada = kept.find(m => m.user_id === "1");
  eq([ada.username, ada.last_name, ada.message_count], ["ada", "Lovelace", 10], "merge fields");
  eq(Array.from(ada.groups).sort(), ["G1", "G2"], "merge groups union");
}

// filters
{
  const cfg = { requireUsername: true, filterAds: true, filterBots: true, filterScam: true, adThreshold: 2 };
  ok(GE.classify(GE.normalizeMember({ id: 2, first_name: "NoHandle" }), cfg) === "no_username", "filter no_username");
  ok(GE.classify(GE.normalizeMember({ id: 9, username: "promo", first_name: "广告推广 t.me/xyz" }), cfg) === "ad_marketing", "filter ad");
  ok(GE.classify(GE.normalizeMember({ id: 10, username: "realuser", first_name: "Jane" }), cfg) === null, "keep clean");
  ok(GE.classify(GE.normalizeMember({ id: 12, username: "mybot", is_bot: true }), cfg) === "bot", "filter bot");
}

// extractList envelopes
{
  eq(GE.extractList([{ id: 1 }, { id: 2 }]).list.length, 2, "extract root list");
  const e = GE.extractList({ total: 5, data: [{ id: 1 }] });
  eq([e.list.length, e.total], [1, 5], "extract data+total");
  eq(GE.extractList({ result: { items: [{ id: 1 }, { id: 2 }] } }).list.length, 2, "extract nested");
}

// CSV
{
  const recs = [GE.normalizeMember({ id: 1, username: "a", first_name: "Ann" })];
  const { kept } = GE.runPipeline(recs, { filterAds: false });
  const csv = GE.toCSV(kept, GE.TABLE_COLUMNS);
  ok(csv.includes("a") && csv.split("\r\n").length >= 2, "csv output");
}

// demo data runs through pipeline
{
  const raw = [].concat(
    GE.demoMembers("alpha", 25).map(r => GE.normalizeMember(r, "alpha")),
    GE.demoMembers("beta", 25).map(r => GE.normalizeMember(r, "beta")));
  const { kept, stats } = GE.runPipeline(raw, { requireUsername: true, filterAds: true, filterBots: true, filterScam: true, adThreshold: 2 });
  ok(stats.seen > 0 && stats.kept > 0 && stats.kept <= stats.unique, "demo pipeline sane");
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
