#!/usr/bin/env python3
"""Validate Free-N package: buffers, jobs, Index, and mod.ini if/ic/vert_count."""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

MAX_N = 16384
PARTS = [
    "hair_a",
    "hair_b",
    "legs",
    "skin",
    "fringe",
    "neck",
    "body",
]


def parse_ini_globals(ini: Path) -> dict[str, str]:
    text = ini.read_text(encoding="utf-8", errors="replace")
    out: dict[str, str] = {}
    for m in re.finditer(
        r"global\s+\$([A-Za-z0-9_]+)\s*=\s*([^\r\n;]+)", text
    ):
        out[m.group(1)] = m.group(2).strip()
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "folder", type=Path, nargs="?", default=Path(__file__).resolve().parents[1]
    )
    p.add_argument("--n", type=int, default=0)
    p.add_argument(
        "--body-only",
        action="store_true",
        help="Require non-body ic_*=0 and Body job covers all verts",
    )
    args = p.parse_args()
    root = args.folder.resolve()
    meshes = root / "Meshes"
    errors: list[str] = []
    warns: list[str] = []

    n = args.n
    meta_path = root / "META.json"
    if not n and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            n = int(meta.get("vert_count") or 0)
        except Exception:
            pass
    if not n:
        rest = meshes / "rest.buf"
        if rest.is_file() and rest.stat().st_size % 12 == 0:
            n = rest.stat().st_size // 12
    if not n:
        raise SystemExit("pass --n or set META vert_count / rest.buf")

    print(f"Validating free-N package N={n} at {root}")

    def need(path: Path, size: int) -> None:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(root)}")
            return
        got = path.stat().st_size
        if got != size:
            errors.append(f"{path.name}: {got} != {size}")
        else:
            print(f"  OK {path.relative_to(root)} ({got})")

    if n > MAX_N:
        errors.append(f"N {n} > MAX {MAX_N}")

    need(meshes / "rest.buf", n * 12)
    need(meshes / "weights.buf", n * 8)
    need(meshes / "tans.buf", n * 8)
    need(meshes / "TexCoord.buf", n * 8)

    ib_count = 0
    ib = meshes / "Index.buf"
    if not ib.is_file():
        errors.append("missing Index.buf")
    else:
        raw = ib.read_bytes()
        if len(raw) % 2:
            errors.append("Index.buf odd size")
        else:
            ib_count = len(raw) // 2
            if ib_count:
                mx = max(struct.unpack_from(f"<{ib_count}H", raw))
                if mx >= n:
                    errors.append(f"Index max {mx} >= N {n}")
                else:
                    print(f"  OK Index.buf {ib_count} indices max={mx}")
            else:
                warns.append("empty Index.buf")

    body_job_count = 0
    total_job_verts = 0
    jp = meshes / "Bones.params"
    if not jp.is_file() or jp.stat().st_size != 16:
        errors.append(f"bad {jp.name}")
    base, count, wbase, _ = struct.unpack("<4I", jp.read_bytes())
    total_job_verts += count
    body_job_count = count
    if count and base + count > n:
        errors.append(f"Bones: base+count {base}+{count} > N {n}")
    else:
        print(f"  OK Bones: base={base} count={count} wbase={wbase}")

    # mod.ini cross-check
    ini = root / "mod.ini"
    if not ini.is_file():
        errors.append("missing mod.ini")
    else:
        g = parse_ini_globals(ini)

        # draw table
        for part in PARTS:
            if_k = f"verna_if_{part}"
            ic_k = f"verna_ic_{part}"
            if if_k not in g or ic_k not in g:
                warns.append(f"mod.ini missing ${if_k} or ${ic_k}")
                continue
            try:
                if_v = int(float(g[if_k]))
                ic_v = int(float(g[ic_k]))
            except ValueError:
                errors.append(f"bad {if_k}/{ic_k}")
                continue
            if ic_v < 0 or if_v < 0:
                errors.append(f"{part}: negative if/ic")
            if ic_v and if_v + ic_v > ib_count:
                errors.append(
                    f"{part}: if+ic {if_v}+{ic_v} > Index count {ib_count}"
                )
            if ic_v % 3 != 0 and ic_v != 0:
                warns.append(f"{part}: ic={ic_v} not multiple of 3")

        # body-only convention
        try:
            ic_body = int(float(g.get("verna_ic_body", "0")))
            if_body = int(float(g.get("verna_if_body", "0")))
        except ValueError:
            ic_body, if_body = 0, 0

        others_ic = 0
        for part in PARTS:
            if part == "body":
                continue
            try:
                others_ic += int(float(g.get(f"verna_ic_{part}", "0")))
            except ValueError:
                pass

        body_only = args.body_only or (others_ic == 0 and ic_body > 0)
        if body_only:
            print("  mode: body-only draw table")
            if others_ic != 0:
                errors.append("body-only expected but other ic_* non-zero")
            if ic_body != ib_count:
                errors.append(
                    f"body-only: ic_body {ic_body} != Index count {ib_count}"
                )
            else:
                print(f"  OK ic_body == Index count ({ic_body})")
            if if_body != 0:
                warns.append(f"body-only usually if_body=0 (got {if_body})")
            if body_job_count and body_job_count != n:
                warns.append(
                    f"Body job count {body_job_count} != N {n} "
                    "(Param MultiJob may under-skin)"
                )
            elif body_job_count == n:
                print(f"  OK Body job covers all {n} verts")

    if warns:
        print("WARN:")
        for w in warns:
            print(" ", w)
    if errors:
        print("FAIL:")
        for e in errors:
            print(" ", e)
        return 1
    print("PASS free-N package")
    return 0


if __name__ == "__main__":
    sys.exit(main())
