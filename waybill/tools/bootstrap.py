#!/usr/bin/env python
"""从 PyPI 直接取 wheel 并解压到目标目录。

这个环境里 pip 在临时目录里创建文件会被拒（Permission denied），
所以不用 pip：直接读 PyPI 的 JSON API，挑平台匹配的 wheel，zipfile 解压。

用法：
    python tools/bootstrap.py --target .deps jinja2
    python tools/bootstrap.py --target .deps fastapi uvicorn python-multipart
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

PY = f"{sys.version_info.major}{sys.version_info.minor}"
PLAT = "win_amd64" if sys.platform == "win32" else ("macosx" if sys.platform == "darwin" else "manylinux")


def _score(filename: str) -> int:
    """给 wheel 打分：越高越优先。只接受能在当前解释器上跑的。"""
    if not filename.endswith(".whl"):
        return -1
    stem = filename[:-4]
    parts = stem.split("-")
    if len(parts) < 5:
        return -1
    pytag, abitag, plat = parts[-3], parts[-2], parts[-1]
    if plat == "any":
        if pytag in ("py3", "py2.py3"):
            return 100
        return -1
    if PLAT not in plat:
        return -1
    if f"cp{PY}" in pytag and abitag in (f"cp{PY}", "abi3", "none"):
        return 90
    if pytag in ("py3", "py2.py3"):
        return 80
    return -1


def resolve(name: str) -> dict:
    url = f"https://pypi.org/pypi/{name}/json"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def pick_wheel(meta: dict) -> tuple[str, str] | None:
    version = meta["info"]["version"]
    best, best_score = None, -1
    for f in meta["releases"].get(version, []):
        if f.get("yanked"):
            continue
        s = _score(f["filename"])
        if s > best_score:
            best, best_score = f, s
    if best is None:
        return None
    return best["url"], best["filename"]


def marker_ok(marker: str) -> bool:
    """只处理常见的环境 marker；判断不了的按“需要”处理，宁可多装。"""
    if not marker:
        return True
    m = marker.strip()
    if "extra" in m:
        return False
    if "win32" in m or "Windows" in m:
        return sys.platform == "win32"
    if "darwin" in m:
        return sys.platform == "darwin"
    if "linux" in m:
        return sys.platform.startswith("linux")
    py = m.startswith("python_version")
    if py:
        found = re.search(r'python_version\s*(>=|<=|==|!=|>|<)\s*"([\d.]+)"', m)
        if found:
            op, ver = found.groups()
            cur = tuple(int(x) for x in f"{sys.version_info.major}.{sys.version_info.minor}".split("."))
            want = tuple(int(x) for x in ver.split(".")[:2])
            return {
                ">=": cur >= want, "<=": cur <= want, "==": cur == want,
                "!=": cur != want, ">": cur > want, "<": cur < want,
            }[op]
    return True


def requirements(meta: dict) -> list[str]:
    out = []
    for line in meta["info"].get("requires_dist") or []:
        spec, _, marker = line.partition(";")
        if not marker_ok(marker):
            continue
        name = re.split(r"[\s\[<>=!~;(]", spec.strip(), maxsplit=1)[0]
        if name:
            out.append(name)
    return out


def install(name: str, target: str, seen: set[str], depth: int = 0) -> None:
    key = name.lower().replace("_", "-")
    if key in seen:
        return
    seen.add(key)

    meta = resolve(name)
    picked = pick_wheel(meta)
    if not picked:
        print(f"  !! {name}: 没有可用的 wheel（可能需要源码构建），跳过")
        return
    url, filename = picked
    with urllib.request.urlopen(url, timeout=120) as r:
        data = r.read()
    zipfile.ZipFile(io.BytesIO(data)).extractall(target)
    print(f"  {'  ' * depth}+ {filename} ({len(data) // 1024} KB)")

    for dep in requirements(meta):
        install(dep, target, seen, depth + 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=".deps")
    ap.add_argument("packages", nargs="+")
    args = ap.parse_args()

    target = os.path.abspath(args.target)
    os.makedirs(target, exist_ok=True)
    seen: set[str] = set()
    for pkg in args.packages:
        print(f"installing {pkg}")
        install(pkg, target, seen)
    print(f"done -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
