"""Experimental four-influence skinning, verified on armor_m_ear_garments_01_chest."""
import struct
import uuid
from .collision import _relative_array


def read_skinning(reader, descriptor, model, render_data):
    if len(descriptor) < 316:
        return None
    offset, size = struct.unpack_from('<II', descriptor, 164)
    if not size:
        return None
    count = sum(v.data_size // v.stride for v in model.vertex_buffers)
    if size != count * 8 or offset + size > len(render_data):
        raise ValueError('Unsupported skinning stream size')
    joint_count, hierarchy_count = struct.unpack_from('<HH', descriptor, 312)
    start, map_count = _relative_array(descriptor, 260, 2)
    if map_count != joint_count:
        raise ValueError('Skinning joint count does not match palette')
    palette = struct.unpack_from(f'<{map_count}H', descriptor, start)
    guid = str(uuid.UUID(bytes_le=descriptor[148:164]))
    hierarchy = reader.read_resource(reader.find_resource_index(guid, 897872094))
    start, name_count = _relative_array(hierarchy, 16, 4)
    if name_count != hierarchy_count or any(j >= name_count for j in palette):
        raise ValueError('Skinning palette exceeds hierarchy')
    hashes = struct.unpack_from(f'<{name_count}I', hierarchy, start)
    names = tuple(f'joint_{j:03d}_{hashes[j]:08x}' for j in palette)
    weights = []
    for vertex in range(count):
        record = render_data[offset + vertex * 8:offset + (vertex + 1) * 8]
        if sum(record[4:]) != 255:
            raise ValueError('Unsupported skinning weight normalization')
        influences = {}
        for bone, weight in zip(record[:4], record[4:]):
            if not weight:
                continue
            if bone >= map_count:
                raise ValueError('Skinning bone index exceeds palette')
            influences[bone] = influences.get(bone, 0) + weight / 255.0
        weights.append(tuple(influences.items()))
    return guid, names, tuple(weights)
