"""Opt-in placeable behavior and stable asset identities, independent of bpy."""
import json
import math
import uuid
from .collision import _fnv1a32, _relative_string, _relative_array, _variant_target

# Existing tested stool chain supplies the low-level placement/item structure.
# Its behavior is explicitly stripped before opt-in functions are applied.
BASE_TEMPLATE = 'e6da1bf1-0134-46f5-888a-e94054207c20'
BASE_ITEM = 'dc4a7cc1-81c3-4a05-ac41-9e01724418ed'
BASE_MODEL = '98b0ca77-872a-492d-b051-9b06fc8f495c'


def damage_feedback_donor(reader, material):
    """Resolve a native feedback component instead of guessing material IDs."""
    susceptibility = {'WOOD': 1, 'STONE': 2, 'METAL': 3}.get(material)
    if susceptibility is None:
        raise ValueError('Unsupported gameplay material: ' + str(material))
    templates = [(i, rid) for i, rid in enumerate(reader.resource_ids)
                 if rid.part_index == 0 and rid.type_hash == _fnv1a32('keen::ecs::TemplateResource')]
    templates.sort(key=lambda entry: (entry[1].guid != BASE_TEMPLATE, entry[1].guid))
    for index, rid in templates:
        p = reader.read_resource(index)
        start, count = _relative_array(p, 16 if reader.format == 'KFC4' else 12, 12)
        for n in range(count):
            kind, body, size = _variant_target(p, start+n*12)
            if kind == _fnv1a32('keen::ecs::CollisionFeedbackMaterialComponent') and size >= 44:
                if p[body+36] == susceptibility and any(p[body:body+16]):
                    return rid.guid
    raise ValueError('No native collision feedback donor found for ' + material)


def identities(object_guid):
    root = uuid.UUID(object_guid)
    return {key: str(uuid.uuid5(root, key)) for key in
            ('model', 'template', 'item', 'name', 'description', 'recipe')}


def list_vfx(reader):
    result = []
    owners = {}
    if reader.format == 'KFC4':
        # VfxResource no longer has debugName. Template references provide a
        # useful label without interpreting unrelated bytes as a string.
        for i, resource in enumerate(reader.resource_ids):
            if resource.part_index or resource.type_hash != _fnv1a32('keen::ecs::TemplateResource'):
                continue
            payload = reader.read_resource(i)
            name = _relative_string(payload, 0) or resource.guid
            start, count = _relative_array(payload, 16, 12)
            for n in range(count):
                kind, body, size = _variant_target(payload, start+n*12)
                if kind == _fnv1a32('keen::ecs::VfxComponentResource') and size >= 16:
                    owners.setdefault(str(uuid.UUID(bytes_le=payload[body:body+16])), name)
    for i, resource in enumerate(reader.resource_ids):
        if resource.part_index == 0 and resource.type_hash == _fnv1a32('keen::VfxResource'):
            if reader.format == 'KFC4':
                name = owners.get(resource.guid, 'FX ' + resource.guid)
            else:
                payload = reader.read_resource(i)
                name = _relative_string(payload, 116) or resource.guid
            result.append((name, resource.guid))
    return sorted(result, key=lambda row: row[0].casefold())


def stable_resource_lua(code, object_guid):
    ids = identities(object_guid)
    replacements = (
        ('game.assets.create_resource(source_resource.data, MODEL_TYPE)',
         'game.assets.create_resource(source_resource.data, MODEL_TYPE, "' + ids['model'] + '", 0)'),
        ('source_template.data, "keen::ecs::TemplateResource"\n)',
         'source_template.data, "keen::ecs::TemplateResource", "' + ids['template'] + '", 0\n)'),
        ('game.assets.create_resource(source_item.data, "keen::ItemInfo")',
         'game.assets.create_resource(source_item.data, "keen::ItemInfo", "' + ids['item'] + '", 0)'),
    )
    for old, new in replacements:
        if code.count(old) != 1:
            raise ValueError('Simple object resource generator changed')
        code = code.replace(old, new)
    if code.count('}, "keen::LocaTag")') != 2:
        raise ValueError('Simple object localization generator changed')
    for key in ('name', 'description'):
        code = code.replace('}, "keen::LocaTag")', '}, "keen::LocaTag", "' + ids[key] + '", 0)', 1)
    return code


