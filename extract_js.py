"""Extract real files from folder_collection.md sections into js/."""
import re
from pathlib import Path

ROOT = Path(__file__).parent
text = (ROOT / "folder_collection.md").read_text(encoding="utf-8")

# Sections look like: ### filename\n\n``` lang\n<content>\n```  (line-based)
pattern = re.compile(r"^### (\S+)\s*$\n\n``` \w+\n(.*?)\n```", re.M | re.S)
out = ROOT / "js"
out.mkdir(exist_ok=True)
for name, content in pattern.findall(text):
    (out / name).write_text(content, encoding="utf-8")
    print(f"{name}: {len(content)} bytes")
