# Gridfinity Server API

Base URL: `http://localhost:8000`

All request bodies are JSON (`Content-Type: application/json`).
All field names accept both camelCase and snake_case.

## Constants

| Name | Value | Notes |
|------|-------|-------|
| Gridfinity unit | 42 mm | Width/depth grid spacing |
| Height unit | 7 mm | Bin height increment |

---

## Health

### `GET /api/health`

```json
{ "status": "ok", "version": "0.1.0" }
```

---

## Synchronous Endpoints

These block until generation completes. Fine for single items; avoid for batch work.

### `POST /api/bin/stl`

Generate a single bin. Returns binary STL.

**Request:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| width | int 1–10 | required | Gridfinity units |
| depth | int 1–10 | required | Gridfinity units |
| height | int 1–20 | required | Height units (7mm each) |
| type | `"hollow"` \| `"solid"` | `"hollow"` | |
| wallThickness | float 0.8–3.0 | 1.2 | mm |
| dividers | `{ horizontal, vertical }` | `{ 0, 0 }` | Each 0–10 |
| magnets | bool | false | Magnet holes in base |
| stackable | bool | true | Stacking lip |
| fingerGrabs | bool | false | Scoop cutouts |
| label | string \| null | null | Engraved label text |

**Response:** `200` binary STL, `Content-Disposition: attachment; filename="bin-2x1x3-hollow.stl"`

### `POST /api/baseplate/stl`

Generate a single baseplate. Returns binary STL.

**Request:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| gridWidth | int 1–20 | required | Gridfinity units |
| gridDepth | int 1–20 | required | Gridfinity units |
| hasMagnets | bool | false | Magnet pockets |

**Response:** `200` binary STL, `Content-Disposition: attachment; filename="baseplate-3x3.stl"`

### `POST /api/plate/stl`

Generate multiple items as a ZIP of individual STLs.

**Request:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| name | string | `"plate"` | ZIP filename (without extension) |
| type | `"baseplate"` \| `"bins"` \| `"reprint"` | `"bins"` | Plate category |
| items | PlateItem[] | required | See below |

**PlateItem:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| x | float | 0 | Position on plate (mm) |
| y | float | 0 | Position on plate (mm) |
| rotation | float | 0 | Degrees (0 or 90) |
| itemType | `"bin"` \| `"baseplate"` | required | |
| binData | object | null | BinRequest or BaseplateRequest fields |

**Response:** `200` ZIP file containing named STLs.

---

## Async Job Endpoints

For long-running generation. Submit a job, poll for status, download when done.

### `POST /api/jobs/bin`

Submit a bin generation job. Request body same as `POST /api/bin/stl`.

**Response (cache miss):** `202`
```json
{ "jobId": "a1b2c3d4e5f6", "status": "pending" }
```

**Response (cache hit):** `200`
```json
{ "jobId": "a1b2c3d4e5f6", "status": "complete" }
```

### `POST /api/jobs/baseplate`

Submit a baseplate generation job. Request body same as `POST /api/baseplate/stl`.

Response format same as above.

### `POST /api/jobs/plate`

Submit a plate generation job. Request body same as `POST /api/plate/stl`.

Always returns `202` (no cache for plate jobs).

### `GET /api/jobs/{jobId}`

Poll job status.

**Response:** `200`
```json
{
  "jobId": "a1b2c3d4e5f6",
  "status": "pending | running | complete | failed",
  "resultUrl": "/api/jobs/a1b2c3d4e5f6/result",
  "error": null
}
```

`resultUrl` present only when `status` is `"complete"`.
`error` present only when `status` is `"failed"`.

**Response (unknown job):** `404`

### `GET /api/jobs/{jobId}/result`

Download completed result.

**Response:** `200` binary STL or ZIP (matches the job type).
**Response (not done yet):** `409 { "detail": "Job not complete" }`
**Response (unknown job):** `404`

---

## Rate Limiting

