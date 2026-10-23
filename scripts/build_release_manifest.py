"""List only release-owned code/docs; never include runtime data or credentials."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = 'office-release.json'
ROOT_FILES = ['.gitattributes', '.gitignore', 'README.md', 'requirements.txt', 'install-office.bat', 'start-office.bat', 'update-office.bat', 'streamlit_app.py']
DIRECTORIES = ['.github', '.streamlit', 'office', 'scripts', 'site', 'docs']
EXTENSIONS = {'.py', '.bat', '.html', '.css', '.js', '.cjs', '.json', '.toml', '.txt', '.md', '.yml', '.yaml', '.svg'}


def manifest(root=ROOT):
    paths = set(ROOT_FILES)
    for directory in DIRECTORIES:
        for path in (root / directory).rglob('*'):
            if path.is_file() and not path.is_symlink() and path.suffix in EXTENSIONS:
                relative = path.relative_to(root)
                if '__pycache__' not in relative.parts and path.name != 'secrets.toml':
                    paths.add(relative.as_posix())
    paths.discard('site/data/tasks.json')  # Public runtime records change independently.
    return {'format':1, 'version':'0.19', 'files':{name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in sorted(paths)}}


if __name__ == '__main__':
    result = manifest()
    if '--check' in sys.argv:
        assert json.loads((ROOT/NAME).read_text(encoding='utf-8')) == result, 'Run python scripts/build_release_manifest.py before committing code/docs'
        print('Release manifest verified')
    else:
        (ROOT/NAME).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print('Release manifest written')
