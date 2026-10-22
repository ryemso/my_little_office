"""Verify declared deliverables from disk, independently of employee prose."""
import hashlib
from office.workspaces import target


def inspect_artifacts(work,expected):
    results=[]
    for name in expected:
        path=target(work,name)
        present=path.is_file() and path.stat().st_size>0
        results.append({'path':name,'present':present,'bytes':path.stat().st_size if present else 0,
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest() if present else None})
    return results
