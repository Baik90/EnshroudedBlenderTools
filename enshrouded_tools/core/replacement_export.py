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
import uuid

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
    material_mesh_ranges: tuple[tuple[int, int, int], ...] = ()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class ColliderPatch:
    shape: str
    offset: tuple[float, float, float]
    orientation: tuple[float, float, float, float]
    dimensions: tuple[float, ...]


@dataclass(frozen=True)
class ColliderPatchGroup:
    template_guid: str
    template_name: str
    colliders: tuple[ColliderPatch, ...]


@dataclass(frozen=True)
class TexturePatch:
    material_index: int
    material_guid: str
    material_name: str
    slot_name: str
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def file_name(self) -> str:
        return f"{self.material_index}_{self.material_guid}_{self.slot_name}.bin"


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


def build_full_topology_payload(vertex_records, indices, material_mesh_ranges=()) -> ReplacementPayload:
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
    material_mesh_ranges = tuple(
        (int(material), int(offset), int(count))
        for material, offset, count in material_mesh_ranges
    )
    if not material_mesh_ranges:
        material_mesh_ranges = ((0, 0, len(indices)),)
    if any(offset < 0 or count <= 0 or offset + count > len(indices)
           for _material, offset, count in material_mesh_ranges):
        raise ValueError("material mesh range exceeds generated index data")
    if sum(count for _material, _offset, count in material_mesh_ranges) != len(indices):
        raise ValueError("material mesh ranges do not cover all generated indices")

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
        material_mesh_ranges=material_mesh_ranges,
    )


def _number(value: float) -> str:
    return format(float(value), ".17g")


def _collider_patch_lua(mod_id: str, groups) -> str:
    groups = tuple(groups)
    if not groups:
        return ""
    shape_types = {
        "BOX": "keen::ecs::BoxColliderData",
        "SPHERE": "keen::ecs::SphereColliderData",
        "CAPSULE": "keen::ecs::CapsuleColliderData",
    }
    group_literals = []
    for group in groups:
        collider_literals = []
        for collider in group.colliders:
            collider_type = shape_types[collider.shape]
            dimensions = ", ".join(_number(value) for value in collider.dimensions)
            offset = ", ".join(_number(value) for value in collider.offset)
            orientation = ", ".join(_number(value) for value in collider.orientation)
            collider_literals.append(
                "{ type = \"%s\", offset = {%s}, orientation = {%s}, dimensions = {%s} }"
                % (collider_type, offset, orientation, dimensions)
            )
        group_literals.append(
            "{ guid = \"%s\", name = %s, colliders = {%s} }"
            % (group.template_guid, json.dumps(group.template_name), ", ".join(collider_literals))
        )
    return f'''
local COLLIDER_GROUPS = {{{", ".join(group_literals)}}}

local function patch_template_colliders(group)
    local template_resource = game.assets.get_resource(
        group.guid, "keen::ecs::TemplateResource", 0
    )
    if template_resource == nil then
        error("[{mod_id}] target TemplateResource not found: " .. group.guid)
    end
    local template = template_resource.data
    local collider_component = nil
    for _, component in ipairs(template.components) do
        if component.type == "keen::ecs::ColliderResourceComponent" then
            collider_component = component.value
            break
        end
    end
    if collider_component == nil then
        error("[{mod_id}] ColliderResourceComponent not found: " .. group.guid)
    end

    local patch_index = 1
    for _, resource_data in ipairs(collider_component.colliders) do
        for _, collider_variant in ipairs(resource_data.dataArray) do
            local patch = group.colliders[patch_index]
            if patch == nil then
                error("[{mod_id}] Blender collider count is smaller than the template count")
            end
            if collider_variant.type ~= patch.type then
                error("[{mod_id}] collider shape mismatch at index " .. tostring(patch_index))
            end
            local collider = collider_variant.value
            collider.offset.x = patch.offset[1]
            collider.offset.y = patch.offset[2]
            collider.offset.z = patch.offset[3]
            collider.orientation.x = patch.orientation[1]
            collider.orientation.y = patch.orientation[2]
            collider.orientation.z = patch.orientation[3]
            collider.orientation.w = patch.orientation[4]
            if patch.type == "keen::ecs::BoxColliderData" then
                collider.shape.halfSize.x = patch.dimensions[1]
                collider.shape.halfSize.y = patch.dimensions[2]
                collider.shape.halfSize.z = patch.dimensions[3]
            elseif patch.type == "keen::ecs::SphereColliderData" then
                collider.shape.radius = patch.dimensions[1]
            elseif patch.type == "keen::ecs::CapsuleColliderData" then
                collider.shape.radius = patch.dimensions[1]
                collider.shape.length = patch.dimensions[2]
            end
            patch_index = patch_index + 1
        end
    end
    if patch_index - 1 ~= #group.colliders then
        error("[{mod_id}] Blender collider count is larger than the template count")
    end
    print("[{mod_id}] patched colliders: " .. group.name)
end

for _, group in ipairs(COLLIDER_GROUPS) do
    patch_template_colliders(group)
end
'''


