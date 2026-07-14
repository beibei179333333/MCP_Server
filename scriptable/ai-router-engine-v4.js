/* =====================================================================
 *  AI 智能路由引擎 4.0  —  iPhone 操作按钮 × Scriptable × 硅基流动(SiliconFlow)
 * ---------------------------------------------------------------------
 *  相比 3.3 新增（v4.0 大版本）：
 *    ⑫ 多模型智能路由：翻译用小快模型、代码用代码模型、长文推理用 R1，兜底用 V3
 *      （模型对应表在 CONFIG.MODEL_MAP，可按你在硅基流动能用的模型自行替换）。
 *    ⑬ Token 用量统计 + 超阈值提醒：每次调用累计当月用量，超过阈值提醒一次，
 *      中文菜单「📊 本月用量」可随时查看。
 *    ⑭ Function Calling（AI 执行操作）：中文菜单「🤖 AI 执行操作」可让 AI 直接
 *      建日历事件 / 发 Telegram——每个动作执行前都会弹窗请你逐次确认授权。
 *    ⑮ 本地长期记忆 RAG：把历史向量化存本地，处理中文业务时自动检索最相似的
 *      过往记录注入上下文，越用越懂你的偏好（用硅基流动的 Embedding 模型）。
 *    ⑯ 每周 Prompt 自动调优：定期读历史，自动总结一份「用户画像」注入系统提示，
 *      也可在菜单「🧬 自我进化」手动触发。
 *
 *  相比 3.2 新增：
 *    ⑪ AI 供应商切换到「硅基流动 SiliconFlow」（OpenAI 兼容）：文本、备用、识图
 *      三个模型统一走硅基流动，一个 API Key 全搞定，不再需要分别配置 DeepSeek
 *      官方和识图模型。文本默认 deepseek-ai/DeepSeek-V3，备用 deepseek-ai/DeepSeek-R1，
 *      识图默认 Qwen/Qwen2.5-VL-72B-Instruct（都可在 CONFIG 里改）。
 *
 *  相比 3.1 新增：
 *    ⑧ 流式响应 + 实时预览：开启 CONFIG.STREAM_ENABLED 后，AI 回复会在一个
 *      WebView 里逐字流式显示（走 SSE），而不是干等 90 秒才看到结果。
 *      Scriptable 的 Request 本身不支持分块读取，因此借道 WebView 的
 *      fetch()/ReadableStream 实现真流式；一旦请求失败（例如网络环境不支持
 *      跨域流式读取），自动静默降级为原来的一次性请求，不影响可用性。
 *    ⑨ 语音播报（TTS）/"免视"模式：CONFIG.TTS_AFTER_PROCESS 打开后，每次处理
 *      完成会自动朗读结果，方便开车 / 双手不便的场景。也支持不改配置、按次
 *      触发：把操作按钮绑定的快捷指令换成"询问的文本"传入 "speak" 参数（或
 *      URL Scheme 加 ?speak=1）即可临时开启朗读，不影响默认静默模式。
 *    ⑩ 多步串联：中文业务菜单 / 代码诊断菜单里新增"🔗 多步串联"，可依次勾选
 *      多个已有功能，上一步的输出自动作为下一步的输入，中间步骤不打扰，只在
 *      最后展示 / 复制 / 播报最终结果。
 *
 *  相比 3.0 新增：
 *    ⑦ 新增分支 E：剪贴板里是聊天截图 → 识图模型读对话 → 生成 3 种推荐回复，
 *      点选即复制到剪贴板（识图模型与文本共用同一个硅基流动 Key，无需单独配置）
 *
 *  相比 2.0 新增：
 *    ① 密钥迁移 Keychain（明文只在首次运行时输入一次，之后本地加密存储）
 *    ② 语言检测升级：不再只识别英文，任意非中文语言都会被路由到翻译流
 *    ③ 新增分支 D：代码 / 报错日志 检测 → 专属代码诊断菜单
 *    ④ 本地历史记录（JSON 落盘，可在中文菜单里查看最近 N 条）
 *    ⑤ 短时缓存：同一段文本 + 同一分支，N 分钟内重复触发直接复用结果
 *    ⑥ 主模型失败自动切换备用模型（容灾）
 *
 *  工作流：
 *    先看剪贴板是否为图片 → 是聊天截图 → 分支 E：识图 + 推荐回复
 *    否则读剪贴板文本 → 智能路由
 *      ├─ 分支 A：含 URL     → 抓取网页正文 → AI 深度摘要
 *      ├─ 分支 D：像代码/日志 → 代码诊断菜单（解释/找Bug/优化/加注释）
 *      ├─ 分支 B：非中文文本  → 无感翻译 → 结果覆盖剪贴板 + 系统通知
 *      └─ 分支 C：中文文本   → 原生菜单（9 路固化流，含"查看历史"）
 *    所有分支结束后 → 结构化等宽消息 无感同步到 Telegram Bot
 *
 *  绑定操作按钮：设置 → 操作按钮 → 快捷指令 → 选择「Run Script」
 * ===================================================================== */

// ╔════════════════════════ ① 配 置 区 ═══════════════════════════╗
// ║  敏感信息（API Key / Bot Token / Chat ID）已迁移到 Keychain。      ║
// ║  首次运行会弹窗要求输入一次，之后自动读取，不再明文保存在脚本里。  ║
// ╚════════════════════════════════════════════════════════════════╝
const CONFIG = {
  // AI 供应商：硅基流动 SiliconFlow（OpenAI 兼容接口），文本 / 备用 / 识图共用同一个 Key
  API_URL: "https://api.siliconflow.cn/v1/chat/completions",
  MODEL: "deepseek-ai/DeepSeek-V3",              // 文本主模型
  FALLBACK_MODEL: "deepseek-ai/DeepSeek-R1",     // 主模型连续失败后自动切换的备用模型
  VISION_MODEL: "Qwen/Qwen2.5-VL-72B-Instruct",  // 识图（聊天截图）模型

  TEMPERATURE: 0.3,
  TIMEOUT_SECONDS: 90,
  MAX_RETRY: 2,
  MAX_WEB_CHARS: 8000,
  MAX_TOKENS: 2048,

  CACHE_MINUTES: 10,     // 相同文本+分支，多少分钟内直接复用缓存结果
  HISTORY_MAX: 200,      // 本地历史最多保留多少条（超出自动裁剪最旧的）

  STREAM_ENABLED: true,      // 是否尝试用 WebView 实时流式展示 AI 输出；失败会自动降级为普通请求
  TTS_AFTER_PROCESS: false,  // 是否在每次处理完成后自动朗读结果（也可按次通过 Shortcut 参数临时开启）

  // —— v4.0 —— 多模型路由表：按任务类型选最合适的模型（都可换成你在硅基流动能用的模型）
  MODEL_MAP: {
    translate: "Qwen/Qwen2.5-7B-Instruct",   // 翻译：轻量极速
    summary:   "Qwen/Qwen2.5-7B-Instruct",   // 网页摘要：性价比高
    code:      "deepseek-ai/DeepSeek-V3",     // 代码：能力强
    reasoning: "deepseek-ai/DeepSeek-R1",     // 长文 / 复杂推理
    default:   "deepseek-ai/DeepSeek-V3",     // 兜底
  },

  // —— v4.0 —— Function Calling（让 AI 执行日历 / Telegram 等操作，每次执行前都要确认）
  ENABLE_TOOLS: true,
  TOOL_MODEL: "deepseek-ai/DeepSeek-V3",      // 用于工具调用、需支持 function calling 的模型

  // —— v4.0 —— 本地长期记忆 RAG（向量检索历史，注入上下文）
  RAG_ENABLED: true,
  EMBEDDING_API_URL: "https://api.siliconflow.cn/v1/embeddings",
  EMBEDDING_MODEL: "BAAI/bge-large-zh-v1.5",
  RAG_TOP_K: 3,              // 每次检索注入多少条相似历史
  RAG_MAX_ENTRIES: 100,      // 本地向量库最多保留多少条

  // —— v4.0 —— Token 用量统计
  TOKEN_ALERT_THRESHOLD: 2000000,  // 单月累计超过该 Token 数提醒一次（设为 0 关闭提醒）

  // —— v4.0 —— 每周 Prompt 自动调优（生成"用户画像"注入系统提示）
  SELF_EVOLVE_ENABLED: true,
  SELF_EVOLVE_DAYS: 7,       // 每隔多少天自动进化一次
};

