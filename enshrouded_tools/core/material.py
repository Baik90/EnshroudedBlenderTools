"""Importer-facing parser for keen material resources and raw texture payloads."""

from __future__ import annotations

from dataclasses import dataclass
import struct


MATERIAL_TYPE_HASH = 0xAEE1894B

VK_FORMAT_BC1_RGB_UNORM_BLOCK = 131
VK_FORMAT_BC4_UNORM_BLOCK = 139
VK_FORMAT_BC5_UNORM_BLOCK = 141
VK_FORMAT_BC6H_UFLOAT_BLOCK = 143
VK_FORMAT_BC7_SRGB_BLOCK = 146

_VK_TO_DXGI = {
    VK_FORMAT_BC1_RGB_UNORM_BLOCK: 71,  # DXGI_FORMAT_BC1_UNORM
    VK_FORMAT_BC4_UNORM_BLOCK: 80,      # DXGI_FORMAT_BC4_UNORM
    VK_FORMAT_BC5_UNORM_BLOCK: 83,      # DXGI_FORMAT_BC5_UNORM
    VK_FORMAT_BC6H_UFLOAT_BLOCK: 95,    # DXGI_FORMAT_BC6H_UF16
    VK_FORMAT_BC7_SRGB_BLOCK: 99,       # DXGI_FORMAT_BC7_UNORM_SRGB
}
_BLOCK_BYTES = {
    VK_FORMAT_BC1_RGB_UNORM_BLOCK: 8,
    VK_FORMAT_BC4_UNORM_BLOCK: 8,
    VK_FORMAT_BC5_UNORM_BLOCK: 16,
    VK_FORMAT_BC6H_UFLOAT_BLOCK: 16,
    VK_FORMAT_BC7_SRGB_BLOCK: 16,
}


@dataclass(frozen=True)
class TextureReference:
    slot_name: str
    width: int
    height: int
    depth: int
    mip_count: int
    dimension: int
    vk_format: int
    content_hash: bytes


@dataclass(frozen=True)
class ParsedMaterial:
    debug_name: str
    textures: tuple[TextureReference, ...]


def _relative_counted_string(payload: bytes, pointer_offset: int, length_offset: int) -> str:
    relative = struct.unpack_from("<I", payload, pointer_offset)[0]
    length = struct.unpack_from("<I", payload, length_offset)[0]
    start = pointer_offset + relative
    end = start + length
    if not relative or end > len(payload):
        return ""
    return payload[start:end].decode("utf-8", errors="replace")


def parse_material(payload: bytes) -> ParsedMaterial:
    if len(payload) < 0x30:
        raise ValueError(f"material descriptor is too small: {len(payload)} bytes")

    relative, count = struct.unpack_from("<II", payload, 0x10)
    start = 0x10 + relative if relative else 0
    end = start + count * 44
    if count and end > len(payload):
        raise ValueError("material texture array exceeds descriptor")

    textures = []
    for index in range(count):
        offset = start + index * 44
        width, height, depth, _array_count = struct.unpack_from("<HHHH", payload, offset + 4)
        mip_count = payload[offset + 12]
        dimension = payload[offset + 13]
        vk_format = struct.unpack_from("<H", payload, offset + 14)[0]
        content_hash = payload[offset + 16:offset + 32]
        slot_name = _relative_counted_string(payload, offset + 36, offset + 40)
        textures.append(
            TextureReference(
                slot_name,
                width,
                height,
                depth,
                mip_count,
                dimension,
                vk_format,
                content_hash,
            )
        )

    debug_name = _relative_counted_string(payload, 0x28, 0x2C) or "Enshrouded Material"
    return ParsedMaterial(debug_name, tuple(textures))


def make_dds(texture: TextureReference, payload: bytes) -> bytes:
    """Wrap Keen's headerless BC mip chain in a DDS/DX10 container."""
    try:
        dxgi_format = _VK_TO_DXGI[texture.vk_format]
        block_bytes = _BLOCK_BYTES[texture.vk_format]
    except KeyError as exc:
        raise ValueError(f"unsupported Vulkan texture format {texture.vk_format}") from exc

    expected_size = 0
    width, height, depth = texture.width, texture.height, texture.depth
    for _ in range(texture.mip_count):
        expected_size += (
            max(1, (width + 3) // 4)
            * max(1, (height + 3) // 4)
            * max(1, depth)
            * block_bytes
        )
        width = max(1, width // 2)
        height = max(1, height // 2)
        depth = max(1, depth // 2)
    if len(payload) != expected_size:
        raise ValueError(
            f"texture payload size mismatch for {texture.slot_name}: "
            f"expected {expected_size}, got {len(payload)}"
        )

    top_level_size = (
        max(1, (texture.width + 3) // 4)
        * max(1, (texture.height + 3) // 4)
        * block_bytes
    )
    is_volume = texture.dimension == 2 and texture.depth > 1
    flags = 0x000A1007  # CAPS, HEIGHT, WIDTH, PIXELFORMAT, MIPMAPCOUNT, LINEARSIZE
    if is_volume:
        flags |= 0x00800000  # DDSD_DEPTH
    caps = 0x00401008 if texture.mip_count > 1 else 0x00001000
    header = struct.pack(
        "<7I11I8I5I",
        124,
        flags,
        texture.height,
        texture.width,
        top_level_size,
        texture.depth if is_volume else 0,
        texture.mip_count,
        *([0] * 11),
        32,
        0x4,
        struct.unpack("<I", b"DX10")[0],
        0,
        0,
        0,
        0,
        0,
        caps,
        0x00200000 if is_volume else 0,
        0,
        0,
        0,
    )
    dx10 = struct.pack("<5I", dxgi_format, 4 if is_volume else 3, 0, 1, 0)
    return b"DDS " + header + dx10 + payload
