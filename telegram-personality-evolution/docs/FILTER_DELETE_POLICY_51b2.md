# 消息过滤永久删除政策

更新：2026-07-22

以下类别 **永久删除**，禁止恢复、禁止进入 clean / 上下文 / 标签 / 训练集：

1. **empty_media** — 无有效文字的纯媒体
2. **service** — 系统服务消息
3. **invalid** — 空文本 / 坏时间 / 无发送者

`07_filtered_restored/` 已删除。原始 `00_raw_origin` 只读保留，但不回灌上述三类。

## 深分析覆盖（现行）

```text
valid_message_count <= 100
  OR value.stars >= 3   # 高价值及以上
→ deep_analysis = true
```

主队列：`06_full_coverage/deep_priority_le100.jsonl`（约 7402 人）。  
兼容：`deep_priority_le50.jsonl`（≤50 子集）。
