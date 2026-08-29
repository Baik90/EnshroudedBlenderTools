from dataclasses import dataclass
import struct
import uuid


TEMPLATE_RESOURCE_TYPE_HASH = 0x39768775
COLLIDER_COMPONENT_TYPE_HASH = 0x0E420682

COLLIDER_TYPES = {}


@dataclass(frozen=True)
class Collider:
    shape: str
    offset: tuple[float, float, float]
    orientation: tuple[float, float, float, float]
    dimensions: tuple[float, ...]
    template_name: str
    template_guid: str


def _fnv1a32(value: str) -> int:
    result = 0x811C9DC5
    for byte in value.encode("utf-8"):
        result = ((result ^ byte) * 0x01000193) & 0xFFFFFFFF
    return result


COLLIDER_TYPES.update({
    _fnv1a32("keen::ecs::SphereColliderData"): "SPHERE",
    _fnv1a32("keen::ecs::SpheroidColliderData"): "SPHEROID",
    _fnv1a32("keen::ecs::CylinderColliderData"): "CYLINDER",
    _fnv1a32("keen::ecs::CapsuleColliderData"): "CAPSULE",
    _fnv1a32("keen::ecs::TaperedCapsuleColliderData"): "TAPERED_CAPSULE",
    _fnv1a32("keen::ecs::BoxColliderData"): "BOX",
})


def _relative_array(payload: bytes, field_offset: int, stride: int) -> tuple[int, int]:
    relative, count = struct.unpack_from("<II", payload, field_offset)
    start = field_offset + relative if relative else 0
    if count and (not start or start + count * stride > len(payload)):
        raise ValueError(f"Collider array at 0x{field_offset:x} exceeds TemplateResource")
    return start, count


def _relative_string(payload: bytes, field_offset: int) -> str:
    relative, size = struct.unpack_from("<II", payload, field_offset)
    start = field_offset + relative if relative else 0
    if not start or start + size > len(payload):
        return ""
    return payload[start:start + size].rstrip(b"\0").decode("utf-8", errors="replace")


def _variant_target(payload: bytes, descriptor_offset: int) -> tuple[int, int, int]:
    type_hash, relative, size = struct.unpack_from("<III", payload, descriptor_offset)
    target = descriptor_offset + 4 + relative if relative else 0
    if not target or target + size > len(payload):
        raise ValueError(f"Collider variant at 0x{descriptor_offset:x} exceeds TemplateResource")
    return type_hash, target, size


def _parse_shape(payload: bytes, offset: int, size: int, shape: str) -> tuple[float, ...]:
    shape_offset = offset + 80
    available = offset + size - shape_offset
    counts = {
        "SPHERE": 1,
        "SPHEROID": 2,
        "CYLINDER": 2,
        "CAPSULE": 2,
        "TAPERED_CAPSULE": 3,
        "BOX": 3,
    }
    count = counts[shape]
    if available < count * 4:
        raise ValueError(f"{shape} collider body is too small ({size} bytes)")
    return struct.unpack_from(f"<{count}f", payload, shape_offset)


def parse_template_colliders(payload: bytes, template_guid: str) -> tuple[Collider, ...]:
    """Parse primitive gameplay colliders from a keen::ecs::TemplateResource."""
    if len(payload) < 20:
        return ()
    template_name = _relative_string(payload, 0) or template_guid
    component_start, component_count = _relative_array(payload, 12, 12)
    colliders = []
    for component_index in range(component_count):
        descriptor = component_start + component_index * 12
        type_hash, component_offset, _size = _variant_target(payload, descriptor)
        if type_hash != COLLIDER_COMPONENT_TYPE_HASH:
            continue

        resource_start, resource_count = _relative_array(payload, component_offset, 56)
        for resource_index in range(resource_count):
            resource_offset = resource_start + resource_index * 56
            data_start, data_count = _relative_array(payload, resource_offset, 12)
            for data_index in range(data_count):
                type_hash, body_offset, body_size = _variant_target(
                    payload, data_start + data_index * 12
                )
                shape = COLLIDER_TYPES.get(type_hash)
                if shape is None:
                    continue
                if body_size < 80:
                    raise ValueError(f"{shape} collider header is truncated")
                offset = struct.unpack_from("<3f", payload, body_offset + 8)
                orientation = struct.unpack_from("<4f", payload, body_offset + 20)
                dimensions = _parse_shape(payload, body_offset, body_size, shape)
                colliders.append(Collider(
                    shape=shape,
                    offset=offset,
                    orientation=orientation,
                    dimensions=dimensions,
                    template_name=template_name,
                    template_guid=template_guid,
                ))
    return tuple(colliders)


def find_model_colliders(reader, model_guid: str) -> tuple[Collider, ...]:
    """Find TemplateResources that directly reference a RenderModel GUID."""
    model_bytes = uuid.UUID(model_guid).bytes_le
    found = []
    for index, resource_id in enumerate(reader.resource_ids):
        if resource_id.type_hash != TEMPLATE_RESOURCE_TYPE_HASH or resource_id.part_index != 0:
            continue
        payload = reader.read_resource(index)
        if model_bytes not in payload:
            continue
        found.extend(parse_template_colliders(payload, resource_id.guid))
    return tuple(found)
