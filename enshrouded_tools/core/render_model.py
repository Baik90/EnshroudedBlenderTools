from dataclasses import dataclass
import re
import struct
from typing import Iterator, Optional

from .known_formats import RENDER_MODEL_TYPE_HASH, decode_position, decode_snorm_10_10_10_2

@dataclass
class RenderModelLookup:
    name: str
    guid: str
    resource_index: int
    content_index: int = -1


@dataclass(frozen=True)
class VertexBuffer:
    stride: int
    format_hash: int
    data_offset: int
    data_size: int


@dataclass(frozen=True)
class MaterialReference:
    guid: str
    variant: int


@dataclass(frozen=True)
class RenderMesh:
    material_index: int
    vertex_buffer_index: int
    vertex_offset: int
    index_offset: int
    index_count: int


@dataclass(frozen=True)
class RenderLod:
    first_mesh_index: int
    mesh_count: int
    pixel_size: float


@dataclass(frozen=True)
class ParsedRenderModel:
    debug_name: str
    position_scale: tuple[float, float, float]
    position_offset: tuple[float, float, float]
    materials: tuple[MaterialReference, ...]
    vertex_buffers: tuple[VertexBuffer, ...]
    meshes: tuple[RenderMesh, ...]
    lods: tuple[RenderLod, ...]
    render_data_hash: bytes
    index_data_offset: int
    index_data_size: int
    index_stride: int


@dataclass(frozen=True)
class DecodedMesh:
    vertices: tuple[tuple[float, float, float], ...]
    uvs: tuple[tuple[float, float], ...]
    normals: tuple[tuple[float, float, float], ...]
    tangents: tuple[tuple[float, float, float], ...]
    bitangent_signs: tuple[float, ...]
    triangles: tuple[tuple[int, int, int], ...]
    triangle_materials: tuple[int, ...]

# Known-good regression target. Do not hard-code the importer to this model;
# it exists only so early development has a deterministic test case.
KNOWN_TABLE = RenderModelLookup(
    name="global_props_roughwood_table_01_a_broken",
    guid="02e2e8fd-33cf-4c27-9f11-049261fba027",
    resource_index=13862,
    content_index=60764,
)

def normalize_guid(text: str) -> str:
    return text.strip().lower()

def looks_like_guid(text: str) -> bool:
    return bool(re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        text.strip(),
    ))


def _guid_from_bytes(data: bytes) -> str:
    if len(data) != 16:
        raise ValueError("GUID must be exactly 16 bytes")
    return (
        f"{int.from_bytes(data[0:4], 'little'):08x}-"
        f"{int.from_bytes(data[4:6], 'little'):04x}-"
        f"{int.from_bytes(data[6:8], 'little'):04x}-"
        f"{int.from_bytes(data[8:10], 'big'):04x}-"
        f"{int.from_bytes(data[10:16], 'big'):012x}"
    )


_ASCII_TOKEN = re.compile(rb"[A-Za-z0-9][A-Za-z0-9_./-]{3,255}")


def _debug_name_score(value: str) -> tuple[int, int, int]:
    """Rank likely RenderModel debug names found in a mapped resource."""
    lower = value.lower()
    score = 0
    if lower.startswith(("global_", "building_", "character_", "item_", "terrain_")):
        score += 100
    if value == lower:
        score += 15
    score += min(value.count("_"), 12) * 4
    if "::" in value or "/" in value or "." in value:
        score -= 40
    if lower in {"renderdata", "indexdata", "vertexbuffers", "debugname"}:
        score -= 100
    return score, value.count("_"), len(value)


def extract_debug_name(payload: bytes) -> Optional[str]:
    """Extract the most likely human-readable debugName from a descriptor.

    KFC3 mapped resources retain the UTF-8 debug name. Until the reflection
    descriptor parser is complete, ranking embedded tokens keeps browsing
    independent from Blender while still returning every RenderModel by GUID.
    """
    candidates = {
        match.group().decode("utf-8", errors="strict")
        for match in _ASCII_TOKEN.finditer(payload)
    }
    candidates = {
        value for value in candidates
        if "_" in value and not looks_like_guid(value)
    }
    if not candidates:
        return None
    best = max(candidates, key=_debug_name_score)
    return best if _debug_name_score(best)[0] > 0 else None