const KC_KEYS = {
  API_KEY: "router_siliconflow_api_key", // 硅基流动 API Key（文本 + 识图共用）
  TG_BOT_TOKEN: "router_tg_bot_token",
  TG_CHAT_ID: "router_tg_chat_id",
};

// ╔═══════════════════════ ② 工 具 函 数 ══════════════════════════╗

async function notify(title, body, sound = "default") {
  try {
    const n = new Notification();
    n.title = title;
    n.body = (body || "").slice(0, 1500);
    n.sound = sound;
    await n.schedule();
  } catch (e) {
    console.error("通知发送失败: " + e);
  }
}

async function fail(stage, err) {
  const msg = (err && err.message) ? err.message : String(err);
  console.error(`[${stage}] ${msg}`);
  await notify(`❌ ${stage}失败`, msg, "failure");
}

async function alertBox(title, message) {
  const a = new Alert();
  a.title = title;
  a.message = message;
  a.addCancelAction("知道了");
  await a.presentAlert();
}

/** 弹出单行文本输入框，用于首次配置密钥 */
async function promptText(title, message, placeholder) {
  const a = new Alert();
  a.title = title;
  a.message = message;
  a.addTextField(placeholder || "", "");
  a.addAction("保存");
  a.addCancelAction("取消");
  const idx = await a.presentAlert();
  if (idx === -1) return null;
  return a.textFieldValue(0).trim();
}

function timestamp() {
  const df = new DateFormatter();
  df.dateFormat = "yyyy-MM-dd HH:mm:ss";
  return df.string(new Date());
}

function escapeHTML(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function clip(s, max) {
  s = String(s);
  return s.length > max ? s.slice(0, max) + "\n…（已截断）" : s;
}

/** 简单稳定哈希（用于缓存 key，无需加密强度） */
function simpleHash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h << 5) - h + str.charCodeAt(i);
    h |= 0;
  }
  return String(h);
}

/**
 * 判断本次运行是否需要朗读结果：
 *   1. CONFIG.TTS_AFTER_PROCESS = true → 每次都朗读；
 *   2. 或者本次运行携带的 Shortcut 参数 / URL Scheme 参数里包含 "speak"
 *      （例如把操作按钮长按绑定的快捷指令改成传入文本参数 "speak"，
 *       或用 URL Scheme 触发 scriptable:///run?scriptName=xxx&speak=1）。
 * 这样默认保持静默，只有用户主动要求时才出声，避免在公共场合意外播报。
 */
function shouldSpeakThisRun() {
  if (CONFIG.TTS_AFTER_PROCESS) return true;
  try {
    if (typeof args !== "undefined") {
      if (args.shortcutParameter && String(args.shortcutParameter).toLowerCase().includes("speak")) {
        return true;
      }
      if (args.queryParameters) {
        const v = String(args.queryParameters.speak || "").toLowerCase();
        if (v === "1" || v === "true" || v === "yes") return true;
      }
    }
  } catch (e) {
    // 忽略：不是所有触发方式都会提供 args
  }
  return false;
}

/** 按需朗读结果；朗读失败不影响主流程 */
async function maybeSpeak(text) {
  if (!text || !text.trim()) return;
  if (!shouldSpeakThisRun()) return;
  try {
    Speech.speak(clip(text, 3000));
  } catch (e) {
    console.warn("语音播报失败: " + e.message);
  }
}

/** 将 Scriptable Image 转成 base64 字符串（借道临时文件，Scriptable 无直接 Image→Data API） */
function imageToBase64(image) {
  const tempPath = fm.joinPath(fm.temporaryDirectory(), `ai_router_img_${Date.now()}.png`);
  try {
    fm.writeImage(tempPath, image);
    const data = fm.read(tempPath);
    return data.toBase64String();
  } finally {
    try {
      if (fm.fileExists(tempPath)) fm.remove(tempPath);
    } catch (e) {
      // 忽略清理失败
    }
  }
}

// ╔═══════════════════════ ③ 密 钥 管 理（Keychain）═══════════════╗

/** 从 Keychain 读取密钥；不存在则弹窗要求输入并保存 */
async function getSecret(kcKey, title, message, placeholder) {
  if (Keychain.contains(kcKey)) {
    const v = Keychain.get(kcKey);
    if (v && v.trim()) return v.trim();
  }
  const value = await promptText(title, message, placeholder);
  if (value && value.trim()) {
    Keychain.set(kcKey, value.trim());
    return value.trim();
  }
  return null; // 用户取消/留空
}

async function loadSecrets() {
  const apiKey = await getSecret(
    KC_KEYS.API_KEY,
    "🔑 首次配置：硅基流动 API Key",
    "请填入硅基流动（SiliconFlow）的 API Key，文本对话与截图识图都用它。该值将加密保存在本机 Keychain，仅需输入一次。",
    "sk-xxxxxxxxxxxx"
  );
  if (!apiKey) throw new Error("未配置硅基流动 API Key，脚本无法继续。");

  // Telegram 是可选项：用户可以在弹窗里直接取消，跳过同步功能
  let tgToken = Keychain.contains(KC_KEYS.TG_BOT_TOKEN) ? Keychain.get(KC_KEYS.TG_BOT_TOKEN) : null;
  let tgChat = Keychain.contains(KC_KEYS.TG_CHAT_ID) ? Keychain.get(KC_KEYS.TG_CHAT_ID) : null;

  if (!tgToken || !tgChat) {
    const wantTG = await promptText(
      "📡 可选：Telegram 同步",
      "如需把结果自动同步到 Telegram，请输入「BotToken,ChatID」（英文逗号分隔）。留空则跳过同步功能。",
      "123456:ABC-DEF,987654321"
    );
    if (wantTG && wantTG.includes(",")) {
      const [t, c] = wantTG.split(",").map(s => s.trim());
      if (t && c) {
        Keychain.set(KC_KEYS.TG_BOT_TOKEN, t);
        Keychain.set(KC_KEYS.TG_CHAT_ID, c);
        tgToken = t; tgChat = c;
      }
    }
  }

  return { apiKey, tgToken, tgChat };
}

// ╔═══════════════════════ ④ 本 地 历 史 & 缓 存 ═══════════════════╗

const fm = FileManager.local();
const DIR = fm.joinPath(fm.documentsDirectory(), "ai_router");
if (!fm.fileExists(DIR)) fm.createDirectory(DIR);
const HISTORY_FILE = fm.joinPath(DIR, "history.json");
const CACHE_FILE = fm.joinPath(DIR, "cache.json");

function readJSON(path, fallback) {
  try {
    if (!fm.fileExists(path)) return fallback;
    return JSON.parse(fm.readString(path));
  } catch (e) {
    console.warn(`读取 ${path} 失败，使用默认值: ${e.message}`);
    return fallback;
  }
}

function writeJSON(path, data) {
  try {
    fm.writeString(path, JSON.stringify(data));
  } catch (e) {
    console.warn(`写入 ${path} 失败: ${e.message}`);
  }
}

/** 追加一条历史记录，超出上限自动裁剪最旧的 */
function appendHistory(branchName, original, result) {
  const list = readJSON(HISTORY_FILE, []);
  list.push({
    time: timestamp(),
    branch: branchName,
    original: clip(original, 300),
    result: clip(result, 1200),
  });
  while (list.length > CONFIG.HISTORY_MAX) list.shift();
  writeJSON(HISTORY_FILE, list);
}

/** 查看最近历史（不消耗 AI 调用） */
async function viewHistory() {
  const list = readJSON(HISTORY_FILE, []);
  if (list.length === 0) {
    await alertBox("🕘 历史记录", "暂无历史记录。");
    return;
  }
  const recent = list.slice(-20).reverse();
  const text = recent
    .map((h, i) => `#${i + 1} [${h.time}] ${h.branch}\n原文：${h.original}\n结果：${h.result}`)
    .join("\n\n" + "-".repeat(20) + "\n\n");
  await QuickLook.present(text, false);
}

function cacheKey(branchName, text) {
  return `${branchName}::${simpleHash(text)}`;
}

/** 读取缓存；过期或不存在返回 null */
function getCache(branchName, text) {
  const cache = readJSON(CACHE_FILE, {});
  const key = cacheKey(branchName, text);
  const entry = cache[key];
  if (!entry) return null;
  const ageMs = Date.now() - entry.ts;
  if (ageMs > CONFIG.CACHE_MINUTES * 60 * 1000) return null;
  return entry.result;
}

