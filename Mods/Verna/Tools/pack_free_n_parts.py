#!/usr/bin/env python3
"""Pack separate part OBJs into Free-N multi-part package (WWMI-style draws).

  python pack_free_n_parts.py C:\\path\\to\\parts_folder
  python import_free_n_parts.py C:\\parts   (pack + weights + tans + validate)

Part file names (any of):
  HairA / Hair1 / Velina_Hair1
  HairB / Hair2
  Legs
  Skin (optional)
  Fringe / HairShadow
  Neck (optional)
  Body / Velina_Body1
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path

MAX_N = 16384
PART_ORDER = ["HairA", "HairB", "Legs", "Skin", "Fringe", "Neck", "Body"]

ALIASES = {
    "haira": "HairA",
    "hair_a": "HairA",
    "hair1": "HairA",
    "velina_hair1": "HairA",
    "hairb": "HairB",
    "hair_b": "HairB",
    "hair2": "HairB",
    "velina_hair2": "HairB",
    "legs": "Legs",
    "velina_legs": "Legs",
    "skin": "Skin",
    "fringe": "Fringe",
    "other": "Fringe",
    "neck": "Neck",
    "body": "Body",
    "body1": "Body",
    "velina_body1": "Body",
}


def f32_to_f16_bits(x: float) -> int:
    f = struct.pack("<f", float(x))
    b = struct.unpack("<I", f)[0]
    sign = (b >> 16) & 0x8000
    exp = (b >> 23) & 0xFF
    mant = b & 0x7FFFFF
    if exp == 255:
        return sign | 0x7C00 | (mant >> 13)
    if exp > 142:
        return sign | 0x7C00
    if exp < 113:
        if exp < 103:
            return sign
        shift = 113 - exp
        mant = (mant | 0x800000) >> shift
        return sign | (mant >> 13)
    return sign | ((exp - 112) << 10) | (mant >> 13)


def parse_obj(path: Path):
    verts: list[tuple[float, float, float]] = []
    vts: list[tuple[float, float]] = []
    vert_uv: dict[int, tuple[float, float]] = {}
    faces: list[tuple[int, int, int]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("vt "):
                p = line.split()
                vts.append((float(p[1]), float(p[2])))
            elif line.startswith("f "):
                corners: list[int] = []
                for part in line.split()[1:]:
                    bits = part.split("/")
                    vi = int(bits[0])
                    vi = len(verts) + vi if vi < 0 else vi - 1
                    corners.append(vi)
                    if len(bits) > 1 and bits[1]:
                        ti = int(bits[1])
                        ti = len(vts) + ti if ti < 0 else ti - 1
                        if 0 <= ti < len(vts):
                            vert_uv[vi] = vts[ti]
                for i in range(1, len(corners) - 1):
                    faces.append((corners[0], corners[i], corners[i + 1]))
    uvs = [
        vert_uv.get(i, vts[i] if i < len(vts) else (0.0, 0.0)) for i in range(len(verts))
    ]
    return verts, uvs, faces


def resolve_parts(folder: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() != ".obj":
            continue
        key = re.sub(r"[^a-z0-9]+", "_", p.stem.lower()).strip("_")
        canon = ALIASES.get(key)
        if not canon:
            for alias, name in ALIASES.items():
                if key == alias or key.endswith("_" + alias) or key.startswith(alias + "_"):
                    canon = name
                    break
        if not canon:
            print(f"  skip unknown: {p.name}")
            continue
        if canon in found:
            print(f"  skip duplicate {canon}: {p.name}")
            continue
        found[canon] = p
        print(f"  {canon} <- {p.name}")
    return found


def write_job(path: Path, base: int, count: int) -> None:
    path.write_bytes(struct.pack("<4I", base, count, base * 2, 0))


def set_ini_globals(ini_path: Path, values: dict[str, str]) -> None:
    text = ini_path.read_text(encoding="utf-8", errors="replace")
    for name, val in values.items():
        pat = rf"(global \${re.escape(name)}\s*=\s*)[^\r\n]+"
        text, n = re.subn(pat, rf"\g<1>{val}", text, count=1)
        if not n:
            print(f"  WARN: could not set ${name}")
    ini_path.write_text(text, encoding="utf-8")
    print(f"patched {ini_path}")


def main() -> int:
    pkg = Path(__file__).resolve().parents[1]
    meshes = pkg / "Meshes"

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--write-ini", action="store_true", default=True)
    ap.add_argument("--no-write-ini", dest="write_ini", action="store_false")
    ap.add_argument("--two-sided", action="store_true", default=True)
    ap.add_argument("--one-sided", dest="two_sided", action="store_false")
    ap.add_argument("--undo-flip-v", action="store_true", default=True)
    args = ap.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        raise SystemExit(f"not a folder: {folder}")

    print(f"Scanning {folder}")
    part_files = resolve_parts(folder)
    if not part_files:
        raise SystemExit("no recognized part OBJs")

    all_verts: list[tuple[float, float, float]] = []
    all_uvs: list[tuple[float, float]] = []
    part_tris: dict[str, list[tuple[int, int, int]]] = {n: [] for n in PART_ORDER}

    for name in PART_ORDER:
        path = part_files.get(name)
        if not path:
            continue
        verts, uvs, faces = parse_obj(path)
        if not verts or not faces:
            print(f"  warn empty {name}")
            continue
        base = len(all_verts)
        all_verts.extend(verts)
        all_uvs.extend(uvs)
        part_tris[name] = [(base + a, base + b, base + c) for a, b, c in faces]
        print(f"  loaded {name}: {len(verts)} verts, {len(faces)} tris")

    n = len(all_verts)
    if n < 1 or n > MAX_N:
        raise SystemExit(f"N={n} out of range 1..{MAX_N}")

    ib = bytearray()
    draw: dict[str, tuple[int, int]] = {}
    for name in PART_ORDER:
        tris = part_tris[name]
        if not tris:
            draw[name] = (0, 0)
            continue
        ifirst = len(ib) // 2
        for a, b, c in tris:
            ib += struct.pack("<HHH", a, b, c)
            if args.two_sided:
                ib += struct.pack("<HHH", a, c, b)
        ic = len(ib) // 2 - ifirst
        draw[name] = (ifirst, ic)
        print(f"  draw {name}: if={ifirst} ic={ic}")

    meshes.mkdir(parents=True, exist_ok=True)

    (meshes / "rest.buf").write_bytes(b"".join(struct.pack("<3f", *v) for v in all_verts))
    (meshes / "weights.buf").write_bytes(b"".join(struct.pack("<II", 0, 255) for _ in range(n)))
    (meshes / "tans.buf").write_bytes(b"\x00" * (n * 8))

    uv_blob = bytearray()
    for u, v in all_uvs:
        if args.undo_flip_v:
            v = 1.0 - v
        uv_blob += struct.pack("<HH", f32_to_f16_bits(u), f32_to_f16_bits(v))
        uv_blob += struct.pack("<HH", 0, 0)
    (meshes / "TexCoord.buf").write_bytes(bytes(uv_blob))
    (meshes / "Index.buf").write_bytes(bytes(ib))
    print(f"wrote rest N={n}, Index indices={len(ib) // 2}")

    write_job(meshes / "Bones.params", 0, n)

    ini_vals = {
        "verna_if_hair_a": str(draw["HairA"][0]),
        "verna_ic_hair_a": str(draw["HairA"][1]),
        "verna_if_hair_b": str(draw["HairB"][0]),
        "verna_ic_hair_b": str(draw["HairB"][1]),
        "verna_if_legs": str(draw["Legs"][0]),
        "verna_ic_legs": str(draw["Legs"][1]),
        "verna_if_skin": str(draw["Skin"][0]),
        "verna_ic_skin": str(draw["Skin"][1]),
        "verna_if_fringe": str(draw["Fringe"][0]),
        "verna_ic_fringe": str(draw["Fringe"][1]),
        "verna_if_neck": str(draw["Neck"][0]),
        "verna_ic_neck": str(draw["Neck"][1]),
        "verna_if_body": str(draw["Body"][0]),
        "verna_ic_body": str(draw["Body"][1]),
    }
    print("=== draw table ===")
    for k, v in ini_vals.items():
        print(f"  ${k} = {v}")

    if args.write_ini:
        set_ini_globals(pkg / "mod.ini", ini_vals)

    meta_path = pkg / "META.json"
    if meta_path.is_file():
        try:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            m["vert_count"] = n
            m["free_n_multipart"] = True
            m["parts"] = {
                k: {"first_index": draw[k][0], "index_count": draw[k][1]} for k in PART_ORDER
            }
            meta_path.write_text(json.dumps(m, indent=2), encoding="utf-8")
        except Exception:
            pass

    print()
    print("Next: python import_free_n_parts.py finishes weights, OR:")
    print("  transfer_weights_nn + smooth_weights + rebuild_tans + validate_free_n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