Applies to `POST /api/jobs/*` only. Enabled by default on Linux, disabled on macOS (local dev).

| Limit | Default | Header on 429 |
|-------|---------|----------------|
| Per IP per minute | 10 | `Retry-After` (seconds) |
| Concurrent active jobs | 4 | `Retry-After: 5` |
| Daily total | 500 | `Retry-After` (seconds until reset) |

Override via environment variables: `GRID_RATE_LIMIT_ENABLED`, `GRID_RATE_LIMIT_PER_IP_PER_MINUTE`, etc.

---

## 3MF Plate Export

Generate a single 3MF file with all items positioned on the build plate.
Unlike `POST /api/plate/stl` (ZIP of loose STLs), this produces a ready-to-slice file:
open in slicer, slice, print.

### `POST /api/plate/3mf` (sync)

### `POST /api/jobs/plate-3mf` (async)

**Request:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| name | string | `"plate"` | Filename (without extension) |
| bedWidthMm | float | null | Printer bed width in mm. Written to 3MF metadata if provided. |
| bedDepthMm | float | null | Printer bed depth in mm. |
| items | PlateItem3MF[] | required | See below |

**PlateItem3MF:**

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| itemType | `"bin"` \| `"baseplate"` | required | |
| binData | object | required | BinRequest or BaseplateRequest fields |
| xMm | float | 0 | X position on plate in mm |
| yMm | float | 0 | Y position on plate in mm |
| rotation | float | 0 | Z-axis rotation in degrees |

Positions are in **millimeters** (not grid units). The frontend converts:
`xMm = x_grid_units * 42`.

**Response (sync):** `200` binary 3MF file.
`Content-Type: model/3mf`
`Content-Disposition: attachment; filename="plate.3mf"`

**Response (async):** `202` job submission, same pattern as other job endpoints.

### 3MF File Structure

A 3MF file is a ZIP archive with this layout:

```
plate.3mf  (ZIP)
├── [Content_Types].xml
├── _rels/.rels
└── 3D/3dmodel.model
```

#### `[Content_Types].xml`

Static boilerplate declaring MIME types:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />
  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />
</Types>
```

#### `_rels/.rels`

Static boilerplate pointing to the model file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Target="/3D/3dmodel.model" Id="rel0"
    Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" />
</Relationships>
```

#### `3D/3dmodel.model`

The actual geometry and build layout:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter"
  xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">

  <metadata name="Title">plate</metadata>
  <metadata name="Application">Gridfinity Server</metadata>
  <!-- optional, if bedWidthMm/bedDepthMm provided: -->
  <metadata name="BedWidthMm">220</metadata>
  <metadata name="BedDepthMm">220</metadata>

  <resources>
    <!-- One <object> per unique geometry (deduplicated by cache key) -->
    <object id="1" type="model">
      <mesh>
        <vertices>
          <vertex x="1.00" y="2.00" z="0.00" />
          <vertex x="3.00" y="2.00" z="0.00" />
          <!-- ... indexed vertex list ... -->
        </vertices>
        <triangles>
          <triangle v1="0" v2="1" v3="2" />
          <!-- ... triangles reference vertex indices ... -->
        </triangles>
      </mesh>
    </object>
    <!-- more <object> elements for other unique geometries -->
  </resources>

  <build>
    <!-- One <item> per placement on the plate -->
    <item objectid="1" transform="1 0 0 0 1 0 0 0 1 30 40 0" />
    <item objectid="1" transform="0 -1 0 1 0 0 0 0 1 100 20 0" />
    <!-- Two placements of the same object with different transforms -->
  </build>
