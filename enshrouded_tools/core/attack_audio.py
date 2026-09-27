"""Isolated A/B test for the first light sword attack; build 1076226."""
import struct
import uuid
from .collision import _relative_array, _relative_string, _variant_target, _fnv1a32

SEQUENCE = '23542042-4376-4ded-afc9-5d99cfd95aff'
SOURCE_SOUND = '2545c5f6-a36d-425b-95ee-64e69e04d33e'
TEST_SOUND = '3bd1393e-9a96-49ea-9b51-d6915ca15a9e'
SEQUENCE_TYPE = 0x9FD4A561
COMBO = (SEQUENCE, 'b28fd813-8918-4867-84d9-709d80e12202',
         'e9fdb3a1-dd67-4655-885f-83363bf88e50')


def validate_attack_test(reader, item_guid):
    p = reader.read_resource(reader.find_resource_index(item_guid, 0xB5CE8765))
    start, count = _relative_array(p, 1244, 236)
    if not any(str(uuid.UUID(bytes_le=p[start+i*236+4:start+i*236+20])) == SEQUENCE
               for i in range(count)):
        raise ValueError('Attack audio test requires the sword LightChain1 sequence')
    p = reader.read_resource(reader.find_resource_index(SEQUENCE, SEQUENCE_TYPE))
    start, count = _relative_array(p, 16, 72)
    if count != 1 or _relative_string(p, start+20) != 'Attack_Player_1H_Single_LightChain1':
        raise ValueError('Attack sequence structure changed')
    events, count = _relative_array(p, start, 12)
    if count < 25:
        raise ValueError('Attack sequence has too few events')
    for index, guid in ((23, SOURCE_SOUND), (24, TEST_SOUND)):
        kind, body, size = _variant_target(p, events+index*12)
        if (kind != _fnv1a32('keen::SfxNotifierEvent') or size < 168
                or str(uuid.UUID(bytes_le=p[body+144:body+160])) != guid):
            raise ValueError('Attack sound event no longer matches the tested layout')
    reader.find_resource_index(TEST_SOUND, 0xF257640C)
    for number, guid in enumerate(COMBO, 1):
        p = reader.read_resource(reader.find_resource_index(guid, SEQUENCE_TYPE))
        start, count = _relative_array(p, 16, 72)
        if count != 1 or _relative_string(p, start+20) != f'Attack_Player_1H_Single_LightChain{number}':
            raise ValueError('Unexpected combo sequence structure')
        events, count = _relative_array(p, start, 12)
        sounds, links = [], []
        for i in range(count):
            kind, body, size = _variant_target(p, events+i*12)
            if kind == _fnv1a32('keen::SfxNotifierEvent') and size >= 168:
                sounds.append(str(uuid.UUID(bytes_le=p[body+144:body+160])))
            if kind == _fnv1a32('keen::actor::SetActionOportunity') and size >= 184:
                links.append(str(uuid.UUID(bytes_le=p[body+168:body+184])))
        if sounds.count(SOURCE_SOUND) != 1 or COMBO[number % 3] not in links:
            raise ValueError('Combo sound or follow-up link changed')


def attack_audio_lua():
    return f'''
-- Clone all three light attacks before reconnecting the cyclic combo.
local attack_source_guid = "{SEQUENCE}"
local attack_sources = {{"{COMBO[0]}", "{COMBO[1]}", "{COMBO[2]}"}}
local attack_copies = {{}}
for chain_index, source_guid in ipairs(attack_sources) do
local attack_source_guid = source_guid
local attack_source = game.assets.get_resource(attack_source_guid, "keen::actor::ActorSequenceResource", 0)
if attack_source == nil then error("Attack audio test: source sequence missing") end
local attack_copy = game.assets.create_resource(attack_source.data, "keen::actor::ActorSequenceResource")
if attack_copy == nil then error("Attack audio test: sequence clone failed") end
attack_copy.data.resourceId = attack_copy.guid
local attack_sub = attack_copy.data.subSequences[1]
if #attack_copy.data.subSequences ~= 1 or attack_sub.name ~= "Attack_Player_1H_Single_LightChain" .. tostring(chain_index) then
    error("Attack audio test: unexpected subsequence")
end
local sound_changes = 0
for _, attack_event in ipairs(attack_sub.events) do
    if attack_event.type == "keen::SfxNotifierEvent" and attack_event.value.sound == "{SOURCE_SOUND}" then
        attack_event.value.sound = "{TEST_SOUND}"
        -- Bound the notifier lifetime independently of the sample duration.
        attack_event.value.duration.value = 100000000
        attack_event.value.cancelFromActorSequence = true
        sound_changes = sound_changes + 1
    end
end
if sound_changes ~= 1 then error("Attack audio test: expected one matching combo sound") end
attack_copies[source_guid] = attack_copy
end
for _, source_guid in ipairs(attack_sources) do
    local copy = attack_copies[source_guid]
    local links = 0
    for _, event in ipairs(copy.data.subSequences[1].events) do
        if event.type == "keen::actor::SetActionOportunity" then
            local target = attack_copies[tostring(event.value.followUp)]
            if target ~= nil then event.value.followUp = target.guid; links = links + 1 end
        end
    end
    if links == 0 then error("Attack audio test: no combo links rebound") end
    print("Attack audio combo: source=" .. source_guid .. " copy=" .. tostring(copy.guid) .. " links=" .. tostring(links))
end
-- Playback resolves sequence IDs through the shared collection, not the item reference alone.
local attack_collection_rebinds = 0
local attack_collections = {{}}
for _, resource_type in ipairs({{"keen::Game38ClientResources", "keen::Game38ServerResources"}}) do
    for _, game_resources in ipairs(game.assets.get_resources_by_type(resource_type)) do
        local collection_guid = game_resources.data.shared.actorSequenceCollection
        local copy = attack_collections[tostring(collection_guid)]
        if copy == nil then
            local collection = game.assets.get_resource(collection_guid, "keen::ActorSequenceCollectionResource", 0)
            if collection == nil then error("Attack audio test: active sequence collection missing") end
            local contains_source = false
            for _, sequence_ref in ipairs(collection.data.sequences) do
                if sequence_ref == attack_source_guid then contains_source = true; break end
            end
            if not contains_source then error("Attack audio test: active collection does not contain LightChain1") end
            copy = game.assets.create_resource(collection.data, "keen::ActorSequenceCollectionResource")
            if copy == nil then error("Attack audio test: collection clone failed") end
            for _, source_guid in ipairs(attack_sources) do
                table.insert(copy.data.sequences, attack_copies[source_guid].guid)
            end
            attack_collections[tostring(collection_guid)] = copy
        end
        game_resources.data.shared.actorSequenceCollection = copy
        attack_collection_rebinds = attack_collection_rebinds + 1
    end
end
if attack_collection_rebinds == 0 then error("Attack audio test: no shared sequence collections rebound") end
local attack_rebinds = 0
for _, entry in ipairs(custom_item.data.sequences) do
    local attack_copy = attack_copies[tostring(entry.sequence)]
    if attack_copy ~= nil then
        entry.sequence = attack_copy.guid
        entry.sequenceId.value = game.guid.hash(attack_copy.guid)
        attack_rebinds = attack_rebinds + 1
    end
end
if attack_rebinds == 0 then error("Attack audio test: item does not use LightChain1") end
print("Attack audio test A: combo=3 source={SOURCE_SOUND} replacement={TEST_SOUND} item="
    .. tostring(custom_item.guid)
    .. " rebinds=" .. tostring(attack_rebinds)
    .. " collectionRebinds=" .. tostring(attack_collection_rebinds))
'''
