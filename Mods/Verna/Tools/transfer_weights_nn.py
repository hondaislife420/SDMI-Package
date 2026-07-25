#!/usr/bin/env python3
"""Nearest-neighbor weight transfer: stock Verna → Free-N mesh (no Blender).

For Body-only Free-N (job_Body base=0 count=N, other jobs 0):
  MultiJob skins ALL free verts with the **Body bone palette**.
  So we only sample stock weights from Verna **Body region** verts
  (base 7721 .. 16059), which use Body palette bone indices.

  python transfer_weights_nn.py
  python transfer_weights_nn.py --src-rest ..\\Meshes\\fa_skin\\rest.buf.bak

Requires:
  Meshes/fa_skin/rest.buf     = Free-N positions (N×12)  [current free mesh]
  stock weights source        = 16060×8 (default: backup or Position-side)

If you overwrote stock weights.buf already, use:
  --stock-weights path\\to\\stock_weights.buf
  --stock-rest path\\to\\stock_rest_16060.buf

Writes:
  Meshes/fa_skin/weights.buf  (N×8)
  Optional backup of previous free weights.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

STOCK_N = 16060
BODY_BASE = 7721
BODY_COUNT = 8339  # 7721..16059
MAX_N = 16384


def load_rest(path: Path) -> list[tuple[float, float, float]]:
    raw = path.read_bytes()
    if len(raw) % 12:
        raise SystemExit(f"{path}: size {len(raw)} not multiple of 12")
    n = len(raw) // 12
    verts = []
    for i in range(n):
        x, y, z = struct.unpack_from("<3f", raw, i * 12)
        verts.append((x, y, z))
    return verts


def load_weights(path: Path, n: int) -> bytes:
    raw = path.read_bytes()
    need = n * 8
    if len(raw) < need:
        raise SystemExit(f"{path}: size {len(raw)} < {need}")
    return raw[:need]


def nearest_idx(px: float, py: float, pz: float, pts: list[tuple[float, float, float]]) -> int:
    best = 0
    best_d = 1e30
    for i, (x, y, z) in enumerate(pts):
        dx, dy, dz = px - x, py - y, pz - z
        d = dx * dx + dy * dy + dz * dz
        if d < best_d:
            best_d = d
            best = i
    return best


def main() -> int:
    pkg = Path(__file__).resolve().parents[1]
    mesh = pkg / "Meshes"

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--free-rest",
        type=Path,
        default=None,
        help="Free-N rest (default fa_skin/rest.buf)",
    )
    p.add_argument(
        "--stock-rest",
        type=Path,
        default=None,
        help="Stock 16060 rest (default: try backup, else Position.buf)",
    )
    p.add_argument(
        "--stock-weights",
        type=Path,
        default=None,
        help="Stock 16060 weights (default: try _free_n_backup or fa_skin)",
    )
    p.add_argument(
        "--body-region-only",
        action="store_true",
        default=True,
        help="Sample only Verna Body verts (default ON for body-only Free-N)",
    )
    p.add_argument("--all-stock-verts", action="store_true", help="Sample all 16060 (wrong for body-only jobs)")
    p.add_argument("--k", type=int, default=4, help="k-nearest stock verts to blend (default 4)")
    args = p.parse_args()
    if args.all_stock_verts:
        args.body_region_only = False
    k_nn = max(1, args.k)

    free_rest = args.free_rest
    if not free_rest.is_file():
        raise SystemExit(f"missing free rest: {free_rest}")

    free_verts = load_rest(free_rest)
    n = len(free_verts)
    if n < 1 or n > MAX_N:
        raise SystemExit(f"free N={n} out of range")

    # Stock rest
    stock_rest_path = args.stock_rest
    if stock_rest_path is None:
        candidates = [
            mesh / "_free_n_backup" / "Rest-cs-t3=d9248384-cs=0d516b116c85c323.buf",
        ]
        for c in candidates:
            if c.is_file() and c.stat().st_size == STOCK_N * 12:
                stock_rest_path = c
                break
    if stock_rest_path is None or not stock_rest_path.is_file():
        raise SystemExit(
            "No stock 16060 rest found. Pass --stock-rest path\\to\\16060_rest.buf\n"
            "(copy of original fa_skin/rest.buf or Position.buf of same size)"
        )

    stock_verts = load_rest(stock_rest_path)
    if len(stock_verts) != STOCK_N:
        raise SystemExit(f"stock rest must be {STOCK_N} verts, got {len(stock_verts)}")

    # Stock weights
    stock_w_path = args.stock_weights
    if stock_w_path is None:
        # Prefer backup over current free weights
        bak = mesh / "_free_n_backup" / "Weights-cs-t1=9bff6d41-cs=0d516b116c85c323.buf"
        if bak.is_file() and bak.stat().st_size == STOCK_N * 8:
            stock_w_path = bak
    if stock_w_path is None or not stock_w_path.is_file():
        raise SystemExit(
            "No stock weights found. Pass --stock-weights path\\to\\16060_weights.buf"
        )
    if stock_w_path.resolve() == (mesh / "weights.buf").resolve():
        if stock_w_path.stat().st_size != STOCK_N * 8:
            raise SystemExit(
                "fa_skin/weights.buf is Free-N sized, not stock.\n"
                "Pass --stock-weights to a 16060 weights file (e.g. Meshes/_free_n_backup/weights.buf)"
            )

    stock_w = load_weights(stock_w_path, STOCK_N)
    print(f"Free-N verts: {n} from {free_rest}")
    print(f"Stock rest:   {stock_rest_path} ({len(stock_verts)})")
    print(f"Stock weights:{stock_w_path}")

    if args.body_region_only:
        src_indices = list(range(BODY_BASE, BODY_BASE + BODY_COUNT))
        src_pts = [stock_verts[i] for i in src_indices]
        print(f"Sampling Body region only: {BODY_BASE}..{BODY_BASE + BODY_COUNT - 1}")
    else:
        src_indices = list(range(STOCK_N))
        src_pts = stock_verts
        print("Sampling ALL stock verts (use only if multi-region jobs match stock)")

    # Backup free weights
    out_w = mesh / "weights.buf"
    if out_w.is_file():
        bak = mesh / "weights_free_stub.bak"
        bak.write_bytes(out_w.read_bytes())
        print(f"backed up previous weights → {bak.name}")

    # Chunked NN for speed: simple spatial hash
    cell = 0.15  # game units; tweak if needed
    grid: dict[tuple[int, int, int], list[int]] = {}
    for li, (x, y, z) in enumerate(src_pts):
        key = (int(x / cell), int(y / cell), int(z / cell))
        grid.setdefault(key, []).append(li)

    def blend_weights(locals_d: list[tuple[int, float]]) -> bytes:
        """locals_d: list of (local_src_index, dist2)."""
        acc: dict[int, float] = {}
        for li, d2 in locals_d:
            stock_i = src_indices[li]
            bw, ww = struct.unpack_from("<II", stock_w, stock_i * 8)
            # inverse-distance weight (eps)
            w_nn = 1.0 / (1e-6 + d2)
            for k in range(4):
                b = (bw >> (8 * k)) & 0xFF
                wv = ((ww >> (8 * k)) & 0xFF) / 255.0
                if wv > 0:
                    acc[b] = acc.get(b, 0.0) + wv * w_nn
        items = sorted(acc.items(), key=lambda x: -x[1])[:4]
        while len(items) < 4:
            items.append((0, 0.0))
        s = sum(w for _, w in items) or 1.0
        bw = 0
        ww = 0
        for k, (b, w) in enumerate(items):
            wi = max(0, min(255, int(round((w / s) * 255.0))))
            bw |= (int(b) & 0xFF) << (8 * k)
            ww |= wi << (8 * k)
        return struct.pack("<II", bw, ww)

    out = bytearray(n * 8)
    max_dist2 = 0.0
    for i, (px, py, pz) in enumerate(free_verts):
        cx, cy, cz = int(px / cell), int(py / cell), int(pz / cell)
        candidates: list[int] = []
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for dz in (-2, -1, 0, 1, 2):
                    candidates.extend(grid.get((cx + dx, cy + dy, cz + dz), []))
        scored: list[tuple[float, int]] = []
        if not candidates:
            local = nearest_idx(px, py, pz, src_pts)
            x, y, z = src_pts[local]
            d2 = (px - x) ** 2 + (py - y) ** 2 + (pz - z) ** 2
            scored = [(d2, local)]
        else:
            for li in candidates:
                x, y, z = src_pts[li]
                d2 = (px - x) ** 2 + (py - y) ** 2 + (pz - z) ** 2
                scored.append((d2, li))
            scored.sort(key=lambda t: t[0])
            scored = scored[:k_nn]
        if scored[0][0] > max_dist2:
            max_dist2 = scored[0][0]
        out[i * 8 : i * 8 + 8] = blend_weights([(li, d2) for d2, li in scored])

    out_w.write_bytes(bytes(out))
    print(f"wrote {out_w} ({len(out)} bytes) k={k_nn}")
    print(f"max nearest dist (approx) = {max_dist2 ** 0.5:.4f} (lower is better; big = bad alignment)")
    print()
    print("F10")
    print("Optional: python smooth_weights.py && python rebuild_tans.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
