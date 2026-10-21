from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
html = (root / "site/index.html").read_text()
for target in re.findall(r'(?:src|href)="([^"]+)"', html):
    if target.startswith(("http:", "https:", "#")):
        continue
    assert (root / "site" / target).is_file(), target
for name in ["COMPANY", "ROLES", "ARCHITECTURE", "DECISIONS", "ROADMAP", "WORKLOG"]:
    assert (root / "docs" / (name + ".md")).is_file()
assert "실행 서버 미연결" in html
print("Static office links and documentation verified")
