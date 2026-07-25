#!/usr/bin/env python3
"""Rebuild fa_skin/tans.buf (R8G8B8A8_SNORM pairs T,B per vert) from rest + Index + UV.

  python rebuild_tans.py

Uses Free-N rest.buf / Index.buf / TexCoord.buf by default.
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path


def f16_to_f32(h: int) -> float:
    s = (h >> 15) & 1
    e = (h >> 10) & 0x1F
    m = h & 0x3FF
    if e == 0:
        if m == 0:
            return -0.0 if s else 0.0
        return ((-1) ** s) * (m / 1024.0) * (2 ** -14)
    if e == 31:
        return float("nan") if m else ((-1) ** s) * float("inf")
    return ((-1) ** s) * (1.0 + m / 1024.0) * (2 ** (e - 15))


def snorm8(x: float) -> int:
    x = max(-1.0, min(1.0, x))
    v = int(round(x * 127.0))
    return max(-127, min(127, v)) & 0xFF


def pack_snorm4(x: float, y: float, z: float, w: float = 1.0) -> bytes:
    return bytes([snorm8(x), snorm8(y), snorm8(z), snorm8(w)])


def main() -> int:
    pkg = Path(__file__).resolve().parents[1]
    mesh = pkg / "Meshes"

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rest", type=Path, default=mesh / "rest.buf")
    p.add_argument("--index", type=Path, default=mesh / "Index.buf")
    p.add_argument("--uv", type=Path, default=mesh / "TexCoord.buf")
    args = p.parse_args()

    rest = args.rest.read_bytes()
    n = len(rest) // 12
    if n < 3:
        raise SystemExit("rest too small")

    pos = [struct.unpack_from("<3f", rest, i * 12) for i in range(n)]

    ib = args.index.read_bytes()
    nidx = len(ib) // 2
    indices = list(struct.unpack_from(f"<{nidx}H", ib))
    if nidx % 3:
        print("warn: index count not multiple of 3")

    # UVs: 2× half2 per vert (main + pad) = 8 bytes
    uvs = [(0.0, 0.0)] * n
    if args.uv.is_file() and args.uv.stat().st_size >= n * 8:
        ur = args.uv.read_bytes()
        for i in range(n):
            u_bits, v_bits = struct.unpack_from("<HH", ur, i * 8)
            uvs[i] = (f16_to_f32(u_bits), f16_to_f32(v_bits))

    # Accumulate normals + mikkt-ish tangents
    normals = [[0.0, 0.0, 0.0] for _ in range(n)]
    tangents = [[0.0, 0.0, 0.0] for _ in range(n)]

    def add3(a, b):
        a[0] += b[0]
        a[1] += b[1]
        a[2] += b[2]

    for t in range(nidx // 3):
        i0, i1, i2 = indices[t * 3], indices[t * 3 + 1], indices[t * 3 + 2]
        if i0 >= n or i1 >= n or i2 >= n:
            continue
        p0, p1, p2 = pos[i0], pos[i1], pos[i2]
        e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        nx = e1[1] * e2[2] - e1[2] * e2[1]
        ny = e1[2] * e2[0] - e1[0] * e2[2]
        nz = e1[0] * e2[1] - e1[1] * e2[0]
        fn = (nx, ny, nz)
        add3(normals[i0], fn)
        add3(normals[i1], fn)
        add3(normals[i2], fn)

        uv0, uv1, uv2 = uvs[i0], uvs[i1], uvs[i2]
        du1, dv1 = uv1[0] - uv0[0], uv1[1] - uv0[1]
        du2, dv2 = uv2[0] - uv0[0], uv2[1] - uv0[1]
        det = du1 * dv2 - du2 * dv1
        if abs(det) < 1e-12:
            # geometric fallback tangent
            tx, ty, tz = e1
        else:
            r = 1.0 / det
            tx = (dv2 * e1[0] - dv1 * e2[0]) * r
            ty = (dv2 * e1[1] - dv1 * e2[1]) * r
            tz = (dv2 * e1[2] - dv1 * e2[2]) * r
        ft = (tx, ty, tz)
        add3(tangents[i0], ft)
        add3(tangents[i1], ft)
        add3(tangents[i2], ft)

    def norm3(v):
        l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        if l < 1e-12:
            return (0.0, 1.0, 0.0)
        return (v[0] / l, v[1] / l, v[2] / l)

    out = bytearray()
    for i in range(n):
        N = norm3(normals[i])
        T = norm3(tangents[i])
        # orthonormalize T against N
        dot = T[0] * N[0] + T[1] * N[1] + T[2] * N[2]
        T = norm3((T[0] - N[0] * dot, T[1] - N[1] * dot, T[2] - N[2] * dot))
        # bitangent = N × T
        B = (
            N[1] * T[2] - N[2] * T[1],
            N[2] * T[0] - N[0] * T[2],
            N[0] * T[1] - N[1] * T[0],
        )
        B = norm3(B)
        # MultiJob reads float4 xyz; .w handedness
        out += pack_snorm4(T[0], T[1], T[2], 1.0)
        out += pack_snorm4(B[0], B[1], B[2], 1.0)

    dest = mesh / "tans.buf"
    dest.write_bytes(bytes(out))
    print(f"wrote {dest} ({len(out)} bytes) for {n} verts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
