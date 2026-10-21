from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
html = (root / "site/index.html").read_text()
for target in re.findall(r'(?:src|href)="([^"]+)"', html):
    if target.startswith(("http:", "https:", "#")):
        continue
    assert (root / "site" / target.split("?", 1)[0]).is_file(), target
for name in ["COMPANY", "ROLES", "ARCHITECTURE", "DECISIONS", "ROADMAP", "WORKLOG"]:
    assert (root / "docs" / (name + ".md")).is_file()
assert "API 설정 전에는 AI가 실행되지 않습니다" in html
print("Static office links and documentation verified")
