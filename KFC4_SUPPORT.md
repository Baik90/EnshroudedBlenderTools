# KFC4 reader/import support — 0.29.1

Validated read-only against build
`1269579|^/game38/branches/release_1.0|2026-10-16T12:58:37.402390Z`.

## Format and evidence

The KFC4 compatibility branch used by Shroudforge retains the KFC3 directory
header, 32-byte ResourceId, 8-byte ResourceEntry, 16-byte ContentEntry and
20-byte ResourceChunkInfo. ContentEntry contains offset u32, flags u16,
container index u16 and eight reserved bytes. Compression is still Zstd.

Reference: https://github.com/bonsaibauer/kfc-parser/blob/kfc4_compatibility/crates/kfc-base/src/container/header.rs

The existing reader now explicitly accepts both signatures. `KFCReader` aliases
the historical `KFC3Reader` class; callers can inspect `reader.format`.
Index tables, compressed chunk bounds and logical continuity are checked before
use. Failed initialization closes the files. Truncated DAT errors include the
offset, requested size and actual file size.

Game-resource layouts are separate from archive layout. Offsets below were
checked against the installed Shroudforge reflection cache for the exact build:
`shroudforge/cache/types-enshrouded.json`, not the stale `.cache/types.json`.

- RenderModel: materials @92; 56-byte meshes @108; LODs @116;
  renderData ResourceContentReference @272; indexData @304; vertexData @320.
- Supported static meshes: PNTCT (4), stride 24, x21y21z21_unorm (1).
  Streams are planar: all positions (8 bytes each), normals (4), tangents (4),
  colors (4), then half2 UVs (4). The decoder reconstructs records from planes;
  simply using the old interleaved decoder produces invalid UVs.
- Per-mesh byte offsets/counts replace the old vertexBuffers array. Shared LOD
  streams are deduplicated. Unsupported vertex layouts are rejected explicitly.
- Material: debugName @32; 96-byte images contain RenderStreamedTexture @8.
  Texture dimensions, format, mip count, content hash and debugName are read from
  the new layout. Slot suffixes are preserved. Full-chain content is wrapped as
  DDS; different streaming/tail layouts fail the existing size validation.
- Templates: component array @16 instead of @12. Placeable ItemInfo placedEntity
  @960; debugName @2080; cursor models @876/@892. Component/helper enumeration,
  placeable/equipment catalogs and existing audio donor enumeration use the
  version-specific array offset. VFX resources have no debugName in this build;
  the FX catalog uses referencing template names, falling back to the GUID.

## Validation

`tools/test_archive_reader.py` builds synthetic KFC3 and KFC4 indexes and verifies
GUID lookup, compressed cross-chunk reads, flags and malformed table/DAT rejection.

`tools/check_kfc4_archive.py -- GAME_FOLDER` runs through Blender and checks:

- All 91,812 descriptor reads and all 58 Zstd chunks.
- Bounds of all 101,459 content references across DAT files.
- Broken roughwood table: 1,367 vertices, 1,182 LOD0 triangles, five LODs,
  50,720-byte renderData and three 2048 textures.
- Roughwood stool: 232 vertices, 124 LOD0 triangles, two LODs,
  7,008-byte renderData and three textures.
- Actual Blender table import with UVs, normals, three packed texture images
  and one collider helper. No game archives are written.

## Export migration — experimental 0.29.2

KFC4 static replacement and new-object export are enabled. Full-topology payloads
are planar PNTCT streams with uint16 indices and 16-byte final padding. Generated
meshes use vertexCount, vertexDataByteOffset, vertexFormat, vertexStride and
positionQuantization; LODs use meshOffset. Meshlet/blend-shape/skinning ranges are
cleared for the generated static topology. Position-only replacement preserves
all original bytes outside position planes. ResourceContentReference.hash is
updated while existing reference metadata is retained. Custom localization and
PNG thumbnail references use the new nested content structures.

Full BC mip chains include a separate mip-tail content (remaining chain <=4096
bytes) and regenerated suffix ranges for streamed levels. This threshold and
range layout were checked against the native 2048 BC7, BC5 and BC1 fixtures.
The material slot is resolved through RenderMaterialImage.texture.debugName.
Native BC7/BC5/BC1 mip-tail payloads and all streaming ranges are compared
byte-for-byte to the installed archive fixtures by the export test.
Custom PCM content references use SoundResource.streamedData.hash. Specialized
Attack/Hit bytecode validation is still tied to older layouts and can reject
KFC4; that behavior is not claimed migrated here.

Simple decoration export uses stable identities. The optional seat donor filter
also recognizes KFC4 InteractionOfferRuntime; seating and FX behavior still need
in-game tests. Export adds archive_format to validation.json. Mod Builder rejects
mixed KFC3/KFC4 snapshots or snapshots incompatible with the installed archive;
update old entries instead of reusing old generated vertexBuffers code.

`tools/test_kfc4_export.py -- GAME_FOLDER` verifies position/full-topology
roundtrips (including multiple meshes), untouched UV/normal planes, mip tails,
temporary mod output and an actual Blender Simple export. The optional
`--lua-output PATH` writes scripts for syntax validation by tools/lua_check
(mlua/Lua 5.4; syntax checks do not execute the game APIs). No mod is installed
by these tests. Runtime rendering, placement/persistence, resized texture
streaming, seating and FX require user in-game confirmation. Skin weights remain
unsupported; generated topology is static. KFC3 export remains available.
