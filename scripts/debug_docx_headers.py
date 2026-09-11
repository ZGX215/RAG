"""查看 DOCX 所有分块的标题和内容预览"""
import os, sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

DOCX_DIR = Path(r'E:\workbuddy\8.16\题7')
docx_files = [f for f in os.listdir(str(DOCX_DIR)) if f.endswith('.docx') and '人工智能' in f and not f.startswith('~$')]
DOCX_FILE = DOCX_DIR / docx_files[0] if docx_files else None

from app.ingest.word_reader import WordReader
reader = WordReader()
chunks = reader.read(DOCX_FILE, doc_name="人工智能+行动意见")

print(f"总分块: {len(chunks)}")
print()
for i, c in enumerate(chunks):
    heading = c.meta.heading_number or "(无标题)"
    level = c.meta.heading_level
    preview = c.content[:100].replace("\n", " ").strip()
    indent = "  " * (level - 1)
    print(f"  [{i+1:>2}] {indent}[L{level}] {heading}")
    print(f"       {preview}...")
    print()