#!/usr/bin/env python3
"""Smooth Free-N skin weights over mesh connectivity (reduces NN speckles).

  python smooth_weights.py
  python smooth_weights.py --passes 4

Reads fa_skin/weights.buf + Index.buf + rest.buf size.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def unpack_w(data: bytes, i: int) -> tuple[list[int], list[float]]:
    bw, ww = struct.unpack_from("<II", data, i * 8)
    bones = [(bw >> (8 * k)) & 0xFF for k in range(4)]
    weights = [((ww >> (8 * k)) & 0xFF) / 255.0 for k in range(4)]
    return bones, weights


def pack_w(bones: list[int], weights: list[float]) -> bytes:
    # merge duplicate bones, keep top 4
    acc: dict[int, float] = {}
    for b, w in zip(bones, weights):
        if w <= 0:
            continue
        acc[b] = acc.get(b, 0.0) + w
    items = sorted(acc.items(), key=lambda x: -x[1])[:4]
    while len(items) < 4:
        items.append((0, 0.0))
    s = sum(w for _, w in items) or 1.0
    bones_o = []
    weights_o = []
    bw = 0
    ww = 0
    for k, (b, w) in enumerate(items):
        wn = w / s
        bi = int(b) & 0xFF
        wi = max(0, min(255, int(round(wn * 255.0))))
        bw |= bi << (8 * k)
        ww |= wi << (8 * k)
        bones_o.append(bi)
        weights_o.append(wn)
    return struct.pack("<II", bw, ww)


def main() -> int:
    pkg = Path(__file__).resolve().parents[1]
    mesh = pkg / "Meshes"

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--passes", type=int, default=3)
    p.add_argument("--blend", type=float, default=0.55, help="0=keep, 1=full neighbor avg")
    args = p.parse_args()

    rest = mesh / "rest.buf"
    wpath = mesh / "weights.buf"
    ibpath = mesh / "Index.buf"
    n = rest.stat().st_size // 12
    data = bytearray(wpath.read_bytes())
    if len(data) < n * 8:
        raise SystemExit("weights smaller than rest")
    data = data[: n * 8]

    ib = ibpath.read_bytes()
    nidx = len(ib) // 2
    idx = list(struct.unpack_from(f"<{nidx}H", ib))

    # adjacency
    adj: list[set[int]] = [set() for _ in range(n)]
    for t in range(nidx // 3):
        a, b, c = idx[t * 3], idx[t * 3 + 1], idx[t * 3 + 2]
        if a >= n or b >= n or c >= n:
            continue
        for u, v in ((a, b), (b, c), (c, a)):
            adj[u].add(v)
            adj[v].add(u)

    cur = bytes(data)
    for pss in range(args.passes):
        nxt = bytearray(n * 8)
        for i in range(n):
            bones_i, w_i = unpack_w(cur, i)
            acc: dict[int, float] = {b: w * (1.0 - args.blend) for b, w in zip(bones_i, w_i) if w > 0}
            neigh = adj[i]
            if neigh:
                inv = args.blend / len(neigh)
                for j in neigh:
                    bj, wj = unpack_w(cur, j)
                    for b, w in zip(bj, wj):
                        if w > 0:
                            acc[b] = acc.get(b, 0.0) + w * inv
            items = sorted(acc.items(), key=lambda x: -x[1])
            bs = [b for b, _ in items]
            ws = [w for _, w in items]
            nxt[i * 8 : i * 8 + 8] = pack_w(bs, ws)
        cur = bytes(nxt)
        print(f"  pass {pss + 1}/{args.passes}")

    bak = mesh / "weights_pre_smooth.bak"
    bak.write_bytes(wpath.read_bytes())
    wpath.write_bytes(cur)
    print(f"wrote {wpath} (backup {bak.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
