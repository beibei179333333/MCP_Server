/* 群成员导出 · 纯浏览器核心逻辑（无 DOM / 无网络，便于测试与复用） */
(function (root) {
  "use strict";

  const AD_KEYWORDS = [
    "广告","推广","营销","引流","招商","代理","代充","承接","出售","出粉",
    "卖","购买","招聘","兼职","刷单","刷量","粉丝","拉人","拉群","建群",
    "加微","加我","私聊","联系","客服","在线","咨询","办理","接单","接业务",
    "博彩","菠菜","彩票","棋牌","赌","色情","约炮","约","贷款","网赚","赚钱",
    "usdt","u商","承兑","跑分","支付","通道","三方","四方",
    "飞机号","tg号","协议号","白号","老号","实名","解封","群发",
    "机器人","脚本","软件","破解","vpn","翻墙","节点","梯子",
    "promo","promotion","marketing","advertis","casino","betting","loan",
    "crypto","forex","invest","earn money","make money","free money",
    "click here","join now","subscribe","follow me","dm me","contact me",
    "for sale","cheap","discount","telegram.me","t.me/","wa.me",
    "official","support team","admin","airdrop","giveaway","presale",
  ];

  const FIELD_ALIASES = {
    user_id: ["user_id","userId","id","uid","tg_id","tgId","telegram_id"],
    username: ["username","user_name","userName","login","handle","nick"],
    first_name: ["first_name","firstName","first","fname"],
    last_name: ["last_name","lastName","last","lname"],
    full_name: ["full_name","fullName","name","display_name","displayName","title"],
    phone: ["phone","phone_number","phoneNumber","mobile"],
    bio: ["bio","about","description","status","signature"],
    is_bot: ["is_bot","isBot","bot"],
    is_premium: ["is_premium","isPremium","premium"],
    is_verified: ["is_verified","isVerified","verified"],
    is_scam: ["is_scam","isScam","scam"],
    is_fake: ["is_fake","isFake","fake"],
    language_code: ["language_code","languageCode","lang","language"],
    join_date: ["join_date","joinDate","joined_at","joinedAt","join_time"],
    last_seen: ["last_seen","lastSeen","last_online","lastOnline","last_active"],
    message_count: ["message_count","messageCount","messages","msg_count","msgCount"],
    has_photo: ["has_photo","hasPhoto","photo","avatar","has_avatar","profile_photo","photo_url"],
  };

  const EXPORT_COLUMNS = [
    "user_id","username","full_name","first_name","last_name","phone",
    "is_bot","is_premium","is_verified","is_scam","is_fake","has_photo",
    "language_code","message_count","join_date","last_seen","bio","groups",
  ];
  const TABLE_COLUMNS = ["username","full_name","user_id","message_count",
    "is_premium","language_code","groups"];
  const COLUMN_LABELS = {
    user_id:"用户ID", username:"用户名", full_name:"昵称", first_name:"名",
    last_name:"姓", phone:"电话", is_bot:"机器人", is_premium:"会员",
    is_verified:"认证", is_scam:"诈骗", is_fake:"仿冒", has_photo:"头像",
    language_code:"语言", message_count:"消息数", join_date:"加入时间",
    last_seen:"最后在线", bio:"简介", groups:"所属群",
  };

  function first(d, keys) {
    for (const k of keys) {
      if (d && d[k] !== undefined && d[k] !== null && d[k] !== "" &&
          !(Array.isArray(d[k]) && d[k].length === 0)) return d[k];
    }
    return null;
  }
  function toBool(v) {
    if (typeof v === "boolean") return v;
    if (typeof v === "number") return v !== 0;
    if (typeof v === "string") return ["1","true","yes","y","t"].includes(v.trim().toLowerCase());
    return false;
  }
  function cleanUsername(v) {
    if (v == null) return "";
    let s = String(v).trim();
    if (s.startsWith("@")) s = s.slice(1);
    return s;
  }
  // tri-state: true / false / null(unknown, field not provided)
  function toPhoto(v) {
    if (v === undefined || v === null || v === "") return null;
    if (typeof v === "boolean") return v;
    if (typeof v === "number") return v !== 0;
    const s = String(v).trim().toLowerCase();
    if (["0","false","no","none","null"].includes(s)) return false;
    return true; // a url / id / "true" => has photo
  }

  function normalizeMember(rec, group) {
    if (typeof rec !== "object" || rec === null) rec = { value: rec };
    const v = {};
    for (const c in FIELD_ALIASES) v[c] = first(rec, FIELD_ALIASES[c]);
    const fn = (v.first_name || "").toString().trim();
    const ln = (v.last_name || "").toString().trim();
    let full = (v.full_name || "").toString().trim();
    if (!full) full = [fn, ln].filter(Boolean).join(" ").trim();
    let mc = parseInt(v.message_count, 10); if (isNaN(mc)) mc = 0;
    const m = {
      user_id: (v.user_id == null ? "" : String(v.user_id).trim()),
      username: cleanUsername(v.username),
      first_name: fn, last_name: ln, full_name: full,
      phone: (v.phone == null ? "" : String(v.phone).trim()),
      bio: (v.bio == null ? "" : String(v.bio).trim()),
      is_bot: toBool(v.is_bot), is_premium: toBool(v.is_premium),
      is_verified: toBool(v.is_verified), is_scam: toBool(v.is_scam),
      is_fake: toBool(v.is_fake),
      language_code: (v.language_code == null ? "" : String(v.language_code).trim()),
      join_date: (v.join_date == null ? "" : String(v.join_date).trim()),
      last_seen: (v.last_seen == null ? "" : String(v.last_seen).trim()),
      message_count: mc, has_photo: toPhoto(v.has_photo), groups: new Set(),
    };
    if (group) m.groups.add(String(group));
    return m;
  }

  function dedupKey(m) {
    if (m.user_id) return "id:" + m.user_id;
    if (m.username) return "un:" + m.username.toLowerCase();
    return "nm:" + m.full_name.toLowerCase();
  }
  function mergeMember(a, b) {
    for (const k of ["user_id","username","first_name","last_name","full_name",
                     "phone","bio","language_code","join_date","last_seen"]) {
      if (!a[k] && b[k]) a[k] = b[k];
    }
    for (const k of ["is_bot","is_premium","is_verified","is_scam","is_fake"]) {
      a[k] = a[k] || b[k];
    }
    a.message_count = Math.max(a.message_count, b.message_count);
    b.groups.forEach(g => a.groups.add(g));
  }

  const URL_RE = /(https?:\/\/|t\.me\/|telegram\.me\/|wa\.me\/|@[A-Za-z0-9_]{4,})/i;
  const PHONE_RE = /(?:\+?\d[\s-]?){9,}/;
  const EMOJI_RE = /\p{Extended_Pictographic}/gu;

  function haystack(m) {
    return [m.username, m.full_name, m.first_name, m.last_name, m.bio]
      .filter(Boolean).join(" ").toLowerCase();
  }
  const RANDOM_UN_RE = /^[a-z]?\d{5,}$|^user\d{3,}$|^[a-z]{1,2}\d{4,}$/i;
  function adScore(m, cfg) {
    const text = haystack(m);
    let score = 0;
    const kws = (cfg.adKeywords || AD_KEYWORDS).concat(cfg.extraAdKeywords || []);
    for (const kw of kws) if (kw && text.includes(String(kw).toLowerCase())) score += 1;
    const blob = [m.username, m.full_name, m.bio].filter(Boolean).join(" ");
    if (URL_RE.test(blob)) score += 2;
    if (PHONE_RE.test(m.full_name) || PHONE_RE.test(m.bio)) score += 2;
    const em = (m.full_name.match(EMOJI_RE) || []).length;
    if (em >= (cfg.emojiLimit || 4)) score += 1;
    if (m.is_scam || m.is_fake) score += 3;
    return score;
  }
  function classify(m, cfg) {
    // 白名单：用户名在白名单里则永不过滤
    if (cfg.whitelist && cfg.whitelist.length && m.username &&
        cfg.whitelist.includes(m.username.toLowerCase())) return null;
    // 已注销 / 空白账号：既无用户名也无任何昵称
    if (cfg.filterDeleted && !m.username && !m.full_name) return "deleted";
    if (cfg.requireUsername && !m.username) return "no_username";
    if (cfg.filterBots && m.is_bot) return "bot";
    if (cfg.filterScam && (m.is_scam || m.is_fake)) return "scam_or_fake";
    if (cfg.verifiedOnly && !m.is_verified) return "not_verified";
    if (cfg.premiumOnly && !m.is_premium) return "not_premium";
    if (cfg.noPhoto && m.has_photo === false) return "no_photo";  // 仅在接口明确返回“无头像”时过滤
    if (cfg.minMessages && cfg.minMessages > 0 && m.message_count < cfg.minMessages)
      return "low_activity";
    if (cfg.languageKeep && cfg.languageKeep.length && m.language_code &&
        !cfg.languageKeep.includes(m.language_code.toLowerCase())) return "language";
    if (cfg.filterRandomUsername && m.username && RANDOM_UN_RE.test(m.username))
      return "random_username";
    if (cfg.filterAds && adScore(m, cfg) >= (cfg.adThreshold || 2)) return "ad_marketing";
    return null;
  }

  function runPipeline(rawMembers, cfg) {
    const stats = { seen: 0, unique: 0, merged: 0, filtered: {}, kept: 0 };
    const index = new Map();
    for (const m of rawMembers) {
      stats.seen += 1;
      const key = dedupKey(m);
      if (index.has(key)) { mergeMember(index.get(key), m); stats.merged += 1; }
      else index.set(key, m);
    }
    const deduped = Array.from(index.values());
    stats.unique = deduped.length;
    const kept = [], removed = [];
    for (const m of deduped) {
      const reason = classify(m, cfg);
      if (reason) { stats.filtered[reason] = (stats.filtered[reason] || 0) + 1; removed.push({ m, reason }); }
      else kept.push(m);
    }
    stats.kept = kept.length;
    stats.total_filtered = removed.length;
    kept.sort((a, b) => (b.message_count - a.message_count) ||
      a.username.toLowerCase().localeCompare(b.username.toLowerCase()) ||
      a.user_id.localeCompare(b.user_id));
    return { kept, removed, stats };
  }

  function toRow(m) {
    const r = {};
    for (const c of EXPORT_COLUMNS) {
      if (c === "groups") r[c] = Array.from(m.groups).sort().join(",");
      else if (c === "has_photo") r[c] = m.has_photo === null ? "" : (m.has_photo ? "是" : "否");
      else r[c] = m[c];
    }
    return r;
  }
  function toCSV(members, columns) {
    columns = columns || EXPORT_COLUMNS;
    const esc = v => {
      if (v === null || v === undefined) v = "";
      v = String(v);
      return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
    };
    const lines = [columns.join(",")];
    for (const m of members) {
      const row = toRow(m);
      lines.push(columns.map(c => esc(row[c])).join(","));
    }
    return "﻿" + lines.join("\r\n"); // BOM so Excel reads UTF-8
  }
  function toJSON(members) {
    return JSON.stringify(members.map(toRow), null, 2);
  }

  // ---- link parsing ----
  const SCHEME_RE = /^[a-z]+:\/\//i;
  function parseGroupLink(raw) {
    let s = (raw || "").trim().replace(/^[,;|"'\s\t]+|[,;|"'\s\t]+$/g, "");
    if (!s) return "";
    if (/^-?\d{5,}$/.test(s)) return s;
    if (s.startsWith("@")) return s.slice(1).replace(/\/+$/g, "");
    let body = s.replace(SCHEME_RE, "").replace(/^www\./i, "");
    const m = body.match(/^(?:t\.me|telegram\.me|telegram\.dog)\/(.+)$/i);
    if (m) {
      let path = m[1].replace(/^\/+|\/+$/g, "");
      if (path.startsWith("+")) return path;
      if (path.toLowerCase().startsWith("joinchat/")) return path;
      return path.split("/")[0].split("?")[0];
    }
    const head = body.split("/")[0].split("?")[0];
    if (head.startsWith("+") && /^\+[A-Za-z0-9_-]{4,}$/.test(head)) return head;
    if (/^[A-Za-z0-9_]{4,32}$/.test(head)) return head;
    return "";
  }
  function parseMany(text) {
    const parts = (text || "").split(/[\n\r,]+/);
    const groups = [], seen = new Set(), skipped = [];
    for (let p of parts) {
      p = p.trim(); if (!p) continue;
      const g = parseGroupLink(p);
      if (!g) { skipped.push(p); continue; }
      const key = g.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key); groups.push(g);
    }
    return { groups, skipped };
  }

  // ---- demo data (preview without network) ----
  function demoMembers(group, n) {
    n = n || 25;
    const first = ["小明","Alice","李雷","Bob","韩梅梅","Carol","王伟","Dave","赵敏"];
    const spam = ["出售飞机号 t.me/spam","广告推广加我","USDT承兑通道","招商代理👑👑👑👑","网赚兼职日入过千"];
    const pick = a => a[Math.floor(Math.random() * a.length)];
    const out = [];
    for (let i = 0; i < n; i++) {
      const r = Math.random();
      if (r < 0.18) out.push({ id: 90000 + i, username: "promo" + i, first_name: pick(spam), message_count: Math.floor(Math.random() * 4), has_photo: false });
      else if (r < 0.30) out.push({ id: 80000 + i, first_name: pick(first), message_count: Math.floor(Math.random() * 50), has_photo: Math.random() < 0.5 });
      else if (r < 0.36) out.push({ id: 70000 + i, username: "x" + i, is_scam: true, first_name: "可疑账号" });
      else out.push({ id: 1000 + i, username: "user_" + group.slice(0, 4) + "_" + i, first_name: pick(first), is_premium: Math.random() < 0.2, language_code: pick(["zh","en","ru"]), message_count: 1 + Math.floor(Math.random() * 500), has_photo: Math.random() < 0.85 });
    }
    out.push({ id: 1000, username: "user_" + group.slice(0, 4) + "_0", last_name: "(合并)" });
    out.push({ id: 60001 }); // 已注销账号：无用户名无昵称
    return out;
  }

  // ---- response extraction (mirror of server-side) ----
  const ENVELOPE_KEYS = ["data","items","result","results","list","members","rows","records","users","participants","content"];
  const TOTAL_KEYS = ["total","totalCount","total_count","count","totalRecords"];
  function extractList(payload) {
    let total = null;
    if (Array.isArray(payload)) return { list: payload.filter(x => x && typeof x === "object"), total: null };
    if (payload && typeof payload === "object") {
      for (const tk of TOTAL_KEYS) if (typeof payload[tk] === "number") { total = payload[tk]; break; }
      for (const key of ENVELOPE_KEYS) {
        const val = payload[key];
        if (Array.isArray(val)) return { list: val.filter(x => x && typeof x === "object"), total };
        if (val && typeof val === "object") {
          const inner = extractList(val);
          if (inner.list.length) return { list: inner.list, total: total != null ? total : inner.total };
        }
      }
      for (const k in payload) {
        const val = payload[k];
        if (Array.isArray(val) && val.length && typeof val[0] === "object") return { list: val, total };
      }
    }
    return { list: [], total };
  }

  const GE = {
    AD_KEYWORDS, EXPORT_COLUMNS, TABLE_COLUMNS, COLUMN_LABELS,
    normalizeMember, dedupKey, mergeMember, adScore, classify, runPipeline,
    toRow, toCSV, toJSON, parseGroupLink, parseMany, demoMembers, extractList,
  };
  root.GE = GE;
  if (typeof module !== "undefined" && module.exports) module.exports = GE;
})(typeof globalThis !== "undefined" ? globalThis : this);