function setCache(branchName, text, result) {
  const cache = readJSON(CACHE_FILE, {});
  cache[cacheKey(branchName, text)] = { ts: Date.now(), result };
  // 简单清理：超过 300 条时清空重建，避免文件无限增长
  if (Object.keys(cache).length > 300) {
    writeJSON(CACHE_FILE, { [cacheKey(branchName, text)]: cache[cacheKey(branchName, text)] });
  } else {
    writeJSON(CACHE_FILE, cache);
  }
}

// ╔═══════════════════════ ④.5 用量 / 记忆 / 进化 ═════════════════╗

const USAGE_FILE = fm.joinPath(DIR, "usage.json");
const RAG_FILE = fm.joinPath(DIR, "rag.json");
const PROFILE_FILE = fm.joinPath(DIR, "self_profile.json");

/** 当前月份 key，如 "2026-07" */
function monthKey() {
  const df = new DateFormatter();
  df.dateFormat = "yyyy-MM";
  return df.string(new Date());
}

/** 累计本月 Token 用量（各处 API 调用统一上报 total_tokens） */
function recordUsage(totalTokens) {
  const n = Number(totalTokens);
  if (!n || n <= 0) return;
  const store = readJSON(USAGE_FILE, {});
  const mk = monthKey();
  if (!store[mk]) store[mk] = { tokens: 0, alerted: false };
  store[mk].tokens += n;
  writeJSON(USAGE_FILE, store);
}

/** 粗略估算 token 数（流式无 usage 字段时的兜底，仅用于用量计数，非精确值） */
function estimateTokens(text) {
  if (!text) return 0;
  return Math.ceil(String(text).length / 2);
}

/** 本月用量超过阈值时提醒一次（每月仅提醒一次） */
async function maybeAlertUsage() {
  if (!CONFIG.TOKEN_ALERT_THRESHOLD) return;
  const store = readJSON(USAGE_FILE, {});
  const mk = monthKey();
  const rec = store[mk];
  if (rec && !rec.alerted && rec.tokens >= CONFIG.TOKEN_ALERT_THRESHOLD) {
    rec.alerted = true;
    writeJSON(USAGE_FILE, store);
    await notify("📊 Token 用量提醒", `本月已用约 ${rec.tokens} tokens，已达到提醒阈值 ${CONFIG.TOKEN_ALERT_THRESHOLD}。`);
  }
}

/** 查看用量统计（不消耗 AI 调用） */
async function viewUsage() {
  const store = readJSON(USAGE_FILE, {});
  const months = Object.keys(store).sort().reverse();
  if (months.length === 0) {
    await alertBox("📊 用量统计", "暂无用量记录。");
    return;
  }
  const mk = monthKey();
  const cur = store[mk] ? store[mk].tokens : 0;
  const thresholdNote = CONFIG.TOKEN_ALERT_THRESHOLD ? `\n提醒阈值：${CONFIG.TOKEN_ALERT_THRESHOLD} tokens/月` : "";
  const lines = months.map(m => `${m}：约 ${store[m].tokens} tokens`);
  await QuickLook.present(
    `📊 Token 用量统计\n\n本月（${mk}）：约 ${cur} tokens${thresholdNote}\n\n———— 各月明细 ————\n${lines.join("\n")}`,
    false
  );
}

/** 调用硅基流动 Embedding 接口，返回向量数组 */
async function getEmbedding(apiKey, text) {
  const req = new Request(CONFIG.EMBEDDING_API_URL);
  req.method = "POST";
  req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
  req.headers = { "Content-Type": "application/json", "Authorization": `Bearer ${apiKey}` };
  req.body = JSON.stringify({ model: CONFIG.EMBEDDING_MODEL, input: clip(text, 2000) });
  const json = await req.loadJSON();
  const status = req.response ? req.response.statusCode : 0;
  if (status >= 400 || !json || !json.data || !json.data[0]) {
    const apiMsg = json && json.error ? json.error.message : `状态码 ${status}`;
    throw new Error(`Embedding 失败: ${apiMsg}`);
  }
  if (json.usage) recordUsage(json.usage.total_tokens);
  return json.data[0].embedding;
}