def _texture_patch_lua(mod_id: str, patches) -> str:
    patches = tuple(patches)
    if not patches:
        return ""
    grouped = {}
    for patch in patches:
        grouped.setdefault(
            (patch.material_index, patch.material_guid, patch.material_name), []
        ).append(patch)
    group_literals = []
    for (material_index, material_guid, material_name), textures in sorted(grouped.items()):
        texture_literals = ", ".join(
            "{ slot = %s, file = %s }"
            % (
                json.dumps(patch.slot_name),
                json.dumps(f"textures/{patch.file_name}"),
            )
            for patch in textures
        )
        group_literals.append(
            "{ materialIndex = %d, materialGuid = \"%s\", materialName = %s, textures = {%s} }"
            % (material_index + 1, material_guid, json.dumps(material_name), texture_literals)
        )
    literals = ", ".join(group_literals)
    return f'''
local MATERIAL_PATCHES = {{{literals}}}

for _, patch in ipairs(MATERIAL_PATCHES) do
    local source_material = game.assets.get_resource(
        patch.materialGuid, "keen::RenderMaterialResource", 0
    )
    if source_material == nil then
        error("[{mod_id}] RenderMaterialResource not found: " .. patch.materialGuid)
    end
    local custom_material = game.assets.create_resource(
        source_material.data, "keen::RenderMaterialResource"
    )
    if custom_material == nil then
        error("[{mod_id}] could not create custom material: " .. patch.materialName)
    end
    for _, texture in ipairs(patch.textures) do
        local target_image = nil
        for _, image in ipairs(custom_material.data.images) do
            if image.debugName == texture.slot then
                target_image = image
                break
            end
        end
        if target_image == nil then
            error("[{mod_id}] material texture slot not found: " .. texture.slot)
        end
        local texture_buffer = io.read(texture.file)
        if texture_buffer == nil then
            error("[{mod_id}] could not read " .. texture.file)
        end
        local texture_content = game.assets.create_content(texture_buffer)
        if texture_content == nil then
            error("[{mod_id}] create_content failed for " .. texture.slot)
        end
        target_image.data = game.guid.to_content_hash(texture_content.guid)
        print("[{mod_id}] custom texture: " .. patch.materialName .. "/" .. texture.slot)
    end
    model.materials[patch.materialIndex].material = custom_material
    print("[{mod_id}] assigned custom material: " .. patch.materialName)
end
'''