def function_lua(functions):
    if sum(f['kind'] == 'DESTRUCTIBLE' for f in functions) > 1:
        raise ValueError('Only one Destructible function is supported per object')
    if sum(f['kind'] == 'SEAT' for f in functions) > 1:
        raise ValueError('Only one seating function is supported per object')
    if sum(f['kind'] == 'FX' for f in functions) > 1:
        raise ValueError('Only one FX component pair is supported per object')
    lines = ['''-- Minimal decoration: retain only placement/render infrastructure.
local decoration_components = {
 ["keen::ecs::Ao"]=true, ["keen::ecs::ModelComponent"]=true,
 ["keen::ecs::ModelResource"]=true, ["keen::ecs::ModelRenderHint"]=true,
 ["keen::ecs::CurrentTransform"]=true, ["keen::ecs::StaticTransform"]=true,
 ["keen::ecs::RenderTransform"]=true, ["keen::ecs::TintColor"]=true,
 ["keen::ecs::Debug"]=true, ["keen::ecs::UiOffsets"]=true,
 ["keen::ecs::Destructible"]=true
}
for i = #custom_template.data.components, 1, -1 do
 if not decoration_components[custom_template.data.components[i].type] then
  table.remove(custom_template.data.components, i)
 end
end
-- Decoration remains recoverable without inheriting the donor's loot/notifiers.
table.insert(custom_template.data.components, {type="keen::ecs::DismantleOverride", value={
 overrideMethod=true, method="PickUp", overrideVolumeClass=false, volumeClass="Small",
 ignoreBuildZoneChecks=false, preventDismantlingWithFilledInventory=true}})
''']
    colliders = [f for f in functions if f['kind'] == 'COLLIDER']
    if colliders:
        lines.append('''-- Reuse donor collision flags, but replace all donor geometry.
local collision_types = {
 ["keen::ecs::ColliderResourceComponent"]=true,
 ["keen::ecs::StaticCollider"]=true, ["keen::ecs::StaticClientCollider"]=true,
 ["keen::ecs::MovementColliderConfig"]=true,
 ["keen::ecs::CollisionFeedbackMaterialComponent"]=true
}
local collider_component = nil
for _, component in ipairs(source_template.data.components) do
 if collision_types[component.type] then
  table.insert(custom_template.data.components, component)
  if component.type == "keen::ecs::ColliderResourceComponent" then
   collider_component = custom_template.data.components[#custom_template.data.components].value
  end
 end
end
if collider_component == nil then error("Decoration collision donor is missing") end
local donor_group, donor_box = nil, nil
for _, component in ipairs(source_template.data.components) do
 if component.type == "keen::ecs::ColliderResourceComponent" then
  for _, group in ipairs(component.value.colliders) do
   for _, shape in ipairs(group.dataArray) do
    if shape.type == "keen::ecs::BoxColliderData" then
     donor_group, donor_box = group, shape
     break
    end
   end
   if donor_box ~= nil then break end
  end
 end
end
if donor_box == nil then error("Decoration collision donor has no box") end
for i = #collider_component.colliders, 1, -1 do table.remove(collider_component.colliders, i) end
table.insert(collider_component.colliders, donor_group)
local custom_shapes = collider_component.colliders[1].dataArray
for i = #custom_shapes, 1, -1 do table.remove(custom_shapes, i) end
''')
    for f in functions:
        if f['kind'] == 'DESTRUCTIBLE':
            health = f['max_health']
            if isinstance(health, bool) or not isinstance(health, int) or not 1 <= health <= 65535:
                raise ValueError('Max Health must be an integer between 1 and 65535')
            material = {'WOOD': 'Wood', 'STONE': 'Stone', 'METAL': 'Metal'}.get(f['material'])
            if material is None:
                raise ValueError('Unsupported gameplay material')
            donor = str(uuid.UUID(f['donor_template']))
            lines.append('''do
 local health_found, feedback = false, nil
 for _, component in ipairs(custom_template.data.components) do
  if component.type == "keen::ecs::Destructible" then
   component.value.maxHealth = ''' + str(health) + '''
   health_found = true
  elseif component.type == "keen::ecs::CollisionFeedbackMaterialComponent" then
   feedback = component.value
  end
 end
 if not health_found then error("Destructible donor component missing") end
 if feedback == nil then error("Destructible requires Collider function") end
 local donor = game.assets.get_resource(''' + json.dumps(donor) + ''', "keen::ecs::TemplateResource", 0)
 if donor == nil then error("Gameplay material donor missing") end
 local material_found = false
 for _, component in ipairs(donor.data.components) do
  if component.type == "keen::ecs::CollisionFeedbackMaterialComponent" then
   if component.value.propDamageSusceptibility ~= "''' + material + '''" then
    error("Gameplay material donor changed; re-export the object")
   end
   feedback.material = component.value.material
   feedback.materialId = component.value.materialId
   feedback.propDamageSusceptibility = component.value.propDamageSusceptibility
   material_found = true
  end
 end
 if not material_found then error("Gameplay material donor has no feedback component") end
''')
            if f.get('destruction_effects', False):
                lines.append('''local destruction_found = false
 for _, component in ipairs(source_template.data.components) do
  if component.type == "keen::ecs::OnDestroy" then
   table.insert(custom_template.data.components, component)
   destruction_found = true
  end
 end
 if not destruction_found then error("Base destruction effects missing") end
''')
            lines.append('end\n')
            continue
        position, rotation = f['position'], f['rotation']
        if len(position) != 3 or len(rotation) != 4 or not all(math.isfinite(v) for v in (*position, *rotation)):
            raise ValueError('Invalid function anchor transform')
        x, y, z = position
        qx, qy, qz, qw = rotation
        offset = ('{localOffset={x=%r,y=%r,z=%r},worldOffset={x=0,y=0,z=0},'
                  'orientationOffset={x=%r,y=%r,z=%r,w=%r}}') % (x, y, z, qx, qy, qz, qw)
        if f['kind'] == 'COLLIDER':
            dimensions = f['dimensions']
            if len(dimensions) != 3 or not all(math.isfinite(v) and v > 0 for v in dimensions):
                raise ValueError('Collider dimensions must be finite and positive')
            hx, hy, hz = dimensions
            lines.append('''do
 table.insert(custom_shapes, donor_box)
 local box = custom_shapes[#custom_shapes].value
 box.offset = {x=%r,y=%r,z=%r}
 box.orientation = {x=%r,y=%r,z=%r,w=%r}
 box.shape.halfSize = {x=%r,y=%r,z=%r}
end
''' % (x,y,z,qx,qy,qz,qw,hx,hy,hz))
        elif f['kind'] == 'SEAT':
            lines.append('''do
 local seat_types = {
 ["keen::ecs::InteractionAttachment"]=true, ["keen::ecs::InteractionOffer"]=true,
 ["keen::ecs::InteractionOfferRuntime"]=true,
 ["keen::ecs::ClientInteractionOffer"]=true, ["keen::ecs::InteractionLock"]=true,
 ["keen::ecs::ClientInteractionLock"]=true, ["keen::ecs::CheckPlayerInRange"]=true,
 ["keen::ecs::IsInWaterCheck"]=true,
 ["keen::ecs::ServerTarget"]=true, ["keen::ecs::ActiveNpcTarget"]=true
 }
 local attachment_count, offer_count = 0, 0
 local water_check_count, needs_water_check = 0, false
 for _, component in ipairs(source_template.data.components) do
  if seat_types[component.type] then
   table.insert(custom_template.data.components, component)
   local added = custom_template.data.components[#custom_template.data.components]
   if added.type == "keen::ecs::InteractionAttachment" then
    added.value.guestOffset = ''' + offset + '''
    attachment_count = attachment_count + 1
   elseif added.type == "keen::ecs::InteractionOffer" or added.type == "keen::ecs::InteractionOfferRuntime" then
    offer_count = offer_count + 1
   elseif added.type == "keen::ecs::InteractionLock" then
    needs_water_check = added.value.enableWaterLock
   elseif added.type == "keen::ecs::IsInWaterCheck" then
    water_check_count = water_check_count + 1
   end
  end
 end
 if attachment_count ~= 1 or offer_count ~= 1 then error("Seat donor layout changed; use Legacy mode") end
 if needs_water_check and water_check_count ~= 1 then
  error("Seat donor water lock requires exactly one IsInWaterCheck")
 end
 -- UI position is independent of the effect attachment and the donor's seat.
 local prompt_found = false
 for _, component in ipairs(custom_template.data.components) do
  if component.type == "keen::ecs::UiOffsets" then
   component.value.interactionPromptOffset = {localOffset={x=''' + repr(x) + ''',y=''' + repr(y) + ''',z=''' + repr(z) + '''},
    worldOffset={x=0,y=0.6,z=0},orientationOffset={x=0,y=0,z=0,w=1}}
   prompt_found = true
  end
 end
 if not prompt_found then error("Seat donor has no UiOffsets component") end
end
''')
        elif f['kind'] == 'FX':
            effect = str(uuid.UUID(f['guid']))
            lines.append('''do
 local effect = game.assets.get_resource(''' + json.dumps(effect) + ''', "keen::VfxResource", 0)
 if effect == nil then error("Object FX resource missing") end
 table.insert(custom_template.data.components, {type="keen::ecs::VfxComponent", value={
 fxHandle={value=0}, toggleModifier={},
 attachmentOffset=''' + offset + ''', slot="Root", attachedToEntity="Self", attachToParent=false}})
 table.insert(custom_template.data.components, {type="keen::ecs::VfxComponentResource", value={vfx=effect.guid}})
end
''')
        else:
            raise ValueError('Unsupported object function')
    # All 12,267 original KFC4 TemplateResources inspected use qualified-name
    # order. Appending optional components must not leave a noncanonical array.
    # Sort only after all writes: earlier code keeps references to inserted data.
    lines.append('''-- Match the original TemplateResource component order.
table.sort(custom_template.data.components, function(left, right)
 return left.type < right.type
end)
for i = 2, #custom_template.data.components do
 if custom_template.data.components[i-1].type == custom_template.data.components[i].type then
  error("Duplicate decoration component: " .. custom_template.data.components[i].type)
 end
end
''')
    return '\n'.join(lines)
