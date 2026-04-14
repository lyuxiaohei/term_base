"""
术语库自动化脚本
用法:
  python automate.py --now       手动立即执行
  python automate.py --install   注册 Windows 定时任务
  python automate.py --uninstall 移除定时任务
"""

import json
import os
import re
import sys
import glob
import subprocess
import smtplib
import imaplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("需要安装: pip install pyyaml")
    sys.exit(1)

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("需要安装: pip install faster-whisper")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("需要安装: pip install requests")
    sys.exit(1)

# ─── 路径常量 ───────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
TERMS_DIR = BASE_DIR / "terms"
PENDING_DIR = BASE_DIR / "src" / "pending"
PROCESSED_DIR = BASE_DIR / "src" / "processed"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
STATE_PATH = Path(__file__).resolve().parent / "state.json"

SYSTEM_OPTIONS = ["供应链平台", "电商平台", "财务系统", "人力资源", "生产制造", "其他"]

# ─── 配置 & 状态管理 ─────────────────────────────────────


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"processed_files": [], "pending_changes": {}, "last_run": None}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ─── 模块1: 扫描与转录 ─────────────────────────────────


def scan_new_files(config, state):
    """扫描监控目录，返回未处理过的文件列表"""
    monitor_dir = config.get("monitor_dir")
    if not monitor_dir or not os.path.isdir(monitor_dir):
        print(f"[警告] 监控目录未配置或不存在: {monitor_dir}")
        return []

    extensions = config.get("supported_extensions", [".mp3", ".wav", ".m4a"])
    processed = set(state.get("processed_files", []))
    new_files = []

    for f in os.listdir(monitor_dir):
        ext = os.path.splitext(f)[1].lower()
        if ext in extensions:
            full_path = os.path.join(monitor_dir, f)
            if full_path not in processed:
                new_files.append(full_path)

    return new_files


def transcribe(file_path):
    """用 faster-whisper 转录音频文件，返回文本"""
    print(f"  转录: {os.path.basename(file_path)}")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(file_path, language="zh", beam_size=5, vad_filter=True)

    text_parts = [seg.text for seg in segments]
    return "".join(text_parts)


def save_transcription(file_path, text):
    """保存转录文本到 src/pending/，返回保存路径"""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    basename = os.path.splitext(os.path.basename(file_path))[0]
    output = PENDING_DIR / f"{basename}.txt"
    with open(output, "w", encoding="utf-8") as f:
        f.write(text)
    return output


def archive_source(file_path, state):
    """将源文件移到 processed 目录"""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED_DIR / os.path.basename(file_path)
    # 避免重名
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        dest = PROCESSED_DIR / f"{stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}{suffix}"
    os.rename(file_path, dest)
    state.setdefault("processed_files", []).append(file_path)


# ─── 模块2: AI 术语提取 ─────────────────────────────────

EXTRACT_PROMPT = """你是一个业务术语提取专家。请从以下文本中提取所有业务术语。

要求：
1. 每个术语包含：name（术语名）、system（所属系统）、definition（定义）
2. system 必须是以下之一：供应链平台、电商平台、财务系统、人力资源、生产制造、其他
3. definition 要清晰完整，基于文本内容归纳
4. 返回 JSON 数组格式，不要其他内容

文本：
{text}"""


