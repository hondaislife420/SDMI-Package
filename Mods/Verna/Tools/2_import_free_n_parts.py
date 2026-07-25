#!/usr/bin/env python3
"""WWMI-style multi-part Free-N import.

  python import_free_n_parts.py C:\\path\\to\\folder_with_part_objs

Runs pack_free_n_parts → weight transfer → smooth → tans → validate.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(args: list[str], cwd: Path) -> None:
    print(">", " ".join(args))
    r = subprocess.run([sys.executable, *args], cwd=cwd)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def main() -> int:
    tools = Path(__file__).resolve().parent
    pkg = tools.parent
    bak = pkg / "Meshes" / "_free_n_backup"

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--skip-weights", action="store_true")
    args = ap.parse_args()
    folder = args.folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"not a folder: {folder}")

    run([str(tools / "pack_free_n_parts.py"), str(folder), "--write-ini"], tools)

    if not args.skip_weights:
        sr, sw = bak / "Rest-cs-t3=d9248384-cs=0d516b116c85c323.buf", bak / "Weights-cs-t1=9bff6d41-cs=0d516b116c85c323.buf"
        if sr.is_file() and sw.is_file():
            run(
                [
                    str(tools / "transfer_weights_nn.py"),
                    "--stock-rest",
                    str(sr),
                    "--stock-weights",
                    str(sw),
                    "--free-rest",
                    str(pkg / "Meshes" / "rest.buf"),
                    "--k",
                    "5",
                ],
                tools,
            )
            run([str(tools / "smooth_weights.py"), "--passes", "4"], tools)
        else:
            print("WARN: no stock backup for NN weights")

    run([str(tools / "rebuild_tans.py")], tools)
    run([str(tools / "validate_free_n.py"), str(pkg)], tools)
    print()
    print("DONE multi-part Free-N. F10")
    print("Textures: Textures/free_n/body_*.dds  hair_*.dds  skin_*.dds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