def _new_model_registration_lua(
    mod_id: str,
    template_guid: str,
    item_guid: str,
    item_name: str,
    item_description: str,
    item_icon_file: str = "",
) -> str:
    recipe_guid = str(uuid.uuid5(uuid.UUID(item_guid), f"{mod_id}:recipe"))
    icon_patch = ""
    if item_icon_file:
        icon_patch = f'''
local icon_buffer = io.read({json.dumps(item_icon_file)})
if icon_buffer == nil then
    error("[{mod_id}] could not read custom item icon")
end
local decoded_icon = image.decode(icon_buffer, "png")
if decoded_icon == nil then
    error("[{mod_id}] could not decode custom item icon PNG")
end
if decoded_icon.width ~= 512 or decoded_icon.height ~= 512 then
    error("[{mod_id}] decoded custom item icon is not 512x512")
end
local encoded_icon = image.encode_texture(decoded_icon, "R8G8B8A8_unorm")
if encoded_icon == nil then
    error("[{mod_id}] could not encode custom item icon texture")
end
local icon_content = game.assets.create_content(encoded_icon)
if icon_content == nil then
    error("[{mod_id}] create_content failed for custom item icon")
end
local icon_resource = game.assets.create_resource({{
    data = game.guid.to_content_hash(icon_content.guid),
    debugName = "{mod_id}_icon",
    size = {{ x = 512, y = 512 }},
    type = "Texture2D",
    format = "R8G8B8A8_unorm",
    levelCount = 1,
    isTiled = false
}}, "keen::UiTextureResource")
custom_item.data.iconImage = icon_resource
print("[{mod_id}] EBT ICON created=" .. tostring(icon_resource.guid)
    .. " bytes=" .. tostring(icon_content.size))
'''
    item_name_lua = json.dumps(item_name, ensure_ascii=False)
    item_description_lua = json.dumps(item_description, ensure_ascii=False)
    return f'''
local source_template = game.assets.get_resource(
    "{template_guid}", "keen::ecs::TemplateResource", 0
)
if source_template == nil then
    error("[{mod_id}] base TemplateResource not found: {template_guid}")
end
local custom_template = game.assets.create_resource(
    source_template.data, "keen::ecs::TemplateResource"
)
custom_template.data.name = "{mod_id}"
local model_component_found = false
for _, component in ipairs(custom_template.data.components) do
    if component.type == "keen::ecs::ModelResource" then
        component.value.model = resource
        model_component_found = true
    end
end
if not model_component_found then
    error("[{mod_id}] base template has no ModelResource component")
end

local source_item = game.assets.get_resource("{item_guid}", "keen::ItemInfo", 0)
if source_item == nil then
    error("[{mod_id}] base ItemInfo not found: {item_guid}")
end
if source_item.data.equipment.placedEntity ~= source_template.guid then
    error("[{mod_id}] selected ItemInfo and placeable template do not match")
end
local custom_item = game.assets.create_resource(source_item.data, "keen::ItemInfo")
local custom_name_loca = game.assets.create_resource({{
    keenglish = {item_name_lua},
    description = "{mod_id} item name"
}}, "keen::LocaTag")
local custom_description_loca = game.assets.create_resource({{
    keenglish = {item_description_lua},
    description = "{mod_id} item description"
}}, "keen::LocaTag")
if custom_name_loca == nil or custom_description_loca == nil then
    error("[{mod_id}] could not create custom localization tags")
end

local function append_localized_text(content_hash, name_entry, description_entry)
    local content_guid = game.guid.from_content_hash(content_hash)
    local source_content = game.assets.get_content(content_guid)
    if source_content == nil then
        error("[{mod_id}] localization content not found: " .. tostring(content_guid))
    end
    local source_buffer = source_content:read_data()
    local localization_data = source_buffer:read_resource(
        "keen::LocaTagCollectionResourceData"
    )
    table.insert(localization_data.tags, name_entry)
    table.insert(localization_data.tags, description_entry)
    table.sort(localization_data.tags, function(left, right)
        return left.id.value < right.id.value
    end)
    local output_buffer = buffer.create()
    output_buffer:write_resource(
        "keen::LocaTagCollectionResourceData", localization_data
    )
    local output_content = game.assets.create_content(output_buffer)
    if output_content == nil then
        error("[{mod_id}] could not create extended localization content")
    end
    return game.guid.to_content_hash(output_content.guid)
end

local name_entry = {{
    id = {{ value = game.guid.hash(custom_name_loca.guid) }},
    text = {item_name_lua},
    arguments = {{}},
    genericArguments = 0
}}
local description_entry = {{
    id = {{ value = game.guid.hash(custom_description_loca.guid) }},
    text = {item_description_lua},
    arguments = {{}},
    genericArguments = 0
}}
local localization_contents_patched = 0
for _, localization in ipairs(
    game.assets.get_resources_by_type("keen::LocaTagCollectionResource")
) do
    localization.data.keenglishDataHash = append_localized_text(
        localization.data.keenglishDataHash, name_entry, description_entry
    )
    localization_contents_patched = localization_contents_patched + 1
    for _, language in ipairs(localization.data.languages) do
        language.dataHash = append_localized_text(
            language.dataHash, name_entry, description_entry
        )
        localization_contents_patched = localization_contents_patched + 1
    end
end
if localization_contents_patched == 0 then
    error("[{mod_id}] no localization collections were found")
end
print("[{mod_id}] EBT localization contents patched="
    .. tostring(localization_contents_patched)
    .. " nameId=" .. tostring(name_entry.id.value)
    .. " descriptionId=" .. tostring(description_entry.id.value))

custom_item.data.objectId = custom_item.guid
custom_item.data.itemId.value = game.guid.hash(custom_item.guid)
custom_item.data.name = custom_name_loca
custom_item.data.caption = custom_name_loca
custom_item.data.description = custom_description_loca
custom_item.data.equipment.placedEntity = custom_template
custom_item.data.equipment.visualModel = resource
custom_item.data.equipment.cursorModel = resource
custom_item.data.iconModel = resource
custom_item.data.debugName = "{mod_id}"
{icon_patch}

local item_registries = game.assets.get_resources_by_type("keen::ItemRegistryResource")
local item_registry = nil
for _, registry in ipairs(item_registries) do
    for _, item_ref in ipairs(registry.data.itemRefs) do
        if item_ref == source_item.guid then
            item_registry = registry
            break
        end
    end
    if item_registry ~= nil then break end
end
if item_registry == nil then
    error("[{mod_id}] registry containing the base ItemInfo was not found")
end
local source_item_registry = item_registry
item_registry = game.assets.create_resource(
    source_item_registry.data, "keen::ItemRegistryResource"
)
if item_registry == nil then
    error("[{mod_id}] could not clone the base ItemRegistryResource")
end
local item_count_before = #item_registry.data.itemRefs
table.insert(item_registry.data.itemRefs, custom_item)
table.insert(item_registry.data.dbgNames, "{mod_id}")
print("[{mod_id}] EBT DEBUG item registry=" .. tostring(item_registry.guid)
    .. " sourceRegistry=" .. tostring(source_item_registry.guid)
    .. " before=" .. tostring(item_count_before)
    .. " after=" .. tostring(#item_registry.data.itemRefs)
    .. " sourceId=" .. tostring(source_item.data.itemId.value)
    .. " customId=" .. tostring(custom_item.data.itemId.value))

local item_registry_rebinds = 0
local item_game_resource_types = {{
    "keen::Game38ClientResources",
    "keen::Game38ServerResources"
}}
for _, resource_type in ipairs(item_game_resource_types) do
    for _, game_resources in ipairs(game.assets.get_resources_by_type(resource_type)) do
        if game_resources.data.shared.itemRegistry == source_item_registry.guid then
            game_resources.data.shared.itemRegistry = item_registry
            item_registry_rebinds = item_registry_rebinds + 1
            print("[{mod_id}] EBT DEBUG rebound " .. resource_type
                .. " itemRegistry=" .. tostring(item_registry.guid))
        end
    end
end
if item_registry_rebinds == 0 then
    error("[{mod_id}] central item registry reference was not found")
end

local template_registry = nil
for _, registry in ipairs(game.assets.get_resources_by_type(
    "keen::ecs::TemplateCollectionResource"
)) do
    for _, template_ref in ipairs(registry.data.templates) do
        if template_ref == source_template.guid then
            template_registry = registry
            break
        end
    end
    if template_registry ~= nil then break end
end
if template_registry == nil then
    error("[{mod_id}] collection containing the base TemplateResource was not found")
end
local template_count_before = #template_registry.data.templates
table.insert(template_registry.data.templates, custom_template)
print("[{mod_id}] EBT DEBUG template registry=" .. tostring(template_registry.guid)
    .. " before=" .. tostring(template_count_before)
    .. " after=" .. tostring(#template_registry.data.templates))

local source_recipe_info = nil
local recipe_registry = nil
local recipe_candidate_count = 0
for _, registry in ipairs(game.assets.get_resources_by_type("keen::RecipeRegistryResource")) do
    for _, recipe_info in ipairs(registry.data.recipes) do
        for _, output in ipairs(recipe_info.output) do
            if output.itemRef == source_item.guid then
                recipe_candidate_count = recipe_candidate_count + 1
                print("[{mod_id}] EBT DEBUG recipe candidate="
                    .. tostring(recipe_candidate_count)
                    .. " registry=" .. tostring(registry.guid)
                    .. " guid=" .. tostring(recipe_info.recipeGuid)
                    .. " id=" .. tostring(recipe_info.recipeId.value)
                    .. " workshopGuid=" .. tostring(recipe_info.workshopGuid)
                    .. " workshopId=" .. tostring(recipe_info.workshopId.value)
                    .. " debugName=" .. tostring(recipe_info.debugName)
                    .. " knowledgeType=" .. tostring(recipe_info.knowledgeRequirement.type)
                    .. " knowledgeId="
                    .. tostring(recipe_info.knowledgeRequirement.knowledgeOrQueryId.value)
                    .. " compare=" .. tostring(recipe_info.knowledgeRequirement.compareOperator)
                    .. "/" .. tostring(recipe_info.knowledgeRequirement.compareValue))
                if source_recipe_info == nil then
                    source_recipe_info = recipe_info
                    recipe_registry = registry
                end
            end
        end
    end
end
if source_recipe_info == nil then
    error("[{mod_id}] no recipe outputs the selected base item")
end
print("[{mod_id}] EBT DEBUG selected recipe inputs="
    .. tostring(#source_recipe_info.input)
    .. " outputs=" .. tostring(#source_recipe_info.output)
    .. " requiredProps=" .. tostring(#source_recipe_info.requiredProps)
    .. " comfort=" .. tostring(source_recipe_info.comfortLevel)
    .. " level=" .. tostring(source_recipe_info.level))
for input_index, recipe_input in ipairs(source_recipe_info.input) do
    print("[{mod_id}] EBT DEBUG input=" .. tostring(input_index)
        .. " itemGuid=" .. tostring(recipe_input.itemStack.itemRef)
        .. " itemId=" .. tostring(recipe_input.itemStack.item.value)
        .. " itemCount=" .. tostring(recipe_input.itemStack.count)
        .. " categoryGuid=" .. tostring(recipe_input.inputItemCategory.categoryRef)
        .. " categoryId=" .. tostring(recipe_input.inputItemCategory.category.value)
        .. " categoryCount=" .. tostring(recipe_input.inputItemCategory.count))
end
for _, workshop_registry in ipairs(
    game.assets.get_resources_by_type("keen::WorkshopRegistryResource")
) do
    for _, workshop in ipairs(workshop_registry.data.workshops) do
        if workshop.workshopId.value == source_recipe_info.workshopId.value then
            print("[{mod_id}] EBT DEBUG workshop registry="
                .. tostring(workshop_registry.guid)
                .. " guid=" .. tostring(workshop.workshopGuid)
                .. " id=" .. tostring(workshop.workshopId.value)
                .. " nameId=" .. tostring(workshop.name.value)
                .. " itemGuid=" .. tostring(workshop.itemRef)
                .. " itemId=" .. tostring(workshop.item.value)
                .. " isNpc=" .. tostring(workshop.isNpc))
        end
    end
    for _, npc in ipairs(workshop_registry.data.npcs) do
        if npc.workshopId.value == source_recipe_info.workshopId.value then
            print("[{mod_id}] EBT DEBUG npc workshop registry="
                .. tostring(workshop_registry.guid)
                .. " guid=" .. tostring(npc.workshopGuid)
                .. " id=" .. tostring(npc.workshopId.value)
                .. " nameId=" .. tostring(npc.name.value)
                .. " itemGuid=" .. tostring(npc.itemRef))
        end
    end
end
local source_recipe_registry = recipe_registry
recipe_registry = game.assets.create_resource(
    source_recipe_registry.data, "keen::RecipeRegistryResource"
)
if recipe_registry == nil then
    error("[{mod_id}] could not clone the base RecipeRegistryResource")
end
local recipes = recipe_registry.data.recipes
local recipe_count_before = #recipes
table.insert(recipes, source_recipe_info)
local recipe_info = recipes[#recipes]
recipe_info.recipeGuid = "{recipe_guid}"
recipe_info.recipeId.value = game.guid.hash(recipe_info.recipeGuid)
recipe_info.recipeName = custom_name_loca
recipe_info.debugName = "{mod_id}"
recipe_info.knowledgeRequirement.type = "SimpleBool"
recipe_info.knowledgeRequirement.knowledgeOrQueryId.value = 0
recipe_info.knowledgeRequirement.compareOperator = "Equals"
recipe_info.knowledgeRequirement.compareValue = 0
recipe_info.knowledgeRequirement.isExplicitPlayerKnowledgeQuery = false
for _, output in ipairs(recipe_info.output) do
    if output.itemRef == source_item.guid then
        output.itemRef = custom_item
        output.item.value = custom_item.data.itemId.value
    end
end
print("[{mod_id}] EBT DEBUG recipe registry=" .. tostring(recipe_registry.guid)
    .. " sourceRegistry=" .. tostring(source_recipe_registry.guid)
    .. " before=" .. tostring(recipe_count_before)
    .. " after=" .. tostring(#recipes)
    .. " candidates=" .. tostring(recipe_candidate_count)
    .. " customId=" .. tostring(recipe_info.recipeId.value)
    .. " outputGuid=" .. tostring(custom_item.guid)
    .. " outputId=" .. tostring(custom_item.data.itemId.value)
    .. " knowledge=SimpleBool:0 Equals 0")

local recipe_registry_rebinds = 0
local game_resource_types = {{
    "keen::Game38ClientResources",
    "keen::Game38ServerResources"
}}
for _, resource_type in ipairs(game_resource_types) do
    for _, game_resources in ipairs(game.assets.get_resources_by_type(resource_type)) do
        if game_resources.data.shared.recipeRegistry == source_recipe_registry.guid then
            game_resources.data.shared.recipeRegistry = recipe_registry
            recipe_registry_rebinds = recipe_registry_rebinds + 1
            print("[{mod_id}] EBT DEBUG rebound " .. resource_type
                .. "=" .. tostring(game_resources.guid)
                .. " recipeRegistry=" .. tostring(recipe_registry.guid))
        end
    end
end
if recipe_registry_rebinds == 0 then
    error("[{mod_id}] central recipe registry reference was not found")
end

local recipe_ui_matches = 0
for _, ui_bundle in ipairs(game.assets.get_resources_by_type("keen::FbUiBundle")) do
    local recipe_data = ui_bundle.data.menu.crafting.recipes
    for workshop_index, recipe_tree in ipairs(recipe_data.trees) do
        local workshop_id = recipe_data.workshops[workshop_index]
        for group_index, recipe_group in ipairs(recipe_tree.groups) do
            for set_index, recipe_set in ipairs(recipe_group.sets) do
                local source_index = nil
                for recipe_index, recipe_id in ipairs(recipe_set.entries) do
                    if recipe_id.value == source_recipe_info.recipeId.value then
                        source_index = recipe_index
                        break
                    end
                end
                if source_index ~= nil then
                    table.insert(recipe_set.entries, source_index + 1, recipe_info.recipeId)
                    recipe_ui_matches = recipe_ui_matches + 1
                    print("[{mod_id}] EBT DEBUG recipe UI added"
                        .. " resource=" .. tostring(ui_bundle.guid)
                        .. " workshop=" .. tostring(workshop_index)
                        .. "/" .. tostring(workshop_id.value)
                        .. " group=" .. tostring(group_index)
                        .. "/" .. tostring(recipe_group.groupId)
                        .. " set=" .. tostring(set_index)
                        .. "/" .. tostring(recipe_set.recipeSetId)
                        .. " sourceIndex=" .. tostring(source_index)
                        .. " customId=" .. tostring(recipe_info.recipeId.value)
                        .. " entries=" .. tostring(#recipe_set.entries))
                end
            end
        end
    end
end
if recipe_ui_matches == 0 then
    error("[{mod_id}] source recipe was not found in the crafting UI data")
end
print("[{mod_id}] EBT DEBUG recipe UI summary matches="
    .. tostring(recipe_ui_matches))

print("[{mod_id}] registered new model=" .. tostring(resource.guid)
    .. " template=" .. tostring(custom_template.guid)
    .. " item=" .. tostring(custom_item.guid)
    .. " recipe=" .. tostring(recipe_info.recipeGuid))
'''