def _relative_array(payload: bytes, field_offset: int, entry_size: int) -> tuple[int, int]:
    relative, count = struct.unpack_from("<II", payload, field_offset)
    start = field_offset + relative if relative else 0
    end = start + count * entry_size
    if count and (start < 0 or end > len(payload)):
        raise ValueError(
            f"mapped array at 0x{field_offset:x} exceeds descriptor: "
            f"start=0x{start:x}, count={count}, stride={entry_size}"
        )
    return start, count


def _relative_string(payload: bytes, field_offset: int) -> str:
    relative = struct.unpack_from("<I", payload, field_offset)[0]
    start = field_offset + relative
    if not relative or start >= len(payload):
        return ""
    match = _ASCII_TOKEN.match(payload, start)
    return match.group().decode("utf-8") if match else ""


def parse_render_model(payload: bytes) -> ParsedRenderModel:
    """Parse the importer-facing fields of a mapped keen::RenderModel."""
    if len(payload) < 0xD0:
        raise ValueError(f"RenderModel descriptor is too small: {len(payload)} bytes")

    debug_name = _relative_string(payload, 0) or extract_debug_name(payload) or "RenderModel"
    position_scale = struct.unpack_from("<3f", payload, 0x40)
    position_offset = struct.unpack_from("<3f", payload, 0x4C)

    material_start, material_count = _relative_array(payload, 0x58, 20)
    materials = []
    for index in range(material_count):
        offset = material_start + index * 20
        guid = _guid_from_bytes(payload[offset:offset + 16])
        variant = struct.unpack_from("<I", payload, offset + 16)[0]
        materials.append(MaterialReference(guid, variant))

    vb_start, vb_count = _relative_array(payload, 0x60, 32)
    vertex_buffers = []
    for index in range(vb_count):
        stride, format_hash, data_offset, data_size = struct.unpack_from(
            "<IIII", payload, vb_start + index * 32
        )
        vertex_buffers.append(VertexBuffer(stride, format_hash, data_offset, data_size))

    mesh_start, mesh_count = _relative_array(payload, 0x68, 44)
    meshes = []
    for index in range(mesh_count):
        values = struct.unpack_from("<7I", payload, mesh_start + index * 44 + 16)
        meshes.append(RenderMesh(*values[:5]))

    lod_start, lod_count = _relative_array(payload, 0x70, 12)
    lods = tuple(
        RenderLod(*struct.unpack_from("<IIf", payload, lod_start + index * 12))
        for index in range(lod_count)
    )

    render_data_hash = payload[0x84:0x94]
    index_data_offset, index_data_size, index_stride = struct.unpack_from("<III", payload, 0xC4)
    return ParsedRenderModel(
        debug_name=debug_name,
        position_scale=position_scale,
        position_offset=position_offset,
        materials=tuple(materials),
        vertex_buffers=tuple(vertex_buffers),
        meshes=tuple(meshes),
        lods=lods,
        render_data_hash=render_data_hash,
        index_data_offset=index_data_offset,
        index_data_size=index_data_size,
        index_stride=index_stride,
    )


