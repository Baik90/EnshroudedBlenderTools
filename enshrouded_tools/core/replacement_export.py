"""Topology-preserving RenderModel replacement export, independent of bpy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile

from .known_formats import encode_position, encode_snorm_10_10_10_2


@dataclass(frozen=True)
class ReplacementPayload:
    data: bytes
    position_offset: tuple[float, float, float]
    position_scale: tuple[float, float, float]
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    sphere_center: tuple[float, float, float]
    sphere_radius: float
    vertex_count: int
    index_count: int = 0
    vertex_data_size: int = 0
    vertex_stride: int = 24
    position_fetch_scale: float = 1.0 / 0x1FFFFF
    full_topology: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


def build_replacement_payload(model, original_data: bytes, positions) -> ReplacementPayload:
    positions = tuple(tuple(float(component) for component in position) for position in positions)
    expected_count = sum(buffer.data_size // buffer.stride for buffer in model.vertex_buffers)
    if len(positions) != expected_count:
        raise ValueError(
            f"topology mismatch: source RenderModel has {expected_count} vertices, "
            f"Blender mesh has {len(positions)}"
        )
    if not positions:
        raise ValueError("cannot export an empty mesh")
    if any(buffer.stride != 24 for buffer in model.vertex_buffers):
        raise ValueError("replacement export currently supports only 24-byte vertex buffers")

    bounds_min = tuple(min(position[axis] for position in positions) for axis in range(3))
    bounds_max = tuple(max(position[axis] for position in positions) for axis in range(3))
    extents = tuple(bounds_max[axis] - bounds_min[axis] for axis in range(3))
    margins = tuple(max(extent * 1e-5, 1e-5) for extent in extents)
    position_offset = tuple(bounds_min[axis] - margins[axis] for axis in range(3))
    position_scale = tuple(
        max(extents[axis] + margins[axis] * 2.0, 1e-5)
        for axis in range(3)
    )
    output = bytearray(original_data)
    vertex_index = 0
    for buffer in model.vertex_buffers:
        for local_index in range(buffer.data_size // buffer.stride):
            offset = buffer.data_offset + local_index * buffer.stride
            if offset + buffer.stride > len(output):
                raise EOFError("original renderData vertex buffer is truncated")
            original_u1 = struct.unpack_from("<I", output, offset + 4)[0]
            output[offset:offset + 8] = encode_position(
                positions[vertex_index],
                position_offset,
                position_scale,
                buffer.position_fetch_scale,
                original_u1_flag=original_u1,
            )
            vertex_index += 1

    sphere_center = tuple((bounds_min[axis] + bounds_max[axis]) * 0.5 for axis in range(3))
    sphere_radius = max(
        math.sqrt(sum((position[axis] - sphere_center[axis]) ** 2 for axis in range(3)))
        for position in positions
    ) + max(margins)

    padded_min = tuple(bounds_min[axis] - margins[axis] for axis in range(3))
    padded_max = tuple(bounds_max[axis] + margins[axis] for axis in range(3))
    return ReplacementPayload(
        data=bytes(output),
        position_offset=position_offset,
        position_scale=position_scale,
        bounds_min=padded_min,
        bounds_max=padded_max,
        sphere_center=sphere_center,
        sphere_radius=sphere_radius,
        vertex_count=len(positions),
    )


def build_full_topology_payload(vertex_records, indices) -> ReplacementPayload:
    """Build a complete static 24-byte vertex stream plus uint16 index stream.

    Each record is ``(position, normal, tangent, bitangent_sign, uv, color)``.
    UV is already in Keen convention and color is four raw RGBA bytes.
    """
    records = tuple(vertex_records)
    indices = tuple(int(index) for index in indices)
    if not records or not indices:
        raise ValueError("full topology export requires vertices and triangle indices")
    if len(indices) % 3:
        raise ValueError("index count must be divisible by three")
    if len(records) > 0xFFFF or max(indices) > 0xFFFF:
        raise ValueError("full topology export currently supports at most 65535 vertices")
    if min(indices) < 0 or max(indices) >= len(records):
        raise ValueError("index references a missing exported vertex")

    positions = tuple(tuple(float(value) for value in record[0]) for record in records)
    raw_min = tuple(min(position[axis] for position in positions) for axis in range(3))
    raw_max = tuple(max(position[axis] for position in positions) for axis in range(3))
    extents = tuple(raw_max[axis] - raw_min[axis] for axis in range(3))
    margins = tuple(max(extent * 1e-5, 1e-5) for extent in extents)
    position_offset = tuple(raw_min[axis] - margins[axis] for axis in range(3))
    position_scale = tuple(max(extents[axis] + 2.0 * margins[axis], 1e-5) for axis in range(3))
    fetch_scale = 1.0 / 0x1FFFFF

    vertices = bytearray()
    for position, normal, tangent, bitangent_sign, uv, color in records:
        if len(color) != 4:
            raise ValueError("vertex color must contain exactly four bytes")
        vertices += encode_position(position, position_offset, position_scale, fetch_scale)
        vertices += struct.pack("<I", encode_snorm_10_10_10_2(normal, 1.0))
        vertices += struct.pack("<I", encode_snorm_10_10_10_2(tangent, bitangent_sign))
        vertices += bytes(color)
        vertices += struct.pack("<2e", float(uv[0]), float(uv[1]))

    index_data = struct.pack(f"<{len(indices)}H", *indices)
    center = tuple((raw_min[axis] + raw_max[axis]) * 0.5 for axis in range(3))
    radius = max(math.dist(position, center) for position in positions) + max(margins)
    return ReplacementPayload(
        data=bytes(vertices) + index_data,
        position_offset=position_offset,
        position_scale=position_scale,
        bounds_min=tuple(raw_min[axis] - margins[axis] for axis in range(3)),
        bounds_max=tuple(raw_max[axis] + margins[axis] for axis in range(3)),
        sphere_center=center,
        sphere_radius=radius,
        vertex_count=len(records),
        index_count=len(indices),
        vertex_data_size=len(vertices),
        position_fetch_scale=fetch_scale,
        full_topology=True,
    )


def _number(value: float) -> str:
    return format(float(value), ".17g")


def make_mod_lua(mod_id: str, model_guid: str, payload_file: str, replacement: ReplacementPayload) -> str:
    offset = replacement.position_offset
    scale = replacement.position_scale
    minimum = replacement.bounds_min
    maximum = replacement.bounds_max
    center = replacement.sphere_center
    radius = replacement.sphere_radius
    topology_patch = ""
    if replacement.full_topology:
        topology_patch = f'''
if #model.vertexBuffers < 1 or #model.meshes < 1 or #model.lods < 1 then
    error("[{mod_id}] target RenderModel has no reusable static mesh layout")
end

local vertex_buffer = model.vertexBuffers[1]
vertex_buffer.stride = {replacement.vertex_stride}
vertex_buffer.positionFetchScale = {_number(replacement.position_fetch_scale)}
vertex_buffer.data.start = 0
vertex_buffer.data.count = {replacement.vertex_data_size}
vertex_buffer.skinningDataOffset = 0
vertex_buffer.blendShapeDataOffset = 0
vertex_buffer.blendShapeVertexCount = 0

model.indexData.start = {replacement.vertex_data_size}
model.indexData.count = {replacement.index_count * 2}
model.indexStride = 2

local replacement_mesh = model.meshes[1]
replacement_mesh.vertexBufferIndex = 0
replacement_mesh.vertexOffset = 0
replacement_mesh.indexOffset = 0
replacement_mesh.indexCount = {replacement.index_count}

for _, lod in ipairs(model.lods) do
    lod.firstMeshIndex = 0
    lod.meshCount = 1
end
'''
    return f'''-- Generated by Enshrouded Blender Tools
-- {'Full-topology experimental' if replacement.full_topology else 'Topology-preserving'} keen::RenderModel replacement.

local MODEL_GUID = "{model_guid}"
local MODEL_TYPE = "keen::RenderModel"
local MESH_FILE = "{payload_file}"

print("[{mod_id}] loading")

local resource = game.assets.get_resource(MODEL_GUID, MODEL_TYPE, 0)
if resource == nil then
    error("[{mod_id}] target RenderModel not found: " .. MODEL_GUID)
end

---@type keen.RenderModel
local model = resource.data
if model == nil then
    error("[{mod_id}] target RenderModel has no data")
end

local mesh_buffer = io.read(MESH_FILE)
if mesh_buffer == nil then
    error("[{mod_id}] could not read " .. MESH_FILE)
end

local content = game.assets.create_content(mesh_buffer)
if content == nil then
    error("[{mod_id}] create_content failed")
end

model.renderData = game.guid.to_content_hash(content.guid)
{topology_patch}

model.positionOffset.x = {_number(offset[0])}
model.positionOffset.y = {_number(offset[1])}
model.positionOffset.z = {_number(offset[2])}
model.positionScale.x = {_number(scale[0])}
model.positionScale.y = {_number(scale[1])}
model.positionScale.z = {_number(scale[2])}

model.boundingBox.min.x = {_number(minimum[0])}
model.boundingBox.min.y = {_number(minimum[1])}
model.boundingBox.min.z = {_number(minimum[2])}
model.boundingBox.max.x = {_number(maximum[0])}
model.boundingBox.max.y = {_number(maximum[1])}
model.boundingBox.max.z = {_number(maximum[2])}

local sphere_x = {_number(center[0])}
local sphere_y = {_number(center[1])}
local sphere_z = {_number(center[2])}
local sphere_r = {_number(radius)}
model.boundingSphere.center.x = sphere_x
model.boundingSphere.center.y = sphere_y
model.boundingSphere.center.z = sphere_z
model.boundingSphere.radius = sphere_r

for _, mesh in ipairs(model.meshes) do
    mesh.boundingSphere.center.x = sphere_x
    mesh.boundingSphere.center.y = sphere_y
    mesh.boundingSphere.center.z = sphere_z
    mesh.boundingSphere.radius = sphere_r
end

print("[{mod_id}] patched RenderModel; content=" .. tostring(content.guid))
'''


def make_mod_json(mod_id: str, name: str, version: str, author: str, model_name: str) -> str:
    return json.dumps(
        {
            "id": mod_id,
            "name": name,
            "version": version,
            "capabilities": ["patch"],
            "description": f"Replaces the RenderModel {model_name}.",
            "authors": [author],
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def make_validation_json(model_guid: str, model_name: str, replacement: ReplacementPayload) -> str:
    return json.dumps(
        {
            "mesh_size": len(replacement.data),
            "mesh_sha256": replacement.sha256,
            "target_guid": model_guid,
            "target_type": "keen::RenderModel",
            "target_part": 0,
            "model_name": model_name,
            "vertex_count": replacement.vertex_count,
            "index_count": replacement.index_count,
            "full_topology": replacement.full_topology,
            "vertex_data_size": replacement.vertex_data_size,
            "vertex_stride": replacement.vertex_stride,
            "positionOffset": replacement.position_offset,
            "positionScale": replacement.position_scale,
            "boundingBoxMin": replacement.bounds_min,
            "boundingBoxMax": replacement.bounds_max,
            "boundingSphere": (*replacement.sphere_center, replacement.sphere_radius),
        },
        indent=2,
    ) + "\n"


def write_replacement_mod(
    mods_root,
    mod_id: str,
    mod_name: str,
    version: str,
    author: str,
    model_guid: str,
    model_name: str,
    replacement: ReplacementPayload,
) -> Path:
    """Atomically stage a replacement mod, replacing only its exact target folder."""
    mods_root = Path(mods_root).resolve()
    target = (mods_root / mod_id).resolve()
    if target.parent != mods_root or target == mods_root:
        raise ValueError("unsafe mod export target")

    payload_file = "render_data.bin"
    mods_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{mod_id}_", dir=mods_root))
    try:
        (staging / "src").mkdir()
        (staging / payload_file).write_bytes(replacement.data)
        (staging / "mod.json").write_text(
            make_mod_json(mod_id, mod_name, version, author, model_name),
            encoding="utf-8",
        )
        (staging / "validation.json").write_text(
            make_validation_json(model_guid, model_name, replacement),
            encoding="utf-8",
        )
        (staging / "src" / "mod.lua").write_text(
            make_mod_lua(mod_id, model_guid, payload_file, replacement),
            encoding="utf-8",
        )

        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        staging.replace(target)
        staging = None
        return target
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
