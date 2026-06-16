# G789 场景技能 · 安装说明

> 安装包: **g789-scenarios-pack-03.zip**  
> 场景范围: **S-201 ~ S-300**（共 100 个技能）  
> 生成时间: 2026-05-31 03:05:30

## 安装步骤（Windows）

1. 确保目标目录存在（任选其一）：
   - 用户全局：`C:\Users\admin\.cursor\skills\g789-scenarios`
   - 或项目内：`<项目>/.cursor/skills/g789-scenarios/`
2. 解压本 zip 到任意临时位置，得到文件夹 `g789-scenarios-pack-03/`。
3. 将 `g789-scenarios-pack-03/` 内的 **全部** `S-*` 子目录复制到上述 `g789-scenarios/` 中。
4. （可选）将本包 `SKILLS_INDEX.md` 保存为 `SKILLS_INDEX-pack-03.md` 便于查阅；全量 500 场景可对照仓库总索引 `SKILLS_INDEX.md`。
5. **多包合并**：对 pack-02 ~ pack-05 重复步骤 2–3，所有 `S-*` 目录落在**同一** `g789-scenarios/` 下（共 500 个文件夹）。
6. 重启 Cursor 或重新打开工作区，使技能被发现。

> zip 内根目录为 `g789-scenarios-pack-03/`（非直接 `S-*` 平铺），以便区分各安装包来源。

## 使用方式

- 在对话中 `@` 技能 **name**（见 `SKILLS_INDEX.md` 或各 `SKILL.md` frontmatter 的 `name` 字段）
- 也可直接描述场景名或场景 ID（如 `S-042`），Agent 会匹配对应技能

## 说明

- 技能**自包含**，无需 G789 本地知识库或外部 `@` 引用
- 本包索引见根目录 `SKILLS_INDEX.md`
- 全量 500 场景需安装全部 5 个 zip

## 重建安装包

```bash
python G:\789\scenarios\build_skill_install_packages.py
```
