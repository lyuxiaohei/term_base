"""
术语库健康检查脚本
检查所有术语文件的完整性：frontmatter字段、wikilink引用、孤立术语等
"""

import os
import re
import sys
from pathlib import Path
from datetime import datetime

TERMS_DIR = Path(__file__).parent.parent / "term_vault"

REQUIRED_FIELDS = ["system", "created", "updated"]
VALID_SYSTEMS = ["供应链平台", "电商平台", "财务系统", "人力资源", "生产制造", "其他"]


def parse_frontmatter(content):
    """解析YAML frontmatter，返回dict"""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    meta = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip().strip("'\"")
    return meta


def extract_wikilinks(content):
    """提取所有 [[wikilink]] 目标"""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def load_all_terms():
    """加载所有术语"""
    terms = {}
    for f in sorted(TERMS_DIR.glob("*.md")):
        content = f.read_text(encoding="utf-8")
        meta = parse_frontmatter(content)
        links = extract_wikilinks(content)
        terms[f.stem] = {"meta": meta, "links": links, "file": f}
    return terms


def check_missing_fields(terms):
    """检查缺少必填字段的术语"""
    issues = []
    for name, data in terms.items():
        meta = data["meta"]
        for field in REQUIRED_FIELDS:
            if field not in meta or not meta[field]:
                issues.append(f"  {name}: 缺少 {field}")
        if "en" not in meta or not meta["en"]:
            issues.append(f"  {name}: 缺少 en（英文名）")
    return issues


def check_invalid_system(terms):
    """检查 system 字段是否合法"""
    issues = []
    for name, data in terms.items():
        system = data["meta"].get("system", "")
        if system and system not in VALID_SYSTEMS:
            issues.append(f"  {name}: system='{system}' 不在合法值中")
    return issues


def check_broken_wikilinks(terms):
    """检查指向不存在术语的 wikilink"""
    all_names = set(terms.keys())
    issues = []
    for name, data in terms.items():
        for link in data["links"]:
            if link not in all_names:
                issues.append(f"  {name} -> [[{link}]] （目标不存在）")
    return issues


def check_orphan_terms(terms):
    """检查孤立术语（没有任何其他术语引用它）"""
    referenced = set()
    for name, data in terms.items():
        for link in data["links"]:
            referenced.add(link)
    orphans = []
    for name in terms:
        if name not in referenced:
            orphans.append(f"  {name}")
    return orphans


def check_empty_relations(terms):
    """检查没有关联关系的术语"""
    issues = []
    for name, data in terms.items():
        content = data["file"].read_text(encoding="utf-8")
        if "## 关联" not in content:
            issues.append(f"  {name}: 没有 ## 关联 部分")
            continue
        # 提取关联部分
        rel_section = content.split("## 关联")[1].strip() if "## 关联" in content else ""
        has_upstream = "上游：" in rel_section and len(rel_section.split("上游：")[1].strip()) > 0
        has_downstream = "下游：" in rel_section and len(rel_section.split("下游：")[1].strip()) > 0
        has_related = "相关：" in rel_section and len(rel_section.split("相关：")[1].strip()) > 0
        if not (has_upstream or has_downstream or has_related):
            issues.append(f"  {name}: 关联部分为空")
    return issues


def check_date_format(terms):
    """检查日期格式"""
    issues = []
    date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    for name, data in terms.items():
        meta = data["meta"]
        for field in ["created", "updated"]:
            val = meta.get(field, "")
            if val and not date_re.match(val):
                issues.append(f"  {name}: {field}='{val}' 格式不正确（应为 YYYY-MM-DD）")
    return issues


def run_lint():
    """执行所有检查"""
    print(f"术语库健康检查 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"术语目录: {TERMS_DIR}")
    print()

    terms = load_all_terms()
    print(f"共加载 {len(terms)} 条术语\n")

    total_issues = 0

    checks = [
        ("缺少必填字段", check_missing_fields),
        ("system 字段合法性", check_invalid_system),
        ("日期格式", check_date_format),
        ("空关联关系", check_empty_relations),
        ("断裂的 wikilink", check_broken_wikilinks),
        ("孤立术语（无入链）", check_orphan_terms),
    ]

    for title, check_fn in checks:
        issues = check_fn(terms)
        status = "PASS" if not issues else f"FAIL ({len(issues)})"
        print(f"[{status}] {title}")
        if issues:
            total_issues += len(issues)
            for issue in issues:
                print(issue)
        print()

    # 统计
    system_counts = {}
    for name, data in terms.items():
        s = data["meta"].get("system", "未分类")
        system_counts[s] = system_counts.get(s, 0) + 1

    print("系统分布:")
    for s, c in sorted(system_counts.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c} 条")
    print()

    print(f"检查完成。共发现 {total_issues} 个问题。")
    return total_issues


if __name__ == "__main__":
    sys.exit(0 if run_lint() == 0 else 1)