/** 余弦相似度 */
function cosineSim(a, b) {
  let dot = 0, na = 0, nb = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

/** 检索与当前输入最相似的历史，拼成上下文串注入 system prompt；任何失败都返回 "" */
async function retrieveRAGContext(apiKey, text) {
  if (!CONFIG.RAG_ENABLED) return "";
  const store = readJSON(RAG_FILE, []);
  if (store.length === 0) return "";
  let queryVec;
  try {
    queryVec = await getEmbedding(apiKey, text);
  } catch (e) {
    console.warn("RAG 检索跳过: " + e.message);
    return "";
  }
  const scored = store
    .filter(e => Array.isArray(e.vector) && e.vector.length)
    .map(e => ({ e, score: cosineSim(queryVec, e.vector) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, CONFIG.RAG_TOP_K)
    .filter(x => x.score > 0.5);
  if (scored.length === 0) return "";
  const ctx = scored
    .map((x, i) => `【历史${i + 1}｜${x.e.branch}】原输入：${x.e.text}\n当时结论：${x.e.snippet}`)
    .join("\n\n");
  return `以下是你过去处理过的相似内容，请参考以保持与用户偏好、风格一致（若与本次无关可忽略）：\n${ctx}`;
}

/** 把本次交互向量化后存入本地向量库（失败静默，不影响主流程） */
async function rememberRAG(apiKey, text, result, branch) {
  if (!CONFIG.RAG_ENABLED) return;
  let vec;
  try {
    vec = await getEmbedding(apiKey, text);
  } catch (e) {
    console.warn("RAG 记忆跳过: " + e.message);
    return;
  }
  const store = readJSON(RAG_FILE, []);
  store.push({ text: clip(text, 200), snippet: clip(result, 300), vector: vec, ts: Date.now(), branch });
  while (store.length > CONFIG.RAG_MAX_ENTRIES) store.shift();
  writeJSON(RAG_FILE, store);
}

/** 读取当前"用户画像"（自我进化产物），用于注入 system prompt */
function getSelfProfile() {
  if (!CONFIG.SELF_EVOLVE_ENABLED) return "";
  const p = readJSON(PROFILE_FILE, null);
  return p && p.profile ? p.profile : "";
}

/** 在 system prompt 前拼接额外上下文（画像 / RAG 等） */
function prependSystem(base, extra) {
  return (extra && extra.trim()) ? (extra.trim() + "\n\n" + base) : base;
}

/** 读历史 → 让 AI 总结一份用户画像 → 存盘 */
async function evolveProfile(secrets) {
  const history = readJSON(HISTORY_FILE, []);
  const recent = history.slice(-40);
  const digest = recent
    .map(h => `[${h.branch}] 输入:${clip(h.original, 120)} 结果:${clip(h.result, 200)}`)
    .join("\n");
  if (!digest.trim()) throw new Error("历史记录为空，暂时无法生成用户画像，多用几次再来。");
  const sys =
    "你是一个善于观察的用户画像分析师。请根据用户最近的使用记录，总结一份简短的『用户偏好画像』，" +
    "用于指导后续 AI 回答（例如：常见业务领域、偏好的语气与格式、语言风格、需要规避的点）。" +
    "直接输出画像正文，控制在 200 字以内，不要输出解释或标题。";
  const profile = await callDeepSeek(secrets.apiKey, sys, digest, CONFIG.MODEL_MAP.default);
  writeJSON(PROFILE_FILE, { profile: profile.trim(), updatedAt: Date.now() });
  console.log("已更新用户画像");
}

/** 到周期且历史足够时，自动进行一次自我进化（静默） */
async function maybeSelfEvolve(secrets) {
  if (!CONFIG.SELF_EVOLVE_ENABLED) return;
  const p = readJSON(PROFILE_FILE, null);
  const dueMs = CONFIG.SELF_EVOLVE_DAYS * 24 * 60 * 60 * 1000;
  if (p && p.updatedAt && (Date.now() - p.updatedAt) < dueMs) return;
  const history = readJSON(HISTORY_FILE, []);
  if (history.length < 5) return;
  try {
    await evolveProfile(secrets);
  } catch (e) {
    console.warn("自我进化失败: " + e.message);
  }
}

/** 手动触发自我进化 */
async function evolveNow(secrets) {
  await notify("🧬 自我进化", "正在阅读历史，生成 / 更新用户画像…");
  try {
    await evolveProfile(secrets);
    await alertBox("🧬 自我进化完成", "已根据历史更新用户画像，后续回答会更贴合你的偏好：\n\n" + (getSelfProfile() || "（暂无内容）"));
  } catch (e) {
    await fail("自我进化", e);
  }
}

// ╔═══════════════════════ ⑤ 智 能 路 由 ══════════════════════════╗

/** 是否像代码 / 报错日志（大括号、分号、关键字、堆栈痕迹等信号） */
function looksLikeCode(text) {
  if (text.length < 20) return false;
  const braceOpen = (text.match(/{/g) || []).length;
  const braceClose = (text.match(/}/g) || []).length;
  const codeSignals = /[{};]|=>|function\s|const\s|let\s|import\s|SELECT\s+.+FROM|def\s|class\s|<\?php|#include|Traceback|Exception|Error:|at\s+\S+\(.+:\d+:\d+\)/i;
  const jsonLike = (() => {
    try { JSON.parse(text); return true; } catch (e) { return false; }
  })();
  return jsonLike || (codeSignals.test(text) && braceOpen === braceClose && braceOpen > 0)
      || /Traceback|Exception in thread|Uncaught|Fatal error/i.test(text);
}

/**
 * 判定路由分支
 * 优先级：URL > 代码/日志 > 非中文语言 > 中文业务菜单
 */
function detectRoute(text) {
  const urlMatch = text.match(/https?:\/\/[^\s"'<>「」【】()（）\]]+/i);
  if (urlMatch) return { type: "url", url: urlMatch[0] };

  if (looksLikeCode(text)) return { type: "code" };

  const cnCount = (text.match(/[一-鿿]/g) || []).length;

  // 是否含有任意"字母类"字符（覆盖英/泰/越/韩/日/俄等，不再局限于英文 A-Za-z）
  let hasLetters = false;
  try {
    hasLetters = /\p{L}/u.test(text);
  } catch (e) {
    // 极少数环境不支持 \p{L}，退化为常见字母判断
    hasLetters = /[A-Za-z\u0E00-\u0E7F\u00C0-\u1EF9\uAC00-\uD7A3\u3040-\u30FF]/.test(text);
  }

  if (cnCount === 0 && hasLetters) return { type: "lang" };
  return { type: "zh" };
}

/** 按路由类型 + 文本长度推荐最合适的模型（对应表见 CONFIG.MODEL_MAP） */
function recommendModel(routeType, textLength) {
  const M = CONFIG.MODEL_MAP;
  if (routeType === "url") return (textLength || 0) < 2000 ? M.summary : M.default;
  if (routeType === "code") return M.code;
  if (routeType === "lang") return M.translate;
  if (routeType === "zh") return (textLength || 0) > 3000 ? M.reasoning : M.default;
  return M.default;
}

// ╔═══════════════════════ ⑥ 网 络 层 ═════════════════════════════╗

async function fetchWebText(url) {
  const req = new Request(url);
  req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
  req.headers = {
    "User-Agent":
      "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
  };
  const html = await req.loadString();
  const status = req.response ? req.response.statusCode : 0;
  if (status >= 400) throw new Error(`网页返回状态码 ${status}`);

  const text = html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&#\d+;/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();

  if (text.length < 50) throw new Error("网页正文提取内容过少（可能是纯 JS 渲染页面）");
  return text.slice(0, CONFIG.MAX_WEB_CHARS);
}

/** 调用文本模型（硅基流动 Chat API）：主模型重试用尽后，自动切到备用模型再试一轮 */
async function callDeepSeek(apiKey, systemPrompt, userContent, model) {
  async function tryModel(model, retries) {
    let lastErr = null;
    for (let attempt = 1; attempt <= retries + 1; attempt++) {
      try {
        const req = new Request(CONFIG.API_URL);
        req.method = "POST";
        req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
        req.headers = {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${apiKey}`,
        };
        req.body = JSON.stringify({
          model,
          temperature: CONFIG.TEMPERATURE,
          max_tokens: CONFIG.MAX_TOKENS,
          messages: [
            { role: "system", content: systemPrompt },
            { role: "user", content: userContent },
          ],
        });

        const json = await req.loadJSON();
        const status = req.response ? req.response.statusCode : 0;

        if (status === 401) throw new Error("API Key 无效（401），请检查已保存的硅基流动 Key");
        if (status === 402) throw new Error("硅基流动账户余额不足（402）");
        if (status === 429) throw new Error("请求过于频繁（429），稍后再试");
        if (status >= 400) {
          const apiMsg = json && json.error ? json.error.message : "未知错误";
          throw new Error(`API 错误 ${status}: ${apiMsg}`);
        }

        if (json.usage) recordUsage(json.usage.total_tokens);

        const content =
          json && json.choices && json.choices[0] &&
          json.choices[0].message && json.choices[0].message.content;
        if (!content || !content.trim()) throw new Error("AI 返回了空内容");
        return content.trim();
      } catch (e) {
        lastErr = e;
        if (/401|402/.test(String(e.message))) throw e;
        if (attempt <= retries) {
          console.warn(`[${model}] 第 ${attempt} 次请求失败，正在重试: ${e.message}`);
        }
      }
    }
    throw lastErr;
  }

  const primaryModel = model || CONFIG.MODEL;
  try {
    return await tryModel(primaryModel, CONFIG.MAX_RETRY);
  } catch (primaryErr) {
    if (!CONFIG.FALLBACK_MODEL || CONFIG.FALLBACK_MODEL === primaryModel) {
      throw new Error(`AI 请求失败: ${primaryErr.message}`);
    }
    console.warn(`主模型失败，切换备用模型 ${CONFIG.FALLBACK_MODEL}: ${primaryErr.message}`);
    try {
      const result = await tryModel(CONFIG.FALLBACK_MODEL, 1);
      return result;
    } catch (fallbackErr) {
      throw new Error(`主/备模型均失败。主：${primaryErr.message}；备：${fallbackErr.message}`);
    }
  }
}

/** 调用识图模型（硅基流动，OpenAI 兼容多模态格式），传入 base64 图片 + system prompt */
async function callVisionAPI(apiKey, systemPrompt, imageBase64) {
  let lastErr = null;
  for (let attempt = 1; attempt <= CONFIG.MAX_RETRY + 1; attempt++) {
    try {
      const req = new Request(CONFIG.API_URL);
      req.method = "POST";
      req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
      req.headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`,
      };
      req.body = JSON.stringify({
        model: CONFIG.VISION_MODEL,
        temperature: CONFIG.TEMPERATURE,
        max_tokens: CONFIG.MAX_TOKENS,
        messages: [
          { role: "system", content: systemPrompt },
          {
            role: "user",
            content: [
              { type: "text", text: "请阅读这张聊天截图，理解对话内容后给出推荐回复。" },
              { type: "image_url", image_url: { url: `data:image/png;base64,${imageBase64}` } },
            ],
          },
        ],
      });

      const json = await req.loadJSON();
      const status = req.response ? req.response.statusCode : 0;

      if (status === 401) throw new Error("识图模型 API Key 无效（401），请检查已保存的密钥");
      if (status >= 400) {
        const apiMsg = json && json.error ? json.error.message : "未知错误";
        throw new Error(`识图模型 API 错误 ${status}: ${apiMsg}`);
      }

      if (json.usage) recordUsage(json.usage.total_tokens);

      const content =
        json && json.choices && json.choices[0] &&
        json.choices[0].message && json.choices[0].message.content;
      if (!content || !content.trim()) throw new Error("识图模型返回了空内容");
      return content.trim();
    } catch (e) {
      lastErr = e;
      if (/401/.test(String(e.message))) throw e;
      if (attempt <= CONFIG.MAX_RETRY) {
        console.warn(`[识图模型] 第 ${attempt} 次请求失败，正在重试: ${e.message}`);
      }
    }
  }
  throw new Error(`识图模型请求失败: ${lastErr.message}`);
}

/**
 * 流式调用文本模型（硅基流动），并在一个轻量 WebView 里逐字实时展示结果。
 *
 * 实现要点：Scriptable 自带的 Request 对象没有"分块读取"的 API（load* 系列
 * 都是等整个响应体到达后才 resolve），所以真正的流式渲染借道 WebView 的
 * JS 引擎——它是一个真正的浏览器上下文，支持 fetch() + ReadableStream 读取
 * Server-Sent Events。页面里的脚本先加载好，再由 Scriptable 通过
 * evaluateJavaScript(_, true) 调用 run()，run() 完成后调用页面里注入的
 * completion(value) 把最终文本带回 Scriptable。
 *
 * 任何环节出错（网络、跨域限制、模型报错等）都会被捕获并通过带
 * "__STREAM_ERROR__" 前缀的字符串返回，调用方据此自动降级为非流式请求，
 * 不会让用户卡在一个空白或报错的弹窗里。
 */
async function callDeepSeekStream(apiKey, model, systemPrompt, userContent, title) {
  const html = `<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#0b0b0c; color:#f2f2f2;
         margin:0; padding:18px 16px 90px; }
  h2 { font-size:15px; color:#7fa8ff; margin:0 0 14px; font-weight:600; }
  #out { white-space:pre-wrap; word-break:break-word; font-size:16px; line-height:1.6; min-height:30vh; }
  #out.empty::after { content:"AI 正在思考…"; color:#666; }
  .bar { position:fixed; left:0; right:0; bottom:0; display:flex; gap:10px; padding:12px 16px;
         background:rgba(11,11,12,0.92); backdrop-filter:blur(10px); }
  button { flex:1; padding:14px; border:none; border-radius:12px; font-size:15px; font-weight:600; }
  .copy { background:#2f6fff; color:#fff; }
  .done { background:#2c2c2e; color:#fff; }
  button:active { opacity:0.7; }
</style></head>
<body>
  <h2>${escapeHTML(title)}</h2>
  <div id="out" class="empty"></div>
  <div class="bar">
    <button class="copy" onclick="copyOut()">📋 复制</button>
    <button class="done" onclick="finish()">✅ 完成</button>
  </div>
<script>
  let full = '';
  let finished = false;
  let usage = null;
  function render() {
    const el = document.getElementById('out');
    el.textContent = full;
    el.classList.toggle('empty', full.length === 0);
    window.scrollTo(0, document.body.scrollHeight);
  }
  function copyOut() {
    try { navigator.clipboard.writeText(full); } catch (e) {}
  }
  function finish() {
    if (finished) return;
    finished = true;
    completion(JSON.stringify({ text: full || '（AI 未返回内容）', usage: usage }));
  }
  async function run() {
    try {
      const resp = await fetch(${JSON.stringify(CONFIG.API_URL)}, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + ${JSON.stringify(apiKey)}
        },
        body: JSON.stringify({
          model: ${JSON.stringify(model)},
          temperature: ${CONFIG.TEMPERATURE},
          max_tokens: ${CONFIG.MAX_TOKENS},
          stream: true,
          stream_options: { include_usage: true },
          messages: [
            { role: 'system', content: ${JSON.stringify(systemPrompt)} },
            { role: 'user', content: ${JSON.stringify(userContent)} }
          ]
        })
      });
      if (!resp.ok || !resp.body) {
        const errText = await resp.text().catch(function () { return ''; });
        throw new Error('HTTP ' + resp.status + ' ' + errText);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buf += decoder.decode(chunk.value, { stream: true });
        const lines = buf.split('\\n');
        buf = lines.pop();
        for (const line of lines) {
          const t = line.trim();
          if (!t.startsWith('data:')) continue;
          const payload = t.slice(5).trim();
          if (!payload || payload === '[DONE]') continue;
          try {
            const json = JSON.parse(payload);
            if (json.usage) usage = json.usage;
            const delta = json.choices && json.choices[0] && json.choices[0].delta && json.choices[0].delta.content;
            if (delta) { full += delta; render(); }
          } catch (e) { /* 忽略单个分片解析失败 */ }
        }
      }
      if (!finished) finish();
    } catch (e) {
      if (!finished) { finished = true; completion('__STREAM_ERROR__' + (e && e.message ? e.message : String(e))); }
    }
  }
</script>
</body></html>`;

  const wv = new WebView();
  await wv.loadHTML(html);
  wv.present(false); // 非全屏展示；不等待用户关闭，evaluateJavaScript 会在收到 completion() 后自行 resolve
  const raw = await wv.evaluateJavaScript("run()", true);
  return raw;
}

/**
 * 统一封装："优先尝试流式展示，失败静默降级为普通请求"。
 * 返回 { text, streamed }，streamed 表示这次是否成功走了流式 WebView 展示
 * （调用方可据此决定是否还需要额外弹一次 presentResult，避免重复展示）。
 */
async function generateWithDisplay(secrets, title, systemPrompt, userContent, options = {}) {
  const model = options.model || CONFIG.MODEL;
  let sys = systemPrompt;
  if (options.injectProfile !== false) sys = prependSystem(sys, getSelfProfile());

  if (CONFIG.STREAM_ENABLED) {
    try {
      const streamedRaw = await callDeepSeekStream(secrets.apiKey, model, sys, userContent, title);
      if (streamedRaw && !streamedRaw.startsWith("__STREAM_ERROR__")) {
        let text = streamedRaw;
        let usageRecorded = false;
        try {
          const parsed = JSON.parse(streamedRaw);
          text = parsed.text;
          if (parsed.usage && parsed.usage.total_tokens) { recordUsage(parsed.usage.total_tokens); usageRecorded = true; }
        } catch (e) {
          // 兼容极端情况：返回的不是 JSON 就当作纯文本
        }
        // 兜底：若流式会话未返回 usage（provider 忽略 include_usage，或用户提前点"完成"），
        // 用字符数粗略估算，保证月度用量计数不漏记（仅为估算值）。
        if (!usageRecorded) recordUsage(estimateTokens(sys) + estimateTokens(userContent) + estimateTokens(text));
        return { text, streamed: true };
      }
      console.warn("流式展示失败，降级为普通请求: " + streamedRaw);
    } catch (e) {
      console.warn("流式展示异常，降级为普通请求: " + e.message);
    }
  }
  const text = await callDeepSeek(secrets.apiKey, sys, userContent, model);
  return { text, streamed: false };
}

/** 同步到 Telegram */
async function syncToTelegram(secrets, branchName, original, aiResult) {
  if (!secrets.tgToken || !secrets.tgChat) {
    console.log("Telegram 未配置，跳过同步");
    return;
  }
  try {
    const text =
      `🔀 <b>AI 智能路由引擎 · ${escapeHTML(branchName)}</b>\n\n` +
      `📥 <b>原始文本</b>\n<pre>${escapeHTML(clip(original, 600))}</pre>\n\n` +
      `🤖 <b>AI 处理结果</b>\n<pre>${escapeHTML(clip(aiResult, 2600))}</pre>\n\n` +
      `⏱️ <code>${timestamp()}</code>`;

    const req = new Request(`https://api.telegram.org/bot${secrets.tgToken}/sendMessage`);
    req.method = "POST";
    req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
    req.headers = { "Content-Type": "application/json" };
    req.body = JSON.stringify({
      chat_id: secrets.tgChat,
      text: text,
      parse_mode: "HTML",
      disable_web_page_preview: true,
    });

    const json = await req.loadJSON();
    if (!json.ok) throw new Error(json.description || "Telegram API 返回 ok=false");
    console.log("Telegram 同步成功");
  } catch (e) {
    await fail("Telegram 同步", e);
  }
}

// ╔═══════════════════════ ⑦ 结 果 呈 现 ══════════════════════════╗

async function presentResult(title, result) {
  const a = new Alert();
  a.title = title;
  a.message = result.length > 700 ? result.slice(0, 700) + "\n…" : result;
  a.addAction("📄 查看全文");
  a.addAction("📋 复制结果");
  a.addCancelAction("完成");
  const idx = await a.presentAlert();
  if (idx === 0) {
    await QuickLook.present(result, false);
  } else if (idx === 1) {
    Pasteboard.copy(result);
    await notify("📋 已复制", "AI 处理结果已写入剪贴板");
  }
}

// ╔═══════════════════════ ⑦.5 工 具 调 用（Function Calling）══════╗

/** AI 可调用的本地工具（OpenAI 兼容 function 描述） */
const TOOLS = [
  {
    type: "function",
    function: {
      name: "create_calendar_event",
      description: "在系统日历中创建一个事件/提醒。当用户内容包含明确的时间安排、会议、待办、截止时间时使用。",
      parameters: {
        type: "object",
        properties: {
          title: { type: "string", description: "事件标题" },
          startTime: { type: "string", description: "开始时间，尽量输出可被 JS new Date() 解析的格式，如 2026-07-15T15:00:00" },
          endTime: { type: "string", description: "结束时间，可选；缺省则默认为开始后 1 小时" },
          notes: { type: "string", description: "备注，可选" },
        },
        required: ["title", "startTime"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "send_telegram_message",
      description: "通过用户已配置的 Telegram Bot 发送一条消息。当用户要求转发、通知、发送到 Telegram 时使用。",
      parameters: {
        type: "object",
        properties: {
          text: { type: "string", description: "要发送的消息正文" },
        },
        required: ["text"],
      },
    },
  },
];

/** 执行前的授权确认弹窗（返回 true 表示用户允许） */
async function confirmAction(title, message) {
  const a = new Alert();
  a.title = title;
  a.message = message;
  a.addAction("✅ 允许");
  a.addCancelAction("❌ 拒绝");
  const idx = await a.presentAlert();
  return idx === 0;
}

async function execCreateCalendarEvent(args) {
  if (!args || !args.title) return "失败：缺少事件标题，未创建。";
  const start = new Date(args.startTime);
  if (isNaN(start.getTime())) return `失败：无法解析开始时间「${args.startTime}」。`;
  let end = args.endTime ? new Date(args.endTime) : new Date(start.getTime() + 60 * 60 * 1000);
  if (isNaN(end.getTime())) end = new Date(start.getTime() + 60 * 60 * 1000);
  const when = args.startTime + (args.endTime ? ` ~ ${args.endTime}` : "（默认 1 小时）");
  const ok = await confirmAction(
    "📅 AI 想创建日历事件",
    `标题：${args.title}\n时间：${when}${args.notes ? `\n备注：${args.notes}` : ""}\n\n是否允许？`
  );
  if (!ok) return "用户拒绝了创建日历事件。";
  try {
    const ev = new CalendarEvent();
    ev.title = args.title;
    ev.startDate = start;
    ev.endDate = end;
    if (args.notes) ev.notes = args.notes;
    await ev.save();
    return `已成功在日历创建事件「${args.title}」（${when}）。`;
  } catch (e) {
    return "创建日历事件失败：" + e.message;
  }
}

async function execSendTelegram(secrets, args) {
  if (!secrets.tgToken || !secrets.tgChat) return "失败：尚未配置 Telegram Bot，无法发送。";
  if (!args || !args.text || !String(args.text).trim()) return "失败：消息内容为空，未发送。";
  const ok = await confirmAction(
    "📨 AI 想发送 Telegram 消息",
    `内容：${clip(args.text, 300)}\n\n是否允许发送到你配置的 Chat？`
  );
  if (!ok) return "用户拒绝了发送 Telegram 消息。";
  try {
    const req = new Request(`https://api.telegram.org/bot${secrets.tgToken}/sendMessage`);
    req.method = "POST";
    req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
    req.headers = { "Content-Type": "application/json" };
    req.body = JSON.stringify({ chat_id: secrets.tgChat, text: args.text });
    const json = await req.loadJSON();
    if (!json.ok) return "Telegram 发送失败：" + (json.description || "未知错误");
    return "已通过 Telegram 发送成功。";
  } catch (e) {
    return "Telegram 发送失败：" + e.message;
  }
}

/**
 * 带工具调用的多轮对话：模型返回 tool_calls → 本地逐个执行（执行前弹窗确认）
 * → 把结果回喂模型 → 直到模型给出不含工具调用的最终回复。
 */
async function callWithTools(secrets, systemPrompt, userContent) {
  const messages = [
    { role: "system", content: systemPrompt },
    { role: "user", content: userContent },
  ];
  const MAX_ROUNDS = 4;

  for (let round = 0; round < MAX_ROUNDS; round++) {
    const req = new Request(CONFIG.API_URL);
    req.method = "POST";
    req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
    req.headers = { "Content-Type": "application/json", "Authorization": `Bearer ${secrets.apiKey}` };
    req.body = JSON.stringify({
      model: CONFIG.TOOL_MODEL,
      temperature: CONFIG.TEMPERATURE,
      max_tokens: CONFIG.MAX_TOKENS,
      tools: TOOLS,
      messages,
    });

    const json = await req.loadJSON();
    const status = req.response ? req.response.statusCode : 0;
    if (status >= 400) {
      const apiMsg = json && json.error ? json.error.message : "未知错误";
      throw new Error(`工具调用 API 错误 ${status}: ${apiMsg}`);
    }
    if (json.usage) recordUsage(json.usage.total_tokens);

    const msg = json.choices && json.choices[0] && json.choices[0].message;
    if (!msg) throw new Error("工具调用返回为空");

    const toolCalls = msg.tool_calls;
    if (!toolCalls || toolCalls.length === 0) {
      return (msg.content || "").trim() || "（AI 未返回内容）";
    }

    messages.push({ role: "assistant", content: msg.content || "", tool_calls: toolCalls });

    for (const tc of toolCalls) {
      const fnName = tc.function && tc.function.name;
      let argsObj = {};
      let parseOk = true;
      try { argsObj = JSON.parse((tc.function && tc.function.arguments) || "{}"); } catch (e) { parseOk = false; }
      let toolResult;
      if (!parseOk) {
        toolResult = `工具「${fnName || "?"}」的参数不是合法 JSON，未执行；请以合法 JSON 重新提供参数。`;
      } else if (fnName === "create_calendar_event") {
        toolResult = await execCreateCalendarEvent(argsObj);
      } else if (fnName === "send_telegram_message") {
        toolResult = await execSendTelegram(secrets, argsObj);
      } else {
        toolResult = "未知工具：" + fnName;
      }
      messages.push({ role: "tool", tool_call_id: tc.id || "", content: toolResult });
    }
  }
  return "（工具调用超过最大轮数，已停止。请把需求拆分得更具体一些。）";
}

// ╔═══════════════════════ ⑧ 分 支 逻 辑 ══════════════════════════╗

/** 分支 F：AI 执行操作（Function Calling，逐次授权） */
async function branchAgent(secrets, rawText) {
  await notify("🤖 AI 助手", "正在理解你的意图，可能会请求执行操作…");
  const sys =
    "你是一个能操作用户 iPhone 的智能助手。你可用的工具：在日历创建事件、通过 Telegram 发送消息。" +
    "请根据用户内容判断是否需要调用工具：包含时间安排/待办就创建日历事件；要求转发/通知就发 Telegram。" +
    "可以连续调用多个工具。全部完成后，用中文简要说明你做了哪些操作；若无需任何操作，就直接给出有帮助的回答。" +
    `当前时间是 ${timestamp()}，请据此换算"明天/后天/下周"等相对时间。`;

  let result;
  try {
    result = await callWithTools(secrets, sys, rawText);
  } catch (e) {
    await fail("AI 执行操作", e);
    return null;
  }

  Pasteboard.copy(result);
  await notify("✅ AI 执行完成（已复制说明）", result);
  appendHistory("分支F · AI执行", rawText, result);
  await syncToTelegram(secrets, "分支F · AI执行", rawText, result);
  await maybeSpeak(result);
  await presentResult("🤖 AI 执行结果", result);
  return result;
}

async function branchURL(secrets, rawText, url) {
  await notify("🔗 检测到链接", "正在抓取网页并进行 AI 深度摘要…");

  const cached = getCache("url", url);
  if (cached) {
    await notify("⚡ 命中缓存", "使用最近处理结果，未重新调用 AI");
    await presentResult("🔗 网页深度摘要（缓存）", cached);
    return cached;
  }

  let pageText, sourceNote;
  try {
    pageText = await fetchWebText(url);
    sourceNote = "以下是该网页提取出的正文内容";
  } catch (e) {
    console.warn("网页抓取失败，降级处理: " + e.message);
    pageText = `（网页正文抓取失败：${e.message}。请基于该 URL 的域名、路径等已知信息尽力推断主题并说明局限。）URL: ${url}`;
    sourceNote = "网页抓取失败，仅有 URL 信息";
  }

  const { text: result, streamed } = await generateWithDisplay(
    secrets,
    "🔗 网页深度摘要",
    "请对以下链接的目标网页内容进行核心要点提炼，用精简的中文脑图或清单形式输出。",
    `目标链接：${url}\n${sourceNote}：\n\n${pageText}`,
    { model: recommendModel("url", pageText.length) }
  );

  setCache("url", url, result);
  appendHistory("分支A · 链接摘要", url, result);
  await syncToTelegram(secrets, "分支A · 链接摘要", url, result);
  await maybeSpeak(result);
  if (!streamed) await presentResult("🔗 网页深度摘要", result);
  return result;
}

/** 把 AI 返回的 "1. xxx\n2. xxx\n3. xxx" 格式解析成回复候选数组 */
function parseReplyOptions(text) {
  const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
  const replies = [];
  for (const line of lines) {
    const m = line.match(/^(\d+)[\.\)、]\s*(.+)$/);
    if (m) replies.push(m[2].trim());
  }
  return replies;
}

/** 分支 E：剪贴板是聊天截图 → 识图模型读对话 → 生成推荐回复菜单（选中即复制） */
async function branchScreenshot(secrets, imageBase64) {
  await notify("📸 检测到聊天截图", "AI 正在阅读对话内容，生成推荐回复…");

  const cacheBranch = "screenshot::" + CONFIG.VISION_MODEL;
  const cached = getCache(cacheBranch, imageBase64);

  let raw;
  if (cached) {
    raw = cached;
    await notify("⚡ 命中缓存", "使用最近处理结果，未重新调用识图模型");
  } else {
    const systemPrompt =
      "你是一个贴心的聊天助手。这是一张聊天记录截图，请仔细阅读双方的对话内容，理解语境、关系和情绪，" +
      "然后针对对话中对方最新一条消息，给出 3 种不同语气的推荐回复：1. 随和自然 2. 简洁干脆 3. 认真详细。" +
      "直接输出回复正文本身，不要输出任何解释、前缀或多余文字，严格按以下格式逐行输出：\n1. xxx\n2. xxx\n3. xxx";

    try {
      raw = await callVisionAPI(secrets.apiKey, systemPrompt, imageBase64);
    } catch (e) {
      await fail("截图分析", e);
      return null;
    }
    setCache(cacheBranch, imageBase64, raw);
  }

  const replies = parseReplyOptions(raw);

  if (replies.length === 0) {
    // AI 没有按格式输出，直接把全文呈现给用户，允许整体复制
    await presentResult("📸 截图分析结果", raw);
    appendHistory("分支E · 截图推荐回复", "[聊天截图]", raw);
    await syncToTelegram(secrets, "分支E · 截图推荐回复", "[聊天截图]", raw);
    return raw;
  }

  const menu = new Alert();
  menu.title = "📸 推荐回复";
  menu.message = "选择一条，自动复制到剪贴板";
  replies.forEach(r => menu.addAction(r.length > 40 ? r.slice(0, 40) + "…" : r));
  menu.addAction("📄 查看全文");
  menu.addCancelAction("取消");

  const idx = await menu.presentSheet();
  if (idx === -1) {
    // 用户取消也记一条历史，方便之后在"查看历史"里找回全部候选回复
    appendHistory("分支E · 截图推荐回复", "[聊天截图]", raw);
    await syncToTelegram(secrets, "分支E · 截图推荐回复", "[聊天截图]", raw);
    return raw;
  }

  if (idx === replies.length) {
    await QuickLook.present(raw, false);
  } else {
    Pasteboard.copy(replies[idx]);
    await notify("📋 已复制", replies[idx]);
    await maybeSpeak(replies[idx]);
  }

  appendHistory("分支E · 截图推荐回复", "[聊天截图]", raw);
  await syncToTelegram(secrets, "分支E · 截图推荐回复", "[聊天截图]", raw);
  return raw;
}

/**
 * 多步串联：让用户依次勾选若干已有功能（同一菜单内的 FLOWS），
 * 上一步的输出自动作为下一步的输入，中间步骤只做轻量通知、不弹结果，
 * 只有最后一步走"实时展示"，最终结果才被复制/记录/播报/展示。
 *
 * @param secrets      硅基流动密钥等
 * @param rawText      本次触发的原始文本（第 1 步的输入）
 * @param availableFlows 可供串联选择的 flow 列表（需排除"查看历史""多步串联"自身等特殊项）
 * @param cachePrefix  缓存/历史分支名前缀，如 "chain-zh" / "chain-code"，避免不同菜单互相污染缓存
 */
async function branchChainFlows(secrets, rawText, availableFlows, cachePrefix) {
  const MAX_STEPS = 5;
  const routeType = cachePrefix === "code" ? "code" : "zh";  // 让串联各步沿用发起分支的模型路由
  const chain = [];

  while (chain.length < MAX_STEPS) {
    const menu = new Alert();
    menu.title = "🔗 多步串联";
    menu.message = chain.length === 0
      ? "选择第 1 步要执行的功能"
      : `已选：${chain.map(f => f.name).join(" → ")}\n继续选下一步，或结束串联`;
    availableFlows.forEach(f => menu.addAction(f.name));
    if (chain.length > 0) menu.addAction("✅ 结束并执行");
    menu.addCancelAction("取消");

    const idx = await menu.presentSheet();
    if (idx === -1) return null; // 取消整条链

    if (chain.length > 0 && idx === availableFlows.length) break; // 点了"结束并执行"

    chain.push(availableFlows[idx]);
  }

  if (chain.length === 0) {
    await alertBox("🔗 多步串联", "未选择任何步骤，已取消。");
    return null;
  }

  let currentInput = rawText;
  let finalResult = null;
  let streamedFinal = false;

  for (let i = 0; i < chain.length; i++) {
    const step = chain[i];
    const isLast = i === chain.length - 1;

    if (!isLast) {
      await notify(`🔗 步骤 ${i + 1}/${chain.length} · ${step.name}`, "处理中，结果将自动传入下一步…");
      currentInput = await callDeepSeek(secrets.apiKey, step.prompt, currentInput, recommendModel(routeType, currentInput.length));
    } else {
      const stepTitle = `🔗 第 ${i + 1}/${chain.length} 步 · ${step.name}`;
      const { text, streamed } = await generateWithDisplay(secrets, stepTitle, step.prompt, currentInput, { model: recommendModel(routeType, currentInput.length) });
      finalResult = text;
      streamedFinal = streamed;
      currentInput = text;
    }
  }

  const chainName = "🔗 多步串联 · " + chain.map(f => f.name).join(" → ");
  Pasteboard.copy(finalResult);
  await notify(`✅ ${chainName} 完成（已覆盖剪贴板）`, finalResult);

  setCache(cachePrefix + "::chain::" + chain.map(f => f.name).join("|"), rawText, finalResult);
  appendHistory(chainName, rawText, finalResult);
  await syncToTelegram(secrets, chainName, rawText, finalResult);
  await maybeSpeak(finalResult);
  if (!streamedFinal) await presentResult(chainName, finalResult);

  return finalResult;
}

/** 分支 D：代码 / 报错日志诊断菜单 */
async function branchCode(secrets, rawText) {
  const FLOWS = [
    { name: "🐛 找 Bug / 报错诊断", prompt: "你是全栈顶级运维专家。请诊断这段代码或报错日志，用大白话中文指出根因，并给出最快的排查/修复方案。" },
    { name: "📖 逐段解释代码", prompt: "请逐段解释这段代码的作用，用简洁中文说明每一部分在做什么。" },
    { name: "🛠️ 重构优化建议", prompt: "请审查这段代码，指出可优化点（性能、可读性、安全性、边界情况），给出具体修改建议。" },
    { name: "📝 补全注释", prompt: "请为这段代码补充清晰的中文注释，保持代码逻辑不变，只输出补充注释后的完整代码。" },
    { name: "🔁 语言转换", prompt: "请将这段代码用另一种主流语言重写（如原为 JS 则转 Python，反之亦然），保持逻辑一致，并简要说明关键差异。" },
    { name: "🔗 多步串联", prompt: "__CHAIN__" },  // 特殊项：依次串联执行以上多个功能
  ];

  const menu = new Alert();
  menu.title = "💻 检测到代码 / 日志";
  menu.message = rawText.length > 80 ? rawText.slice(0, 80) + "…" : rawText;
  FLOWS.forEach(f => menu.addAction(f.name));
  menu.addCancelAction("取消");

  const idx = await menu.presentSheet();
  if (idx === -1) return null;

  const flow = FLOWS[idx];

  if (flow.prompt === "__CHAIN__") {
    const chainable = FLOWS.filter(f => f.prompt && !f.prompt.startsWith("__"));
    return await branchChainFlows(secrets, rawText, chainable, "code");
  }

  const cached = getCache("code::" + flow.name, rawText);
  if (cached) {
    await notify("⚡ 命中缓存", `${flow.name} 使用最近结果，未重新调用 AI`);
    await presentResult(`${flow.name} · 处理结果（缓存）`, cached);
    return cached;
  }

  await notify(`${flow.name} 处理中`, "AI 正在深度分析，请稍候…");
  const { text: result, streamed } = await generateWithDisplay(secrets, `${flow.name} · 处理结果`, flow.prompt, rawText, { model: recommendModel("code", rawText.length) });

  Pasteboard.copy(result);
  await notify(`✅ ${flow.name} 完成（已覆盖剪贴板）`, result);

  setCache("code::" + flow.name, rawText, result);
  appendHistory(`分支D · ${flow.name}`, rawText, result);
  await syncToTelegram(secrets, `分支D · ${flow.name}`, rawText, result);
  await maybeSpeak(result);
  if (!streamed) await presentResult(`${flow.name} · 处理结果`, result);
  return result;
}

/** 分支 B：任意非中文语言 → 翻译成中文 */
async function branchLang(secrets, rawText) {
  await notify("🌐 检测到非中文文本", "AI 翻译进行中…");

  const cached = getCache("lang", rawText);
  if (cached) {
    Pasteboard.copy(cached);
    await notify("⚡ 命中缓存（已覆盖剪贴板）", cached);
    return cached;
  }

  const { text: result } = await generateWithDisplay(
    secrets,
    "🌐 翻译结果",
    "你是一个顶级同声传译。请直接将以下内容（无论原文是什么语言）翻译成通俗易懂的大白话中文。不要解释，不要输出任何前缀或引言。",
    rawText,
    { model: recommendModel("lang", rawText.length), injectProfile: false }
  );

  Pasteboard.copy(result);
  await notify("✅ 翻译完成（已覆盖剪贴板）", result);

  setCache("lang", rawText, result);
  appendHistory("分支B · 翻译", rawText, result);
  await syncToTelegram(secrets, "分支B · 翻译", rawText, result);
  await maybeSpeak(result);
  return result;
}

/** 分支 C：中文业务处理菜单（含记忆/用量/进化/执行等特殊项） */
async function branchChinese(secrets, rawText) {
  const FLOWS = [
    { name: "⚡ 核心执行", prompt: "请将这段文本提取出最核心的行动项（To-Do List），并生成一份直接可以回复的 Telegram 消息模板。" },
    { name: "📐 逻辑拆解", prompt: "你是一个严谨的系统架构师。请帮我梳理这段配置/代码/业务逻辑中的规则边界，用结构化的清单列出。" },
    { name: "🛡️ 风险评估", prompt: "你是一个经验丰富的商业安全专家。请立刻找出这段文案、合同或规则中可能存在的陷阱、潜在风险和漏洞。" },
    { name: "💬 快捷回复", prompt: "针对业务上下文，生成 3 种不同语气的 Telegram 快捷回复模板（1. 礼貌婉拒；2. 积极推进并索要更多细节；3. 强势定规矩/催款）。" },
    { name: "📢 频道润色", prompt: "请帮我把这段话进行高阶润色。要求：去掉所有废话和口水词，使用务实严谨的词汇，排版多用 Emoji 符号做分段点缀，使其适合在 Telegram 频道发布。" },
    { name: "📊 智能变表", prompt: "请把这段混乱的文本/数字进行清洗，剔除无效信息，将其整理成一份标准的 Markdown 结构化表格（包含时间、项目、主体、金额等核心列）。" },
    { name: "🛠️ 报错诊断", prompt: "你是一个全栈顶级运维专家。请立刻诊断这段报错信息，用大白话中文指出核心崩溃原因，并给出最快的排查修复命令行。" },
    { name: "🧠 局势盘算", prompt: "请帮我复盘这段局势，从「天时（时机趋势）、地利（资源卡位）、人和（利益博弈）」三个维度进行极简剖析，并给出一条进取、一条退守的行动建议。" },
    { name: "🔗 多步串联", prompt: "__CHAIN__" },  // 特殊项：依次串联执行以上多个功能
    ...(CONFIG.ENABLE_TOOLS ? [{ name: "🤖 AI 执行操作", prompt: "__AGENT__" }] : []),  // Function Calling
    { name: "📊 本月用量", prompt: "__USAGE__" },  // 特殊项：查看 Token 用量
    ...(CONFIG.SELF_EVOLVE_ENABLED ? [{ name: "🧬 自我进化", prompt: "__EVOLVE__" }] : []),  // 手动触发画像更新
    { name: "🕘 查看历史", prompt: "__HISTORY__" },  // 特殊项：不调用 AI，仅查看本地历史
  ];

  const menu = new Alert();
  menu.title = "🧠 AI 智能路由引擎";
  menu.message = rawText.length > 60 ? rawText.slice(0, 60) + "…" : rawText;
  FLOWS.forEach(f => menu.addAction(f.name));
  menu.addCancelAction("取消");

  const idx = await menu.presentSheet();
  if (idx === -1) return null;

  const flow = FLOWS[idx];

  // —— 特殊项（不进入常规 AI 处理流程）——
  if (flow.prompt === "__HISTORY__") { await viewHistory(); return null; }
  if (flow.prompt === "__USAGE__") { await viewUsage(); return null; }
  if (flow.prompt === "__EVOLVE__") { await evolveNow(secrets); return null; }
  if (flow.prompt === "__AGENT__") { return await branchAgent(secrets, rawText); }

  if (flow.prompt === "__CHAIN__") {
    const chainable = FLOWS.filter(f => f.prompt && !f.prompt.startsWith("__"));
    return await branchChainFlows(secrets, rawText, chainable, "zh");
  }

  const cached = getCache("zh::" + flow.name, rawText);
  if (cached) {
    Pasteboard.copy(cached);
    await notify(`⚡ ${flow.name} 命中缓存（已覆盖剪贴板）`, cached);
    await presentResult(`${flow.name} · 处理结果（缓存）`, cached);
    return cached;
  }

  await notify(`${flow.name} 处理中`, "AI 正在深度分析，请稍候…");

  // 长期记忆（RAG）：检索相似历史注入上下文
  let ragContext = "";
  try {
    ragContext = await retrieveRAGContext(secrets.apiKey, rawText);
  } catch (e) {
    console.warn("RAG 检索异常（忽略）: " + e.message);
  }
  const systemPrompt = prependSystem(flow.prompt, ragContext);

  const { text: result, streamed } = await generateWithDisplay(
    secrets,
    `${flow.name} · 处理结果`,
    systemPrompt,
    rawText,
    { model: recommendModel("zh", rawText.length) }
  );

  Pasteboard.copy(result);
  await notify(`✅ ${flow.name} 完成（已覆盖剪贴板）`, result);

  setCache("zh::" + flow.name, rawText, result);
  appendHistory(flow.name, rawText, result);
  await syncToTelegram(secrets, flow.name, rawText, result);
  await rememberRAG(secrets.apiKey, rawText, result, flow.name);
  await maybeSpeak(result);
  if (!streamed) await presentResult(`${flow.name} · 处理结果`, result);
  return result;
}

// ╔═══════════════════════ ⑨ 主 流 程 ═════════════════════════════╗

async function route(secrets) {
  // 优先检测剪贴板里是否是图片（例如聊天截图）→ 分支 E：识图 + 推荐回复
  let clipboardImage = null;
  try {
    if (Pasteboard.pasteImage) clipboardImage = Pasteboard.pasteImage();
  } catch (e) {
    clipboardImage = null; // 剪贴板不是图片时 Scriptable 可能抛错，视为无图片
  }

  if (clipboardImage) {
    const imageBase64 = imageToBase64(clipboardImage);
    console.log("路由判定: screenshot");
    await branchScreenshot(secrets, imageBase64);
    return;
  }

  let clipboard;
  try {
    clipboard = Pasteboard.paste();
  } catch (e) {
    throw new Error("剪贴板读取失败: " + e.message);
  }

  if (!clipboard || !clipboard.trim()) {
    await alertBox("📋 剪贴板为空", "请先复制一段文本 / 链接 / 聊天截图，再按下操作按钮。");
    return;
  }
  const text = clipboard.trim();

  const decision = detectRoute(text);
  console.log(`路由判定: ${decision.type}`);

  switch (decision.type) {
    case "url":
      await branchURL(secrets, text, decision.url);
      break;
    case "code":
      await branchCode(secrets, text);
      break;
    case "lang":
      await branchLang(secrets, text);
      break;
    default:
      await branchChinese(secrets, text);
      break;
  }
}

async function main() {
  const secrets = await loadSecrets();
  try {
    await route(secrets);
  } finally {
    // 收尾（在用户看到结果之后执行）：用量提醒 + 到期则自我进化
    await maybeAlertUsage();
    await maybeSelfEvolve(secrets);
  }
}

try {
  await main();
} catch (e) {
  await fail("脚本运行", e);
} finally {
  Script.complete();
}
