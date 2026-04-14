# 术语库项目 (term_base)

基于 Obsidian 的业务术语智能管理系统。

## 目录结构

本项目根目录即为 Obsidian 仓库。

```
term_base/                ← Obsidian 仓库根目录
├── src/                  ← 待解析的文档/音频
│   ├── pending/          ← 未解析
│   └── processed/        ← 已处理文件归档
├── terms/                ← 术语库（每条术语一个 .md 文件）
├── templates/            ← 术语模板
├── views/                ← Dataview 视图页面
└── scripts/              ← 工具脚本（导出等）
```

## 术语文件格式

每条术语 = `terms/<术语名>.md`，格式：

```markdown
---
system: "所属系统"
source: "来源文件名"
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
---

业务定义内容...

## 关联
- 上游：[[相关术语]]
- 下游：[[相关术语]]
- 相关：[[相关术语]]
```

## system 字段可选值

供应链平台、电商平台、财务系统、人力资源、生产制造、其他

## 工作流

1. 将待解析文件放入 `src/pending/`
2. 运行 `/extract` 提取术语
3. 在 Obsidian 中查看、编辑术语
4. 需要导出时运行 `python scripts/export.py`

## 推荐 Obsidian 插件

- **Dataview** — 表格视图和查询（views/ 依赖此插件）
- **Obsidian Git** — 自动版本管理和变更追踪
- **Templater**（可选） — 基于模板快速新建术语
