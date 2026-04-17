# 术语库项目 (term_base)

基于 Obsidian 的业务术语智能管理系统。音频会议录音自动转录、AI 提取术语、自动关联、Git 同步。

## 目录结构

```
term_base/                ← Obsidian 仓库 + Git 仓库
├── index.md              ← 术语总览（128条，按系统分类）
├── log.md                ← 操作日志（自动化运行记录）
├── src/                  ← 源文件
│   ├── pending/          ← 待处理（放入音频/文档，自动扫描）
│   └── processed/        ← 已处理归档
├── term_vault/           ← 术语库（每条术语一个 .md 文件，128条）
├── templates/            ← 术语模板
├── views/                ← Dataview 视图页面
│   ├── 首页.md           ← 入口导航
│   ├── 术语总览.md       ← 全部术语表格
│   ├── 按系统查看.md     ← 按系统分类
│   ├── 最近更新.md       ← 最近修改的术语
│   ├── 术语仪表盘.md    ← 健康状况与统计
│   └── 孤立术语.md      ← 无入链的术语
└── scripts/              ← 自动化脚本
    ├── automate.py       ← 主流程（转录→AI提取→关联→写入→Git推送）
    ├── batch_transcribe.py ← 批量转录（手动触发）
    ├── fix_relations.py  ← 批量修复空关联术语
    ├── lint.py           ← 健康检查（字段、wikilink、孤立术语）
    ├── config.json       ← 配置（AI、邮箱、定时）
    └── state.json        ← 运行状态
```

## 术语文件格式

每条术语 = `term_vault/<术语名>.md`：

```markdown
---
system: "所属系统"
en: "englishName"
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

## 自动化流程

每天 09:00 由 Windows 定时任务自动执行（`TermBase_AutoRun`）：

```
① 放入音频 → ② 转录(whisper) → ③ AI提取术语(qwen3.5-plus)
→ ④ 变更检测 → ⑤ 写入term_vault/ → ⑥ 邮件通知
→ ⑦ Git自动推送GitHub → ⑧ 记录操作日志
```

- 已有 txt 转录文本时跳过转录，直接提取术语
- AI 提取时传入已有术语列表，自动建立上下游关联
- 术语变更时记录到 pending_changes，等邮件审批后更新
- config.json 中设置 `skip_approve: true` 可跳过审批直接更新

## 手动操作

```bash
# 手动触发一次完整流程
python scripts/automate.py --now

# 仅批量转录（不提取术语）
python scripts/batch_transcribe.py

# 批量修复空关联术语
python scripts/fix_relations.py

# 健康检查
python scripts/lint.py

# 注册/移除定时任务
python scripts/automate.py --install
python scripts/automate.py --uninstall
```

## 配置

编辑 `scripts/config.json`：
- AI：阿里百炼 qwen3.5-plus（已配置）
- 邮箱：待配置（hongzhao.com SMTP 暂不通）
- `skip_approve: true` — 跳过审批，变更直接写入
- 邮箱配置说明见 `scripts/配置模板.md`

## 推荐 Obsidian 插件

- **Dataview** — 表格视图和查询（views/ 依赖此插件）
- **Obsidian Git** — 自动版本管理和变更追踪
