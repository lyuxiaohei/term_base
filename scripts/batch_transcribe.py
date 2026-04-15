"""批量转录脚本 - 模型只加载一次"""
import os
import glob
from faster_whisper import WhisperModel

PENDING_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "pending")
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "processed")

os.makedirs(PROCESSED_DIR, exist_ok=True)

files = sorted(glob.glob(os.path.join(PENDING_DIR, "*.mp3")), key=os.path.getsize)
print(f"待转录文件: {len(files)} 个")

print("Loading model...")
model = WhisperModel("base", device="cpu", compute_type="int8")

for i, fp in enumerate(files, 1):
    basename = os.path.basename(fp)
    txt_name = os.path.splitext(basename)[0] + ".txt"
    txt_path = os.path.join(PENDING_DIR, txt_name)

    if os.path.exists(txt_path):
        print(f"[{i}/{len(files)}] 跳过(已转录): {basename}")
        continue

    print(f"[{i}/{len(files)}] 转录: {basename}")
    try:
        segments, info = model.transcribe(fp, language="zh", beam_size=5, vad_filter=True)
        text = "".join(seg.text for seg in segments)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  完成: {len(text)} 字")
    except Exception as e:
        print(f"  失败: {e}")

print("全部转录完成!")
