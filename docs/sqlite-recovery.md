# SQLite 损坏库抢救手册

`sqlite3 .recover` 在 3.40.1 上会在 `writable_schema` 阶段抛 `SQL logic error`，
只吐出 7 行 PRAGMA 头、dump 为空。本手册给出不依赖 `.recover` 的第二套方案：
用 Python 的 `sqlite3` 逐表读取，遇到坏页就二分定位边界跳过去，
把损失压到坏页本身那几行，而不是整张表。

工具：[`tools/sqlite_salvage.py`](../tools/sqlite_salvage.py)（纯标准库，无第三方依赖）。

## 0. 先别动原库

所有操作都在**副本**上做。原库只读、immutable 打开，脚本永远不会写它，
但复制一份仍然是最省心的前提。

```bash
mkdir -p /root/rescue && cd /root/rescue
cp -a /path/to/main.db        ./main.db
cp -a /path/to/main.db-wal    ./main.db-wal 2>/dev/null || true
cp -a /path/to/main.db-shm    ./main.db-shm 2>/dev/null || true
sha256sum main.db | tee main.db.sha256
```

**WAL 注意**：脚本用 `immutable=1` 打开，这个标志会**忽略 `-wal` 文件**。
如果 `-wal` 非空（脚本会警告），先在副本上做一次 checkpoint 把它合并进主库，
否则 WAL 里还没落盘的事务不会被救出来：

```bash
python3 -c "import sqlite3;c=sqlite3.connect('main.db');c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close()"
```

## 1. 先确认要不要编译新版 sqlite

不一定要编译。系统的 `sqlite3` CLI 旧，不代表 Python 绑定的也旧：

```bash
sqlite3 --version                                    # CLI，可能是 3.40.1
python3 -c "import sqlite3;print(sqlite3.sqlite_version)"   # 抢救脚本实际用的版本
```

抢救脚本走的是 Python 绑定那一份。只有当 Python 那边也明显偏旧、
且下面的流程报出解析层面的问题时，才值得去编译新版。脚本每次运行都会把
实际使用的版本打在第一行日志里。

## 2. 跑抢救

```bash
python3 tools/sqlite_salvage.py main.db rescued.db \
    --segment messages:session_id \
    --report rescue.json
```

- `--segment messages:session_id`：按 session 分段抢救。每个 session 单独扫，
  一个 session 撞上坏页不会连累其他 session，报告里也能看出具体是哪几个
  session 掉了数据。
- `--report`：写一份 JSON，含每表行数、跳过的 rowid 区间、错误样本。
- 想先小范围试：加 `--tables sessions` 只跑一张表。
- 退出码：`0` = 全部干净读完，`2` = 救出来了但有损失，`1` = 没法进行。

对 165M 的库，整个过程是秒级到分钟级，不需要挂后台。

## 3. 核对结果

```bash
python3 - <<'PY'
import sqlite3
src = sqlite3.connect("file:main.db?mode=ro&immutable=1", uri=True)
dst = sqlite3.connect("rescued.db")
print("integrity:", dst.execute("PRAGMA integrity_check").fetchone()[0])
for t in ("sessions", "messages"):
    try:    before = src.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    except Exception as e: before = f"unreadable ({e})"
    after = dst.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"{t}: before={before} after={after}")
# 哪些 session 掉了消息
print(dst.execute(
    "SELECT count(*) FROM sessions s WHERE NOT EXISTS"
    " (SELECT 1 FROM messages m WHERE m.session_id = s.id)").fetchone()[0],
    "session(s) 现在没有任何消息")
PY
```

`sessions` 应该是 129 且完整。`messages` 的差额就是坏页吃掉的行，
`rescue.json` 里 `skipped_spans` 给出对应的 rowid 区间。

如果有行因为约束冲突插不进去，脚本不会丢掉它们，而是连同原因写进
`_salvage_quarantine` 表，可以事后单独看：

```bash
python3 -c "import sqlite3;print(sqlite3.connect('rescued.db').execute('SELECT tbl,reason,count(*) FROM _salvage_quarantine GROUP BY 1,2').fetchall())" 2>/dev/null || echo "无隔离行"
```

## 4. 换上去

确认无误后再替换，旧库留着别删：

```bash
systemctl stop <服务名>          # 先停写入方
mv /path/to/main.db /path/to/main.db.corrupt.$(date +%F)
cp rescued.db /path/to/main.db
systemctl start <服务名>
```

根库（50M 那个）同样流程走一遍，只是不需要 `--segment`。

## 工作原理

1. 只读 + `immutable=1` 打开，绝不写原库、不加锁、不触发 checkpoint。
2. `text_factory` 用 `errors="replace"` 解码 —— 坏页里常有非法 UTF-8 字节，
   默认行为会直接抛异常，把一行本来完好的数据也搞丢。
3. 按 rowid 顺序批量读。一旦某批报 `database disk image is malformed`，
   先改成一行一行读，把坏页**之前**那些仍然可读的行榨出来；
   等单行读也失败，才说明真的走到坏页了。
4. 这时用**倍增探测**向前跳，直到某次读成功，再**二分回退**收紧边界，
   把跳过的 rowid 区间压到最小。区间记进报告。
5. 表的原始 DDL 原样重建，索引/触发器/视图最后统一重放；
   rowid 显式保留，救出来的行和原来一一对应。

## 已验证

`tests/test_sqlite_salvage.py` 会真的造一个库、用 `dbstat` 定位 `messages`
的叶子页、往上面写随机字节，然后断言抢救结果。

```bash
python3 tests/test_sqlite_salvage.py     # 或 python3 -m pytest tests/ -q
```

实测对照（207 MB、193,500 条消息、59 个分散坏页）：

| 方式 | 救回消息数 | 占比 |
| --- | --- | --- |
| 直接 `SELECT * FROM messages` | 3,253 | 1.7% |
| `sqlite_salvage.py` | 193,269 | **99.88%** |

耗时 4.6 秒，59 个坏页对应正好 59 个跳过区间、约 231 个 rowid。
救出的行与未损坏原库逐行比对：无伪造行、无内容偏差。
