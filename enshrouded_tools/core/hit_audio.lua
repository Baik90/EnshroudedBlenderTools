-- HIT TEST H: clone native melee program and only set its optional on-hit spawn.
do
    local zero = "00000000-0000-0000-0000-000000000000"
    if tostring(custom_item.data.equipment.program) ~= zero then
        error("Hit test H: existing equipment program; refusing to replace gameplay")
    end
    local donor = game.assets.get_resource("262ce15c-5f01-470a-a2b7-7079c6200c29", "keen::ecs::TemplateResource", 0)
    if donor == nil then error("Hit test H: audio donor missing") end
    local audio = game.assets.create_resource(donor.data, "keen::ecs::TemplateResource")
    local allowed = {
        ["keen::ecs::AudioComponent"] = true,
        ["keen::ecs::AudioResourceComponent"] = true,
        ["keen::ecs::CurrentTransform"] = true,
        ["keen::ecs::StaticTransform"] = true,
        ["keen::ecs::RenderTransform"] = true,
        ["keen::ecs::DoNotSave"] = true,
        ["keen::ecs::SpawnTime"] = true,
        ["keen::ecs::LifeTime"] = true,
    }
    for i = #audio.data.components, 1, -1 do
        if not allowed[audio.data.components[i].type] then table.remove(audio.data.components, i) end
    end
    local audio_count, lifetime_count = 0, 0
    for _, c in ipairs(audio.data.components) do
        if c.type == "keen::ecs::AudioComponent" then
            c.value.stopOnDestroy = true
            c.value.attach = false
        elseif c.type == "keen::ecs::AudioResourceComponent" then
            c.value.soundContainer = "e6da80f2-3534-459a-b605-75ff55d7caf7"
            audio_count = audio_count + 1
        elseif c.type == "keen::ecs::LifeTime" then
            c.value.lifeTime.value = 100000000
            lifetime_count = lifetime_count + 1
        end
    end
    if audio_count ~= 1 or lifetime_count ~= 1 then error("Hit test H: invalid audio-only template") end

    audio.data.name = "lightsaber_hit_test_h_audio_only"
    local selected = game.assets.get_resource("__DONOR__", "keen::ecs::TemplateResource", 0)
    if selected == nil then error("Hit audio: selected donor missing") end
    local chosen, count = nil, 0
    for _, c in ipairs(selected.data.components) do
        if c.type == "keen::ecs::AudioResourceComponent" then chosen=c.value.soundContainer; count=count+1 end
    end
    if count ~= 1 then error("Hit audio: expected one donor sound") end
    for _, c in ipairs(audio.data.components) do
        if c.type == "keen::ecs::AudioResourceComponent" then c.value.soundContainer=chosen end
    end
    local sound = game.assets.get_resource(chosen, "keen::SoundContainerResource", 0)
    if sound == nil then error("Hit test H: sound missing") end
    local source = game.assets.get_resource("0c3a7176-9336-47a3-ae98-d9433ac5ffbb", "keen::ImpactProgram", 0)
    if source == nil then error("Hit test H: melee program missing") end
    local program = game.assets.create_resource(source.data, "keen::ImpactProgram")
    if program == nil then error("Hit test H: clone failed") end
    program.data.programGuid = program.guid
    program.data.id.value = game.guid.hash(program.guid)
    local bytes = {}
    for i, value in ipairs(program.data.data) do bytes[i] = value end
    local hex = tostring(audio.guid):gsub("-", "")
    local raw = {}
    for i = 1, 32, 2 do raw[#raw+1] = assert(tonumber(hex:sub(i,i+1), 16)) end
    local packed = {raw[4],raw[3],raw[2],raw[1],raw[6],raw[5],raw[8],raw[7],raw[9],raw[10],raw[11],raw[12],raw[13],raw[14],raw[15],raw[16]}
    local changed = 0
    for _, v in ipairs(program.data.dataLayout) do
        if v.dbgName == "SpawnTemplate_OnHit::value" then
            if v.size ~= 16 or v.configId.value ~= 0x2c9f18a9 then error("Hit test H: constant changed") end
            local offset = v.offsetInBytes
            if offset + 16 > #bytes then error("Hit test H: out of bounds") end
            for i, value in ipairs(packed) do
                if bytes[offset+i] ~= 0 then error("Hit test H: existing spawn template") end
                bytes[offset+i] = value
            end
            v.configId.value = 0
            changed = changed + 1
        end
    end
    if changed ~= 1 then error("Hit test H: expected one spawn constant") end
    program.data.data = bytes
    local registries = game.assets.get_resources_by_type("keen::ImpactRegistryResource")
    if #registries == 0 then error("Hit test H: impact registry missing") end
    for _, registry in ipairs(registries) do table.insert(registry.data.programs, program.guid) end
    local templates = game.assets.get_resources_by_type("keen::ecs::TemplateCollectionResource")
    if #templates == 0 then error("Hit test H: template registry missing") end
    for _, registry in ipairs(templates) do table.insert(registry.data.templates, audio) end


-- Test K: experimental post-ApplyDamage sound trampolines; original addresses retained.
local heavy_source = game.assets.get_resource("7874874d-15f6-4151-90e3-6003732774e2", "keen::ImpactProgram", 0)
if heavy_source == nil then error("Test K: heavy source missing") end
local heavy = game.assets.create_resource(heavy_source.data, "keen::ImpactProgram")
if heavy == nil then error("Test K: heavy clone failed") end
if #heavy.data.code ~= 468 or #heavy.data.dataLayout ~= 61 then error("Test K: heavy layout changed") end
local hb = {}
for i,v in ipairs(heavy.data.data) do hb[i] = v end
while #hb % 16 ~= 0 do hb[#hb+1] = 0 end
local audio_offset = #hb
for _,v in ipairs(packed) do hb[#hb+1] = v end
if #hb > 65535 then error("Test K: data offset overflow") end
table.insert(heavy.data.dataLayout, {
    name = {value=0x4b485431}, configId={value=0}, type={value=0x2a44d9ef},
    size=16, offsetInBytes=audio_offset, dbgName="TestK_Audio::value"
})
heavy.data.data = hb
local code = {}
for i,v in ipairs(heavy.data.code) do code[i]=v end
-- Native GroundHitSpawn argument setup, with a separate sound-template constant.
local expected = {0x0c,0x0c,0x0c,0x0c,0x0c,0x0b,0xffff0002,0x0c,0x0b,0xffff001c,0x0b,0xffff0030,0x0b,0xffff0031,0x0c,0x13,0x59f89a94,0x61b11b03,0x1b}
for i,v in ipairs(expected) do
    if code[101+i] ~= v then error("Test K: native spawn block changed") end
end
local sites = {{213,0x01234416},{356,0x7f724efd},{409,0xa455d96d},{461,0x5335a762}}
for _,site in ipairs(sites) do
    local at, node_id = site[1], site[2]
    if code[at+1] ~= 0x13 or code[at+2] ~= node_id or code[at+3] ~= 0xb04d0e7a then error("Test K: damage call changed") end
    local target = #code
    -- Execute the original damage call, retain its return below the spawn arguments.
    code[#code+1]=0x13; code[#code+1]=node_id; code[#code+1]=0xb04d0e7a
    for i,v in ipairs(expected) do
        if i == 10 then v=0xffff003d end
        code[#code+1]=v
    end
    code[#code+1]=0x08; code[#code+1]=at+3
    code[at+1]=0x08; code[at+2]=target; code[at+3]=0x1e
end
if #code ~= 564 then error("Test K: trampoline length mismatch") end
heavy.data.code = code
heavy.data.programGuid = heavy.guid
heavy.data.id.value = game.guid.hash(heavy.guid)
for _,registry in ipairs(registries) do table.insert(registry.data.programs, heavy.guid) end

-- Clone light combo and the directly referenced heavy sequence.
local attack_source_guid = "23542042-4376-4ded-afc9-5d99cfd95aff"
local attack_sources = {"23542042-4376-4ded-afc9-5d99cfd95aff", "b28fd813-8918-4867-84d9-709d80e12202", "e9fdb3a1-dd67-4655-885f-83363bf88e50", "565411c6-b057-4997-ae4e-f95e9e0ff48a"}
local attack_copies = {}
for chain_index, source_guid in ipairs(attack_sources) do
local attack_source_guid = source_guid
local attack_source = game.assets.get_resource(attack_source_guid, "keen::actor::ActorSequenceResource", 0)
if attack_source == nil then error("Attack audio test: source sequence missing") end
local attack_copy = game.assets.create_resource(attack_source.data, "keen::actor::ActorSequenceResource")
if attack_copy == nil then error("Attack audio test: sequence clone failed") end
attack_copy.data.resourceId = attack_copy.guid
local attack_sub = attack_copy.data.subSequences[1]
local is_heavy = chain_index == 4
local expected_name = is_heavy and "Attack_Player_Melee_Heavy_Sword_Diagonal" or ("Attack_Player_1H_Single_LightChain" .. tostring(chain_index))
local expected_program = is_heavy and "7874874d-15f6-4151-90e3-6003732774e2" or "0c3a7176-9336-47a3-ae98-d9433ac5ffbb"
if #attack_copy.data.subSequences ~= 1 or attack_sub.name ~= expected_name then
    error("Attack audio test: unexpected subsequence")
end
local impact_changes = 0
for _, event in ipairs(attack_sub.events) do
    if event.type == "keen::actor::SpawnImpact" and tostring(event.value.impact) == expected_program then
        event.value.impact = is_heavy and heavy.guid or program.guid
        impact_changes = impact_changes + 1
    end
end
if impact_changes ~= 3 then error("Hit test H: expected three melee impacts per combo") end
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
    if source_guid ~= "565411c6-b057-4997-ae4e-f95e9e0ff48a" and links == 0 then error("Attack audio test: no combo links rebound") end
    print("Attack audio combo: source=" .. source_guid .. " copy=" .. tostring(copy.guid) .. " links=" .. tostring(links))
end
-- Playback resolves sequence IDs through the shared collection, not the item reference alone.
local attack_collection_rebinds = 0
local attack_collections = {}
for _, resource_type in ipairs({"keen::Game38ClientResources", "keen::Game38ServerResources"}) do
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
if attack_rebinds < 2 then error("Attack audio test: item does not use LightChain1") end
print("[lightsaber] TEST K: experimental heavy post-damage spawn; NO SWING MARKER; light hit test retained; audio=selected donor; program=" .. tostring(program.guid) .. " itemRebinds=" .. tostring(attack_rebinds))
end
