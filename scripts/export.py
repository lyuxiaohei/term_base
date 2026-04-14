"""
术语库导出脚本
用法: python export.py [输出文件名]
默认输出: 术语库导出_<日期>.xlsx
"""

import glob
import sys
import os
from datetime import datetime

try:
    import yaml
except ImportError:
    print("需要安装 PyYAML: pip install pyyaml")
    sys.exit(1)

try:
    import openpyxl
except ImportError:
    print("需要安装 openpyxl: pip install openpyxl")
    sys.exit(1)

VAULT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMS_DIR = os.path.join(VAULT_DIR, "terms")


def parse_term(filepath):
    """解析单个术语文件，返回 (元数据, 正文)"""
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, None

    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()

    # 提取定义（关联部分之前的内容）
    definition = body.split("## 关联")[0].strip() if "## 关联" in body else body

    name = os.path.splitext(os.path.basename(filepath))[0]
    return name, {
        "system": meta.get("system", ""),
        "definition": definition,
        "source": meta.get("source", ""),
        "updated": str(meta.get("updated", "")),
    }


def export(output_path=None):
    if not output_path:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(VAULT_DIR, f"术语库导出_{date_str}.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "术语库"

    headers = ["术语名称", "所属系统", "业务定义", "来源文件", "更新时间"]
    ws.append(headers)

    # 设置列宽
    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 60
    ws.column_dimensions["D"].width = 25
    ws.column_dimensions["E"].width = 15

    count = 0
    for filepath in sorted(glob.glob(os.path.join(TERMS_DIR, "*.md"))):
        name, data = parse_term(filepath)
        if name and data:
            ws.append([name, data["system"], data["definition"],
                       data["source"], data["updated"]])
            count += 1

    wb.save(output_path)
    print(f"已导出 {count} 条术语到: {output_path}")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else None
    export(output)
