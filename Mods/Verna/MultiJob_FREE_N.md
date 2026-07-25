# Free-N — custom mesh package

Max verts: **16384**.

---

## What `if_*` / `ic_*` are (1:1 draws)

```text
drawindexed = ic_PART , if_PART , 0
              count     start in YOUR Index.buf
```

Game still *triggers* draws at stock first_index (HairA=0, Body=28545, …).  
You **skip** and draw **your** range.

### Multi-part

Split Index ranges + non-zero `ic_*` per part + matching textures.

---

## 1:1 files (what matches your mesh)

| File | Bytes | Role |
|------|------:|------|
| `fa_skin/rest.buf` | N×12 | Bind pose |
| `fa_skin/weights.buf` | N×8 | Skin (not Verna UV layout) |
| `fa_skin/tans.buf` | N×8 | Tangents |
| `TexCoord.buf` | N×8 | UVs |
| `Index.buf` | indices×2 | Tris |
| `Job.params` | 16 | Vert ranges for bone job |
| Textures | DDS/PNG | **Same UVs as TexCoord** |
| mod.ini if/ic | — | Draw table |

---

## Multi-part (separate hair / body / legs)

1. In Blender, export **separate OBJs** (aligned to Verna), e.g.:

```
my_parts/
  Velina_Hair1.obj      → HairA
  Velina_Hair2.obj      → HairB
  Velina_Legs.obj       → Legs
  Velina_Fringe.obj     → Fringe
  Velina_Body1.obj      → Body
  (etc Skin.obj, Neck.obj)
```

2. One command:

```bat
python import_free_n_parts.py C:\path\to\my_parts
```

3. Textures (each part draw uses its slot):

```
Textures/free_n/body_diffuse.dds   (+ normal, mask)
Textures/free_n/hair_diffuse.dds   (+ normal, mask)
Textures/free_n/skin_diffuse.dds   (+ normal, mask)   optional
```

4. F10 — Hair draw uses hair tex; Body draw uses body tex; Current Verina Mod Legs obj uses Skin maps cause of weird colours when replacing if_,ic_ with legs

---
