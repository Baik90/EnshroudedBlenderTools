"""Confirmed format facts from the current Enshrouded KFC3 reverse engineering."""

RENDER_MODEL_TYPE = "keen::RenderModel"
RENDER_MODEL_TYPE_HASH = 0x177394C7

# Confirmed static model vertex stream used by the roughwood-table test.
KNOWN_VERTEX_STRIDE = 24

# Position packing:
#   u0 bits 11..31 -> X[0..20]
#   u1 bits  0..20 -> Z[0..20]
#   Y high 11 bits -> u0 bits 0..10
#   Y low  10 bits -> u1 bits 21..30
#   u1 bit 31       -> unknown flag; preserve when doing template replacement
POSITION_MASK = 0x1FFFFF


def _snorm10(raw: int) -> float:
    signed = raw - 0x400 if raw & 0x200 else raw
    return max(-1.0, signed / 511.0)


def decode_snorm_10_10_10_2(packed: int):
    """Decode Vulkan-style A2B10G10R10 SNORM into normalized XYZ and W sign."""
    import math
    xyz = tuple(_snorm10((packed >> shift) & 0x3FF) for shift in (0, 10, 20))
    length = math.sqrt(sum(component * component for component in xyz))
    if length:
        xyz = tuple(component / length for component in xyz)
    w_bits = (packed >> 30) & 0x3
    w = -1.0 if w_bits in {2, 3} else float(w_bits)
    return xyz, w


def encode_snorm_10_10_10_2(vector, w: float = 1.0) -> int:
    """Encode a unit XYZ vector and signed W for normal/tangent export."""
    import math
    length = math.sqrt(sum(float(component) ** 2 for component in vector))
    if not length:
        raise ValueError("cannot encode a zero-length direction")
    packed = 0
    for shift, component in zip((0, 10, 20), vector):
        value = max(-1.0, min(1.0, float(component) / length))
        signed = max(-511, min(511, round(value * 511.0)))
        packed |= (signed & 0x3FF) << shift
    packed |= (1 if w >= 0.0 else 3) << 30
    return packed

def decode_position(vertex24: bytes, position_offset, position_scale, fetch_scale):
    import struct
    if len(vertex24) < 8:
        raise ValueError("vertex must contain at least 8 bytes")
    u0, u1 = struct.unpack_from("<II", vertex24, 0)
    qx = (u0 >> 11) & POSITION_MASK
    qz = u1 & POSITION_MASK
    qy = ((u0 & 0x7FF) << 10) | ((u1 >> 21) & 0x3FF)
    return tuple(
        position_offset[i] + (q * fetch_scale * position_scale[i])
        for i, q in enumerate((qx, qy, qz))
    )

def encode_position(position, position_offset, position_scale, fetch_scale, original_u1_flag=0):
    import struct
    qs = []
    for i in range(3):
        denom = fetch_scale * position_scale[i]
        if denom == 0:
            raise ValueError("invalid zero position quantization scale")
        q = round((position[i] - position_offset[i]) / denom)
        if not 0 <= q <= POSITION_MASK:
            raise ValueError(f"position component {i} outside 21-bit quantization range: {q}")
        qs.append(q)
    qx, qy, qz = qs
    u0 = ((qx & POSITION_MASK) << 11) | ((qy >> 10) & 0x7FF)
    u1 = (qz & POSITION_MASK) | ((qy & 0x3FF) << 21) | (original_u1_flag & 0x80000000)
    return struct.pack("<II", u0, u1)