def decode_lod(model: ParsedRenderModel, render_data: bytes, lod_index: int) -> DecodedMesh:
    """Decode packed positions, half2 UVs and triangle indices for one LOD."""
    if not 0 <= lod_index < len(model.lods):
        raise IndexError(f"LOD {lod_index} outside available range 0..{len(model.lods) - 1}")
    if model.index_stride != 2:
        raise ValueError(f"unsupported index stride {model.index_stride}; expected uint16")

    vertices = []
    uvs = []
    normals = []
    tangents = []
    bitangent_signs = []
    buffer_bases = []
    fetch_scale = 1.0 / 0x1FFFFF
    for vertex_buffer in model.vertex_buffers:
        if vertex_buffer.stride != 24:
            raise ValueError(f"unsupported vertex stride {vertex_buffer.stride}; expected 24")
        if vertex_buffer.data_size % vertex_buffer.stride:
            raise ValueError("vertex buffer size is not divisible by its stride")
        buffer_bases.append(len(vertices))
        count = vertex_buffer.data_size // vertex_buffer.stride
        for index in range(count):
            offset = vertex_buffer.data_offset + index * vertex_buffer.stride
            vertex = render_data[offset:offset + vertex_buffer.stride]
            if len(vertex) != vertex_buffer.stride:
                raise EOFError("renderData vertex buffer is truncated")
            vertices.append(decode_position(vertex, model.position_offset, model.position_scale, fetch_scale))
            packed_normal, packed_tangent = struct.unpack_from("<II", vertex, 8)
            normal, _ = decode_snorm_10_10_10_2(packed_normal)
            tangent, bitangent_sign = decode_snorm_10_10_10_2(packed_tangent)
            normals.append(normal)
            tangents.append(tangent)
            bitangent_signs.append(bitangent_sign)
            u, v = struct.unpack_from("<2e", vertex, 20)
            uvs.append((float(u), 1.0 - float(v)))

    lod = model.lods[lod_index]
    triangles = []
    triangle_materials = []
    for mesh_index in range(lod.first_mesh_index, lod.first_mesh_index + lod.mesh_count):
        if not 0 <= mesh_index < len(model.meshes):
            raise ValueError(f"LOD references missing mesh {mesh_index}")
        mesh = model.meshes[mesh_index]
        if not 0 <= mesh.vertex_buffer_index < len(buffer_bases):
            raise ValueError(f"mesh references missing vertex buffer {mesh.vertex_buffer_index}")
        if mesh.index_count % 3:
            raise ValueError(f"mesh {mesh_index} index count is not divisible by three")
        index_start = model.index_data_offset + mesh.index_offset * model.index_stride
        index_end = index_start + mesh.index_count * model.index_stride
        if index_end > len(render_data):
            raise EOFError(f"mesh {mesh_index} index data is truncated")
        indices = struct.unpack_from(f"<{mesh.index_count}H", render_data, index_start)
        base = buffer_bases[mesh.vertex_buffer_index] + mesh.vertex_offset
        for offset in range(0, len(indices), 3):
            i0, i1, i2 = (base + value for value in indices[offset:offset + 3])
            # Keen's front-face winding is opposite to Blender's.
            triangle = (i0, i2, i1)
            if max(triangle) >= len(vertices):
                raise ValueError(f"mesh {mesh_index} index exceeds decoded vertices")
            triangles.append(triangle)
            triangle_materials.append(mesh.material_index)

    return DecodedMesh(
        tuple(vertices),
        tuple(uvs),
        tuple(normals),
        tuple(tangents),
        tuple(bitangent_signs),
        tuple(triangles),
        tuple(triangle_materials),
    )


def iter_render_models(reader) -> Iterator[RenderModelLookup]:
    """Yield all part-zero keen::RenderModel resources in archive order."""
    indices = [
        index for index, rid in enumerate(reader.resource_ids)
        if rid.type_hash == RENDER_MODEL_TYPE_HASH and rid.part_index == 0
    ]
    indices.sort(key=lambda index: reader.resource_entries[index].offset)

    active_chunk = None
    for index in indices:
        entry = reader.resource_entries[index]
        chunk = reader.find_chunk_for_offset(entry.offset)
        if chunk != active_chunk:
            reader.clear_chunk_cache()
            active_chunk = chunk
        rid = reader.resource_ids[index]
        name = extract_debug_name(reader.read_resource(index)) or rid.guid
        yield RenderModelLookup(name=name, guid=rid.guid, resource_index=index)

    reader.clear_chunk_cache()


def list_render_models(reader) -> list[RenderModelLookup]:
    return sorted(iter_render_models(reader), key=lambda model: (model.name.casefold(), model.guid))

def resolve_model(reader, query: str) -> Optional[RenderModelLookup]:
    """TODO: make generic.

    First implementation target:
    * GUID -> locate ResourceId with type_hash 0x177394c7 and part 0.
    * Debug name -> search decompressed resource data for UTF-8 query and retain
      only resources whose ResourceId has the RenderModel type hash.
    * Parse RenderModel mapped resource enough to obtain debugName and renderData.

    The current KFC3Reader already exposes resource IDs, entries and logical
    resource extraction. Keep the archive parser separate from Blender API.
    """
    q = query.strip()
    if not q:
        return None

    if looks_like_guid(q):
        guid = normalize_guid(q)
        for idx, rid in enumerate(reader.resource_ids):
            if rid.guid == guid and rid.type_hash == RENDER_MODEL_TYPE_HASH and rid.part_index == 0:
                name = extract_debug_name(reader.read_resource(idx)) or guid
                return RenderModelLookup(name=name, guid=guid, resource_index=idx)
        return None

    query = q.casefold()
    exact = None
    for model in iter_render_models(reader):
        name = model.name.casefold()
        if name == query:
            return model
        if exact is None and query in name:
            exact = model
    return exact