def make_mod_lua(
    mod_id: str,
    model_guid: str,
    payload_file: str,
    replacement: ReplacementPayload,
    collider_groups=(),
    texture_patches=(),
    new_model_template_guid="",
    new_model_item_guid="",
    item_name="Custom Item",
    item_description="Custom item created with Enshrouded Blender Tools.",
    item_icon_file="",
) -> str:
    offset = replacement.position_offset
    scale = replacement.position_scale
    minimum = replacement.bounds_min
    maximum = replacement.bounds_max
    center = replacement.sphere_center
    radius = replacement.sphere_radius
    topology_patch = ""
    if replacement.full_topology:
        mesh_ranges = replacement.material_mesh_ranges
        mesh_patch_lines = []
        for mesh_index, (material_index, index_offset, index_count) in enumerate(mesh_ranges, 1):
            mesh_patch_lines.append(f'''local replacement_mesh_{mesh_index} = model.meshes[{mesh_index}]
replacement_mesh_{mesh_index}.materialIndex = {material_index}
replacement_mesh_{mesh_index}.vertexBufferIndex = 0
replacement_mesh_{mesh_index}.vertexOffset = 0
replacement_mesh_{mesh_index}.indexOffset = {index_offset}
replacement_mesh_{mesh_index}.indexCount = {index_count}''')
        mesh_patch = "\n\n".join(mesh_patch_lines)
        topology_patch = f'''
if #model.vertexBuffers < 1 or #model.meshes < {len(mesh_ranges)} or #model.lods < 1 then
    error("[{mod_id}] target RenderModel has no reusable static mesh layout")
end
if #model.materials < {max(material for material, _offset, _count in mesh_ranges) + 1} then
    error("[{mod_id}] target RenderModel does not contain all used material slots")
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

{mesh_patch}

for _, lod in ipairs(model.lods) do
    lod.firstMeshIndex = 0
    lod.meshCount = {len(mesh_ranges)}
end
'''
    collider_patch = _collider_patch_lua(mod_id, collider_groups)
    texture_patch = _texture_patch_lua(mod_id, texture_patches)
    new_model_patch = (
        _new_model_registration_lua(
            mod_id,
            new_model_template_guid,
            new_model_item_guid,
            item_name,
            item_description,
            item_icon_file,
        )
        if new_model_template_guid else ""
    )
    resource_setup = f'''local source_resource = game.assets.get_resource(MODEL_GUID, MODEL_TYPE, 0)
if source_resource == nil then
    error("[{mod_id}] base RenderModel not found: " .. MODEL_GUID)
end
local resource = game.assets.create_resource(source_resource.data, MODEL_TYPE)''' if new_model_template_guid else f'''local resource = game.assets.get_resource(MODEL_GUID, MODEL_TYPE, 0)
if resource == nil then
    error("[{mod_id}] target RenderModel not found: " .. MODEL_GUID)
end'''
    return f'''-- Generated by Enshrouded Blender Tools
-- {'New model/recipe experimental' if new_model_template_guid else ('Full-topology experimental' if replacement.full_topology else 'Topology-preserving replacement')}.

local MODEL_GUID = "{model_guid}"
local MODEL_TYPE = "keen::RenderModel"
local MESH_FILE = "{payload_file}"

print("[{mod_id}] loading")

{resource_setup}

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

{collider_patch}

{texture_patch}

{new_model_patch}

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


def make_validation_json(
    model_guid: str,
    model_name: str,
    replacement: ReplacementPayload,
    collider_groups=(),
    texture_patches=(),
    new_model_template_guid="",
    new_model_item_guid="",
    item_name="",
    item_description="",
    item_icon_data=b"",
) -> str:
    return json.dumps(
        {
            "mesh_size": len(replacement.data),
            "mesh_sha256": replacement.sha256,
            "target_guid": model_guid,
            "target_type": "keen::RenderModel",
            "target_part": 0,
            "model_name": model_name,
            "new_model": bool(new_model_template_guid),
            "base_template_guid": new_model_template_guid,
            "base_item_guid": new_model_item_guid,
            "item_name": item_name,
            "item_description": item_description,
            "item_icon": (
                {
                    "file": "item_icon.png",
                    "size": len(item_icon_data),
                    "sha256": hashlib.sha256(item_icon_data).hexdigest(),
                    "width": 512,
                    "height": 512,
                    "format": "R8G8B8A8_unorm",
                }
                if item_icon_data else None
            ),
            "vertex_count": replacement.vertex_count,
            "index_count": replacement.index_count,
            "full_topology": replacement.full_topology,
            "vertex_data_size": replacement.vertex_data_size,
            "vertex_stride": replacement.vertex_stride,
            "material_mesh_ranges": replacement.material_mesh_ranges,
            "positionOffset": replacement.position_offset,
            "positionScale": replacement.position_scale,
            "boundingBoxMin": replacement.bounds_min,
            "boundingBoxMax": replacement.bounds_max,
            "boundingSphere": (*replacement.sphere_center, replacement.sphere_radius),
            "collider_templates": [
                {
                    "guid": group.template_guid,
                    "name": group.template_name,
                    "collider_count": len(group.colliders),
                }
                for group in collider_groups
            ],
            "texture_patches": [
                {
                    "material_guid": patch.material_guid,
                    "material_index": patch.material_index,
                    "material_name": patch.material_name,
                    "slot": patch.slot_name,
                    "size": len(patch.data),
                    "sha256": patch.sha256,
                }
                for patch in texture_patches
            ],
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
    collider_groups=(),
    texture_patches=(),
    new_model_template_guid="",
    new_model_item_guid="",
    item_name="",
    item_description="",
    item_icon_data=b"",
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
        if texture_patches:
            (staging / "textures").mkdir()
            for patch in texture_patches:
                (staging / "textures" / patch.file_name).write_bytes(patch.data)
        (staging / payload_file).write_bytes(replacement.data)
        if item_icon_data:
            (staging / "item_icon.png").write_bytes(item_icon_data)
        (staging / "mod.json").write_text(
            make_mod_json(mod_id, mod_name, version, author, model_name),
            encoding="utf-8",
        )
        (staging / "validation.json").write_text(
            make_validation_json(
                model_guid,
                model_name,
                replacement,
                collider_groups,
                texture_patches,
                new_model_template_guid,
                new_model_item_guid,
                item_name,
                item_description,
                item_icon_data,
            ),
            encoding="utf-8",
        )
        (staging / "src" / "mod.lua").write_text(
            make_mod_lua(
                mod_id,
                model_guid,
                payload_file,
                replacement,
                collider_groups,
                texture_patches,
                new_model_template_guid,
                new_model_item_guid,
                item_name,
                item_description,
                "item_icon.png" if item_icon_data else "",
            ),
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
