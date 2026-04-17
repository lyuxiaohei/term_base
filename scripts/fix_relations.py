"""
修复空关联术语 — 用 AI 补充上下游关联关系
用法: python fix_relations.py
"""
import json
import glob
import os
import re
import time
import requests
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMS_DIR = os.path.join(BASE_DIR, "term_vault")
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

BATCH_SIZE = 15  # 每批发送给AI的术语数


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_empty_terms():
    """返回空关联的术语列表 [{name, system, definition}]"""
    empty = []
    for fp in sorted(glob.glob(os.path.join(TERMS_DIR, "*.md"))):
        with open(fp, encoding="utf-8") as f:
            content = f.read()
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()

        # 检查关联部分是否为空
        rel_section = body.split("## 关联")[1].strip() if "## 关联" in body else ""
        if "[[" not in rel_section:
            name = os.path.splitext(os.path.basename(fp))[0]
            definition = body.split("## 关联")[0].strip() if "## 关联" in body else body
            empty.append({
                "name": name,
                "system": meta.get("system", ""),
                "definition": definition,
            })
    return empty


def get_all_term_names():
    """返回所有术语名"""
    return sorted([
        os.path.splitext(os.path.basename(f))[0]
        for f in glob.glob(os.path.join(TERMS_DIR, "*.md"))
    ])


def fix_batch(terms_batch, all_names, config):
    """用AI为一批术语补充关联关系"""
    ai = config["ai"]
    url = f"{ai['base_url'].rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {ai['api_key']}", "Content-Type": "application/json"}

    terms_desc = "\n".join(
        f"- {t['name']}（{t['system']}）：{t['definition'][:100]}"
        for t in terms_batch
    )

    prompt = f"""你是业务术语关联分析专家。请为以下术语补充上下游关联关系。

已有术语列表（关联目标只能从这个列表中选）：
{', '.join(all_names)}

待补充关联的术语：
{terms_desc}

要求：
1. 为每个术语返回 upstream（上游）、downstream（下游）、related（相关）三个列表
2. 列表中的值必须是已有术语列表中存在的术语名
3. 如果没有关联则返回空数组 []
4. 返回 JSON 数组，每个元素包含 name、upstream、downstream、related
5. 不要返回其他内容"""

    payload = {
        "model": ai["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=180)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]

    json_match = re.search(r"\[.*\]", content, re.DOTALL)
    if json_match:
        return json.loads(json_match.group())
    return []


def update_term_relations(name, upstream, downstream, related):
    """更新术语文件的关联部分"""
    filepath = os.path.join(TERMS_DIR, f"{name}.md")
    if not os.path.exists(filepath):
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    parts = content.split("---", 2)
    if len(parts) < 3:
        return False

    body = parts[2].strip()
    definition = body.split("## 关联")[0].strip() if "## 关联" in body else body

    relation_lines = []
    if upstream:
        items = ", ".join(f"[[{t}]]" for t in upstream)
        relation_lines.append(f"- 上游：{items}")
    if downstream:
        items = ", ".join(f"[[{t}]]" for t in downstream)
        relation_lines.append(f"- 下游：{items}")
    if related:
        items = ", ".join(f"[[{t}]]" for t in related)
        relation_lines.append(f"- 相关：{items}")
    if not relation_lines:
        relation_lines.append("-")

    new_body = f"{definition}\n\n## 关联\n{chr(10).join(relation_lines)}\n"
    new_content = f"---{parts[1]}---\n\n{new_body}"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True


def main():
    config = load_config()
    empty_terms = get_empty_terms()
    all_names = get_all_term_names()

    print(f"空关联术语: {len(empty_terms)} 条")
    print(f"总术语库: {len(all_names)} 条")
    print(f"分批处理: 每批 {BATCH_SIZE} 条\n")

    fixed = 0
    for i in range(0, len(empty_terms), BATCH_SIZE):
        batch = empty_terms[i:i + BATCH_SIZE]
        names = [t["name"] for t in batch]
        print(f"[{i+1}-{i+len(batch)}] 处理: {', '.join(names[:5])}...")

        try:
            results = fix_batch(batch, all_names, config)
        except Exception as e:
            print(f"  AI 调用失败: {e}")
            continue

        if not results:
            print("  未返回结果")
            continue

        for r in results:
            name = r.get("name", "")
            upstream = r.get("upstream", [])
            downstream = r.get("downstream", [])
            related = r.get("related", [])
            if update_term_relations(name, upstream, downstream, related):
                rels = []
                if upstream:
                    rels.append(f"↑{len(upstream)}")
                if downstream:
                    rels.append(f"↓{len(downstream)}")
                if related:
                    rels.append(f"~{len(related)}")
                print(f"  OK {name}: {' '.join(rels)}")
                fixed += 1

        # 避免API限流
        time.sleep(2)

    print(f"\n完成！已修复 {fixed}/{len(empty_terms)} 条术语的关联关系")


if __name__ == "__main__":
    main()