</model>
```

### Mesh Conversion (STL → 3MF)

CadQuery outputs ASCII STL files. The server parses these to build the indexed
mesh that 3MF requires. This is fast (milliseconds) — the expensive part is
CAD generation, which is already cached.

**Pipeline:** CadQuery render → ASCII STL bytes (cached) → parse vertices/normals → deduplicate vertices → indexed mesh → 3MF XML

**ASCII STL parsing:**
Extract vertex coordinates from `vertex x y z` lines. Each group of three
consecutive vertices forms one triangle.

**Vertex deduplication:**
ASCII STL stores 3 vertices per triangle with no indexing (lots of duplicates).
3MF uses an indexed format: a unique vertex list + triangles referencing indices.
Round vertex coordinates to 4 decimal places, build a `(x, y, z) → index` dict
to assign each unique position an index.

**No separate mesh cache needed.**
The STL cache already avoids re-running CadQuery. Parsing ASCII STL and
deduplicating vertices adds ~5ms per item. Not worth a second cache layer.

### Transform Matrix

3MF uses a 3x4 affine transformation matrix, written as 12 space-separated
values in **row-major** order:

```
m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32
```

This represents:

```
| m00  m01  m02 |        | rotation |
| m10  m11  m12 |   =    | matrix   |
| m20  m21  m22 |        |          |
| m30  m31  m32 |        | tx ty tz |
```

**CadQuery mesh origin:** Meshes are generated **centered at XY origin**.
A 1×1 bin spans roughly ±20.75mm on X and Y. Z starts at 0 (sits on plate).

**Transform composition** (applied by the server, transparent to the caller):

Given caller-supplied `xMm`, `yMm`, `rotation` (degrees):

1. Rotate around Z-axis by `rotation` degrees (around the mesh's center, which is the origin)
2. Translate so the mesh center lands at `(xMm, yMm, 0)`

For rotation angle θ (converted to radians):

```
cos(θ)  -sin(θ)  0
sin(θ)   cos(θ)  0
0        0       1
xMm      yMm     0
```

As 3MF string: `"cos -sin 0 sin cos 0 0 0 1 xMm yMm 0"`

**What the frontend sends vs. what the server does:**

The frontend sends `xMm` and `yMm` as the **center position** of the item on the
build plate. The server builds the transform matrix from these values. The
frontend does not need to know about mesh origin offsets, matrix math, or 3MF
internals — just: "I want this bin centered at (84, 63) rotated 90°."

**Corner-origin conversion:** If the frontend's bin packer uses corner-origin
coordinates (item placed at its top-left corner), convert to center before
sending:

```
xMm = cornerX + (itemWidthMm / 2)
yMm = cornerY + (itemDepthMm / 2)
```

### Deduplication

Items with identical geometry share a single `<object>` in the 3MF. Each
placement gets its own `<item>` in the `<build>` section with a different
transform.

**Deduplication key:** Same SHA256 cache key already used for STL caching
(`_cache_key(prefix, req)`). If two items produce the same cache key, they
share a mesh resource.

Example: A plate with four identical 2×1×3 hollow bins at different positions
produces one `<object>` with four `<item>` entries.

### What stays out

- Materials, colors, infill, layer height — slicer applies its own defaults
- Thumbnails — valid without them, could add later
- Print settings / slicer profiles — not our concern

### Design Notes

**Why separate from `/api/plate/stl`?**
ZIP of loose STLs = manual import and arrangement in slicer.
3MF = pre-arranged plate, ready to slice. Different workflows.

**Why positions in mm instead of grid units?**
The 3MF transform matrix is in mm. The bin packer already works in mm.
Keeps the server unit-agnostic — it doesn't need to know about gridfinity
grid spacing.

**Cache integration:**
Individual STL generation still benefits from `stl_cache`. When building
a 3MF, the server checks the cache for each unique item before generating.
The 3MF assembly (parsing + XML writing) is fast and not cached itself.

---

## Error Responses

All errors return JSON:

```json
{ "detail": "Human-readable message", "type": "ErrorClassName" }
```

| Status | Meaning |
|--------|---------|
| 422 | Validation error (bad field values) |
| 429 | Rate limited (check `Retry-After` header) |
| 404 | Job not found |
| 409 | Job not complete (result requested too early) |
| 500 | Server error (CAD generation failure, etc.) |
