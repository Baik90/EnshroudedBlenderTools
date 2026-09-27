"""Existing entity audio donors; playback lifecycle must be verified in game."""
import uuid
from .collision import TEMPLATE_RESOURCE_TYPE_HASH, _relative_array, _variant_target, _relative_string, _fnv1a32


def list_audio_donors(reader):
    result = []
    for index, rid in enumerate(reader.resource_ids):
        if rid.part_index or rid.type_hash != TEMPLATE_RESOURCE_TYPE_HASH:
            continue
        p = reader.read_resource(index)
        start, count = _relative_array(p, 12, 12)
        audio, resources = [], []
        for i in range(count):
            kind, body, size = _variant_target(p, start + i * 12)
            if kind == _fnv1a32('keen::ecs::AudioComponent') and size >= 56:
                audio.append(i)
            if kind == _fnv1a32('keen::ecs::AudioResourceComponent') and size >= 16:
                resources.append(str(uuid.UUID(bytes_le=p[body:body+16])))
        if len(audio) == len(resources) == 1 and resources[0] != str(uuid.UUID(int=0)):
            result.append((rid.guid, (_relative_string(p, 0) or rid.guid) + ' [' + rid.guid[:8] + ']'))
    return sorted(result, key=lambda x: x[1].casefold())


def idle_audio_lua(guid):
    uuid.UUID(guid)
    return f'''
-- Experimental: the source sound determines looping behavior.
local audio_donor = game.assets.get_resource("{guid}", "keen::ecs::TemplateResource", 0)
if audio_donor == nil then error("Idle audio template missing") end
local audio_component, audio_resource = nil, nil
local audio_count, resource_count = 0, 0
for _, c in ipairs(audio_donor.data.components) do
    if c.type == "keen::ecs::AudioComponent" then audio_component = c; audio_count = audio_count + 1 end
    if c.type == "keen::ecs::AudioResourceComponent" then audio_resource = c; resource_count = resource_count + 1 end
end
if audio_count ~= 1 or resource_count ~= 1 then error("Idle audio donor must contain exactly one audio pair") end
for _, c in ipairs(custom_template.data.components) do
    if c.type == "keen::ecs::AudioComponent" or c.type == "keen::ecs::AudioResourceComponent" then
        error("Weapon template already contains audio; refusing ambiguous audio replacement")
    end
end
table.insert(custom_template.data.components, audio_component)
local idle_component = custom_template.data.components[#custom_template.data.components]
idle_component.value.stopOnDestroy = true
idle_component.value.attach = true
idle_component.value.offset.localOffset = {{x=0, y=0, z=0}}
idle_component.value.offset.worldOffset = {{x=0, y=0, z=0}}
table.insert(custom_template.data.components, audio_resource)
print("Idle audio attached from template {guid}; verify draw/sheath lifecycle")
'''


def idle_audio_layers_lua(guids):
    """Experimental merged sound entries; first donor supplies spatial settings."""
    guids = [str(uuid.UUID(g)) for g in guids]
    if not guids:
        return ''
    result = idle_audio_lua(guids[0])
    if len(guids) == 1:
        return result
    import json
    return result + '''
do
    local mixed = nil
    local target = nil
    for _, c in ipairs(custom_template.data.components) do
        if c.type == "keen::ecs::AudioResourceComponent" then target = c end
    end
    if target == nil then error("Idle layers: target audio missing") end
    local donors = ''' + '{' + ','.join(json.dumps(g) for g in guids) + '}' + '''
    for index, guid in ipairs(donors) do
        local donor = game.assets.get_resource(guid, "keen::ecs::TemplateResource", 0)
        if donor == nil then error("Idle layers: donor missing") end
        local ref, count = nil, 0
        for _, c in ipairs(donor.data.components) do
            if c.type == "keen::ecs::AudioResourceComponent" then ref=c.value.soundContainer; count=count+1 end
        end
        if count ~= 1 then error("Idle layers: ambiguous donor") end
        local sound = game.assets.get_resource(ref, "keen::SoundContainerResource", 0)
        if sound == nil then error("Idle layers: sound missing") end
        if index == 1 then
            mixed = game.assets.create_resource(sound.data, "keen::SoundContainerResource")
            if mixed == nil then error("Idle layers: clone failed") end
        else
            for _, entry in ipairs(sound.data.entries) do table.insert(mixed.data.entries, entry) end
        end
    end
    target.value.soundContainer = mixed.guid
    print("Idle audio layers experimental: " .. tostring(#donors) .. "; verify overlap and sheath stop")
end
'''
