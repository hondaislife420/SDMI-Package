#!/usr/bin/env python3
"""Buffers from a folder → Blender OBJs (split parts + flipped UVs).

Usage:
  python 1_dump_to_blender.py                  # look next to this script
  python 1_dump_to_blender.py C:\\path\\to\\bufs  # look in that folder

Required files in the folder:
  rest_pos.buf          (16060 * 12 bytes)
  verna_ib.buf          (or ib.buf)
  body_uv.buf           (16060 * 8 bytes)
                        also accepts: body_vs_t3_uv_6e8f6198.buf / body_vs_t3_uv*.buf

Optional (for MTL preview; searched in same folder):
  hair_diffuse.dds
  body_diffuse.dds
  skin_diffuse.dds
  face_diffuse.dds

Creates next to this script (UVs always V-flipped for Blender):
  verna_body_materials.obj   ← import this (split objects)
  verna_body_dumporder.obj   ← one mesh 16060 verts
  verna_body_materials.mtl
  parts\\HairA.obj … Body.obj + .idx

Use --out DIR to write outputs elsewhere.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERT_COUNT = 16060
REST_BYTES = VERT_COUNT * 12
UV_BYTES = VERT_COUNT * 8

# (name, first_index, index_count, diffuse_dds or None)
PARTS = [
    ("HairA", 0, 15168, "hair_diffuse.dds"),
    ("HairB", 15168, 4410, "hair_diffuse.dds"),
    ("Legs", 19578, 1722, "body_diffuse.dds"),
    ("Skin", 21300, 5403, "skin_diffuse.dds"),
    ("Fringe", 26703, 942, "body_diffuse.dds"),
    ("Neck", 27645, 900, "face_diffuse.dds"),
    ("Body", 28545, 37110, "body_diffuse.dds"),
]


def find_file(folder: Path, *names: str) -> Path | None:
    for n in names:
        p = folder / n
        if p.is_file():
            return p
    for n in names:
        if "*" in n:
            hits = sorted(folder.glob(n))
            if hits:
                return hits[0]
    return None


def require_inputs(folder: Path) -> tuple[Path, Path, Path]:
    rest = find_file(folder, "Rest-cs-t3=d9248384-cs=0d516b116c85c323.buf")
    ib = find_file(folder, "Index-ib=e33d5bc8.buf")
    uv = find_file(folder, "TexCoord-vs-t3=6e8f6198.buf")
    missing = []
    if rest is None:
        missing.append("rest_pos.buf")
    if ib is None:
        missing.append("verna_ib.buf  (or ib.buf)")
    if uv is None:
        missing.append("body_uv.buf  (or body_vs_t3_uv_6e8f6198.buf)")
    if missing:
        raise SystemExit(
            "Missing files in folder:\n  - "
            + "\n  - ".join(missing)
            + f"\n\nLooked in:\n  {folder}"
        )
    assert rest and ib and uv
    return rest, ib, uv


def load_rest(path: Path):
    data = path.read_bytes()
    if len(data) != REST_BYTES:
        raise SystemExit(f"{path.name}: size {len(data)} != {REST_BYTES}")
    return [struct.unpack_from("<3f", data, i * 12) for i in range(VERT_COUNT)]


def load_uv(path: Path, flip_v: bool):
    data = path.read_bytes()
    if len(data) != UV_BYTES:
        raise SystemExit(f"{path.name}: size {len(data)} != {UV_BYTES}")
    uvs = []
    for i in range(VERT_COUNT):
        u, v, _z, _w = struct.unpack_from("<4e", data, i * 8)
        if flip_v:
            v = 1.0 - float(v)
        uvs.append((float(u), float(v)))
    return uvs


def load_ib(path: Path) -> list[int]:
    data = path.read_bytes()
    n = len(data) // 2
    return list(struct.unpack("<" + "H" * n, data))


def write_mtl(path: Path, tex_folder: Path) -> None:
    lines = ["# materials (DDS must sit next to this .mtl)\n"]
    seen = set()
    for name, _f, _c, dds in PARTS:
        mat = f"mat_{name}"
        if mat in seen:
            continue
        seen.add(mat)
        lines.append(f"newmtl {mat}\nKd 1 1 1\n")
        if dds and (tex_folder / dds).is_file():
            lines.append(f"map_Kd {dds}\n")
        lines.append("\n")
    path.write_text("".join(lines), encoding="utf-8")


def write_multi_obj(path: Path, mtl_name: str, verts, uvs, ib: list[int]) -> None:
    """Separate objects; face indices are global across the file."""
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# split parts + flipped UV\n")
        f.write(f"mtllib {mtl_name}\n")
        vbase = 1
        for name, first, count, _dds in PARTS:
            used: list[int] = []
            seen: dict[int, int] = {}
            faces: list[tuple[int, int, int]] = []
            end = first + count
            for t in range(first, min(end, len(ib) - 2), 3):
                tri = (ib[t], ib[t + 1], ib[t + 2])
                if tri[0] == tri[1] or tri[1] == tri[2] or tri[0] == tri[2]:
                    continue
                loc = []
                for g in tri:
                    if g not in seen:
                        seen[g] = len(used)
                        used.append(g)
                    loc.append(seen[g])
                faces.append((loc[0], loc[1], loc[2]))
            f.write(f"o {name}\n")
            f.write(f"usemtl mat_{name}\n")
            for g in used:
                x, y, z = verts[g]
                f.write(f"v {x:.9g} {y:.9g} {z:.9g}\n")
            for g in used:
                u, v = uvs[g]
                f.write(f"vt {u:.9g} {v:.9g}\n")
            for a, b, c in faces:
                fa, fb, fc = vbase + a, vbase + b, vbase + c
                f.write(f"f {fa}/{fa} {fb}/{fb} {fc}/{fc}\n")
            vbase += len(used)


def write_dumporder_obj(path: Path, mtl_name: str, verts, uvs, ib: list[int]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# one object, 16060 dump-order verts\n")
        f.write(f"mtllib {mtl_name}\n")
        f.write("o VernaBodyAll\n")
        for x, y, z in verts:
            f.write(f"v {x:.9g} {y:.9g} {z:.9g}\n")
        for u, v in uvs:
            f.write(f"vt {u:.9g} {v:.9g}\n")
        for name, first, count, _dds in PARTS:
            f.write(f"usemtl mat_{name}\n")
            end = first + count
            for t in range(first, min(end, len(ib) - 2), 3):
                a, b, c = ib[t] + 1, ib[t + 1] + 1, ib[t + 2] + 1
                if a == b or b == c or a == c:
                    continue
                f.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")


def write_part(path: Path, idx_path: Path, name, verts, uvs, ib, first, count) -> int:
    used: list[int] = []
    seen: dict[int, int] = {}
    faces: list[tuple[int, int, int]] = []
    end = first + count
    for t in range(first, min(end, len(ib) - 2), 3):
        tri = (ib[t], ib[t + 1], ib[t + 2])
        if tri[0] == tri[1] or tri[1] == tri[2] or tri[0] == tri[2]:
            continue
        loc = []
        for g in tri:
            if g not in seen:
                seen[g] = len(used)
                used.append(g)
            loc.append(seen[g] + 1)
        faces.append((loc[0], loc[1], loc[2]))
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"o {name}\n")
        for g in used:
            x, y, z = verts[g]
            f.write(f"v {x:.9g} {y:.9g} {z:.9g}\n")
        for g in used:
            u, v = uvs[g]
            f.write(f"vt {u:.9g} {v:.9g}\n")
        for a, b, c in faces:
            f.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")
    idx_path.write_text("\n".join(str(g) for g in used) + "\n", encoding="utf-8")
    return len(used)


def main() -> int:
    pkg = Path(__file__).resolve().parents[1]
    mesh = pkg / "Meshes" / "_free_n_backup"
    
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "folder",
        type=Path,
        nargs="?",
        default=mesh,
        help="folder containing rest_pos.buf / ib / uv (default: next to this script)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output folder for OBJs/MTL/parts (default: next to this script)",
    )
    args = ap.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"not a folder: {folder}")

    out_dir =  pkg / "Objects"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Scanning {folder}")
    rest_p, ib_p, uv_p = require_inputs(folder)
    print(f"rest: {rest_p.name}")
    print(f"ib:   {ib_p.name}")
    print(f"uv:   {uv_p.name}")
    print(f"out:  {out_dir}")

    verts = load_rest(rest_p)
    uvs = load_uv(uv_p, flip_v=True)
    ib = load_ib(ib_p)

    mtl_name = "verna_body_materials.mtl"
    write_mtl(out_dir / mtl_name, folder)
    # Always flip-v (only orientation that works in Blender)
    write_multi_obj(out_dir / "verna_body_materials.obj", mtl_name, verts, uvs, ib)
    write_dumporder_obj(out_dir / "verna_body_dumporder.obj", mtl_name, verts, uvs, ib)

    parts_dir = out_dir / "parts"
    parts_dir.mkdir(exist_ok=True)
    for name, first, count, dds in PARTS:
        n = write_part(
            parts_dir / f"{name}.obj",
            parts_dir / f"{name}.idx",
            name,
            verts,
            uvs,
            ib,
            first,
            count,
        )
        print(f"  part {name}: {n} verts  tex={dds}")

    # Remove old dual-named files if present
    for stale in (
        "verna_body_materials_flipv.obj",
        "verna_body_dumporder_flipv.obj",
        "verna_body_materials_flipv.mtl",
    ):
        p = out_dir / stale
        if p.is_file():
            p.unlink()
            print(f"  removed old {stale}")

    print()
    print("=== DONE — import in Blender (UVs already flipped) ===")
    print(f"  {out_dir / 'verna_body_materials.obj'}")
    print(f"  or single part: {parts_dir / 'Body.obj'}")
    print()
    print("Then:  python 2_blender_to_mod.py --parts")
    print("   or: python 2_blender_to_mod.py your_export.obj")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