def extract_terms_ai(text, config):
    """调用 AI API 提取术语，返回列表 [{name, system, definition}]"""
    ai = config.get("ai", {})
    api_key = ai.get("api_key", "")
    if not api_key:
        print("[警告] AI API Key 未配置，跳过术语提取")
        return []

    url = f"{ai.get('base_url', 'https://api.openai.com/v1').rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    # 文本太长则截断
    max_chars = 12000
    truncated = text[:max_chars] + ("..." if len(text) > max_chars else "")

    payload = {
        "model": ai.get("model", "gpt-4o-mini"),
        "messages": [
            {"role": "user", "content": EXTRACT_PROMPT.format(text=truncated)}
        ],
        "temperature": 0.1,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

        # 提取 JSON 部分
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if json_match:
            terms = json.loads(json_match.group())
            return terms
    except Exception as e:
        print(f"[错误] AI 提取失败: {e}")

    return []


# ─── 模块3: 变更检测 ───────────────────────────────────


def load_existing_terms():
    """加载 terms/ 下已有术语，返回 {名称: {system, definition, source, created, updated}}"""
    existing = {}
    for fp in glob.glob(str(TERMS_DIR / "*.md")):
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        meta = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()
        definition = body.split("## 关联")[0].strip() if "## 关联" in body else body
        name = os.path.splitext(os.path.basename(fp))[0]
        existing[name] = {
            "system": meta.get("system", ""),
            "definition": definition,
            "source": meta.get("source", ""),
            "created": meta.get("created", ""),
            "updated": meta.get("updated", ""),
        }
    return existing


def detect_changes(new_terms, existing_terms):
    """分类：新增 / 变更 / 无变化"""
    added, changed, unchanged = [], [], []

    for term in new_terms:
        name = term["name"]
        if name not in existing_terms:
            added.append(term)
        else:
            old_def = existing_terms[name]["definition"]
            if term["definition"].strip() != old_def.strip():
                changed.append({**term, "old_definition": old_def})
            else:
                unchanged.append(term)

    return added, changed, unchanged


def write_term_file(name, system, definition, source):
    """写入一个术语 Markdown 文件"""
    TERMS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = name.replace("/", "-").replace("\\", "-")
    filepath = TERMS_DIR / f"{safe_name}.md"
    today = datetime.now().strftime("%Y-%m-%d")

    # 如果已存在，保留 created
    created = today
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            parts = f.read().split("---", 2)
            if len(parts) >= 3:
                old_meta = yaml.safe_load(parts[1]) or {}
                created = old_meta.get("created", today)

    content = f"""---
system: "{system}"
source: "{source}"
created: "{created}"
updated: "{today}"
---

{definition}

## 关联
-
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)


# ─── 模块4: 邮件通知 ───────────────────────────────────


def send_email(subject, body, recipients, config):
    """发送邮件"""
    email_cfg = config.get("email", {})
    if not email_cfg.get("sender") or not email_cfg.get("smtp_host"):
        print(f"[跳过邮件] 邮件未配置，收件人: {recipients}")
        return False

    msg = MIMEMultipart()
    msg["From"] = email_cfg["sender"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        server = smtplib.SMTP_SSL(email_cfg["smtp_host"], email_cfg["smtp_port"])
        server.login(email_cfg["sender"], email_cfg["password"])
        server.sendmail(email_cfg["sender"], recipients, msg.as_string())
        server.quit()
        print(f"[邮件已发送] {subject} → {recipients}")
        return True
    except Exception as e:
        print(f"[邮件错误] {e}")
        return False


def notify_new_terms(added_terms, source_file, config):
    """通知群2：新增术语"""
    group2 = config.get("stakeholders", {}).get("group2", [])
    if not group2 or not added_terms:
        return

    lines = [f"来源文件: {source_file}\n", "新增术语:\n"]
    for t in added_terms:
        lines.append(f"  - {t['name']}（{t['system']}）: {t['definition'][:80]}...")
    lines.append("\n请在 Obsidian 术语库中查看详情。")

    send_email(
        subject=f"[术语库] 新增 {len(added_terms)} 条术语",
        body="\n".join(lines),
        recipients=group2,
        config=config,
    )


def notify_pending_changes(pending_changes, config):
    """通知群1：有待审批的术语变更"""
    group1 = config.get("stakeholders", {}).get("group1", [])
    if not group1 or not pending_changes:
        return

    lines = ["以下术语口径发生变化，请回复本邮件，在内容中标注：\n"]
    lines.append("示例回复: \"同意 采购管理, 拒绝 订单中心\"\n")

    for change_id, change in pending_changes.items():
        lines.append(f"【{change['name']}】")
        lines.append(f"  原口径: {change['old_definition'][:100]}...")
        lines.append(f"  新口径: {change['definition'][:100]}...")
        lines.append("")

    lines.append("请逐条回复 同意 或 拒绝。")

    send_email(
        subject=f"[术语库-审批] {len(pending_changes)} 条术语口径变更待审批",
        body="\n".join(lines),
        recipients=group1,
        config=config,
    )


def notify_approved_changes(approved_names, config):
    """通知群2：术语口径已更新"""
    group2 = config.get("stakeholders", {}).get("group2", [])
    if not group2 or not approved_names:
        return

    body = f"以下术语口径已更新: {', '.join(approved_names)}\n\n请在 Obsidian 术语库中查看最新定义。"

    send_email(
        subject=f"[术语库] {len(approved_names)} 条术语口径已更新",
        body=body,
        recipients=group2,
        config=config,
    )


# ─── 模块5: 邮件审批解析 ────────────────────────────────


def check_email_replies(config, state):
    """检查群1的邮件回复，解析审批结果"""
    email_cfg = config.get("email", {})
    group1 = config.get("stakeholders", {}).get("group1", [])
    pending = state.get("pending_changes", {})

    if not email_cfg.get("sender") or not email_cfg.get("imap_host") or not pending:
        return

    print("[检查审批邮件回复...]")

    try:
        mail = imaplib.IMAP4_SSL(email_cfg["imap_host"], email_cfg.get("imap_port", 993))
        mail.login(email_cfg["sender"], email_cfg["password"])
        mail.select("INBOX")

        # 搜索最近7天来自群1的邮件
        _, msg_ids = mail.search(None, '(SINCE "{date}")'.format(
            date=datetime.now().strftime("%d-%b-%Y")
        ))

        approved, rejected = [], []

        for msg_id in msg_ids[0].split()[-20:]:  # 只看最近20封
            _, msg_data = mail.fetch(msg_id, "(RFC822)")
            msg = email_lib.message_from_bytes(msg_data[0][1])

            # 检查是否来自群1
            from_addr = msg.get("From", "")
            if not any(g.lower() in from_addr.lower() for g in group1):
                continue

            # 检查是否是回复审批邮件
            subject = msg.get("Subject", "")
            if "术语库-审批" not in subject and "Re:" not in subject:
                continue

            # 解析正文
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

            # 解析审批关键词
            for change_id, change in pending.items():
                name = change["name"]
                if name in body:
                    if re.search(r"同意|通过|确认|approve|yes", body, re.IGNORECASE):
                        approved.append(change_id)
                    elif re.search(r"拒绝|不同意|取消|reject|no", body, re.IGNORECASE):
                        rejected.append(change_id)

        mail.logout()

        # 执行审批结果
        for change_id in approved:
            change = pending.pop(change_id)
            write_term_file(
                change["name"], change["system"],
                change["definition"], change.get("source", "")
            )
            print(f"  [已更新] {change['name']}")

        for change_id in rejected:
            change = pending.pop(change_id)
            print(f"  [已拒绝] {change['name']}")

        if approved:
            notify_approved_changes(
                [pending.get(cid, {}).get("name", cid) for cid in approved],
                config
            )

    except Exception as e:
        print(f"[邮件读取错误] {e}")


# ─── 主流程 ─────────────────────────────────────────────


def run(config, state):
    """执行一次完整的自动化流程"""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*50}")
    print(f"术语库自动化 - {today}")
    print(f"{'='*50}")

    # 检查群1审批回复（处理上次的 pending）
    check_email_replies(config, state)

    # 扫描新文件
    new_files = scan_new_files(config, state)
    if not new_files:
        print("[完成] 没有新文件需要处理")
        state["last_run"] = today
        save_state(state)
        return

    print(f"\n发现 {len(new_files)} 个新文件")

    total_added, total_changed = 0, 0

    for file_path in new_files:
        print(f"\n--- 处理: {os.path.basename(file_path)} ---")
        source_name = os.path.basename(file_path)

        # 转录
        try:
            text = transcribe(file_path)
            print(f"  转录完成: {len(text)} 字")
        except Exception as e:
            print(f"  [转录失败] {e}")
            continue

        # 保存转录文本
        save_transcription(file_path, text)

        # AI 提取术语
        terms = extract_terms_ai(text, config)
        if not terms:
            print("  [跳过] 未提取到术语")
            archive_source(file_path, state)
            continue

        print(f"  提取到 {len(terms)} 条术语")

        # 变更检测
        existing = load_existing_terms()
        added, changed, unchanged = detect_changes(terms, existing)

        print(f"  新增: {len(added)}, 变更: {len(changed)}, 无变化: {len(unchanged)}")

        # 处理新增术语
        for term in added:
            write_term_file(term["name"], term["system"], term["definition"], source_name)
            print(f"  [新增] {term['name']}")
        total_added += len(added)

        # 处理变更术语 → 写入 pending
        for term in changed:
            change_id = f"{term['name']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            state["pending_changes"][change_id] = {
                "name": term["name"],
                "system": term["system"],
                "definition": term["definition"],
                "old_definition": term["old_definition"],
                "source": source_name,
                "date": today,
            }
            print(f"  [待审批] {term['name']}")
        total_changed += len(changed)

        # 归档源文件
        archive_source(file_path, state)

        # 通知群2新增术语
        notify_new_terms(added, source_name, config)

    # 通知群1待审批变更
    notify_pending_changes(state.get("pending_changes", {}), config)

    # 保存状态
    state["last_run"] = today
    save_state(state)

    # 自动推送到 GitHub
    if total_added > 0 or total_changed > 0:
        git_sync(added_count=total_added, changed_count=total_changed)

    print(f"\n{'='*50}")
    print(f"处理完成: 新增 {total_added} 条, 待审批 {total_changed} 条")
    print(f"{'='*50}\n")


# ─── Git 同步 ──────────────────────────────────────────


def git_sync(added_count=0, changed_count=0):
    """自动 commit + push 到 GitHub"""
    try:
        repo_dir = str(BASE_DIR)

        # 检查是否有远程仓库
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=repo_dir
        )
        if result.returncode != 0:
            print("[Git] 未配置远程仓库，跳过推送")
            return

        # git add
        subprocess.run(["git", "add", "terms/", "src/"], cwd=repo_dir, check=True)

        # 检查是否有变更
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=repo_dir
        )
        if result.returncode == 0:
            print("[Git] 没有需要提交的变更")
            return

        # git commit
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"auto: {date_str} 新增{added_count}条"
        if changed_count > 0:
            msg += f", 待审批变更{changed_count}条"
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo_dir, check=True
        )

        # git push
        subprocess.run(
            ["git", "push", "origin", "HEAD"],
            cwd=repo_dir, check=True
        )
        print(f"[Git] 已推送到 GitHub: {msg}")

    except subprocess.CalledProcessError as e:
        print(f"[Git 错误] {e}")
    except Exception as e:
        print(f"[Git 错误] {e}")


# ─── 定时任务管理 ───────────────────────────────────────


def install_task(config):
    """注册 Windows 定时任务"""
    schedule_time = config.get("schedule_time", "09:00")
    hour, minute = schedule_time.split(":")

    python_exe = sys.executable
    script_path = Path(__file__).resolve()

    cmd = (
        f'schtasks /create /tn "TermBase_AutoRun" /tr '
        f'"\\"{python_exe}\\" \\"{script_path}\\" --now" '
        f'/sc daily /st {hour}:{minute} /f'
    )

    print(f"注册定时任务: 每天 {schedule_time}")
    print(f"命令: {cmd}")

    os.system(cmd)
    print("注册完成。可在 Windows 任务计划程序中查看。")


def uninstall_task():
    """移除定时任务"""
    os.system('schtasks /delete /tn "TermBase_AutoRun" /f')
    print("定时任务已移除。")


# ─── 入口 ───────────────────────────────────────────────

if __name__ == "__main__":
    config = load_config()
    state = load_state()

    if "--install" in sys.argv:
        install_task(config)
    elif "--uninstall" in sys.argv:
        uninstall_task()
    elif "--now" in sys.argv:
        run(config, state)
    else:
        print(__doc__)
