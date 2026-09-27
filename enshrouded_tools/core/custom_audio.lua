local function custom_pcm_sound(file, rate, frames, looping, label)
    local input = io.read(file)
    if input == nil then error("Custom sound file missing: " .. file) end
    local content = game.assets.create_content(input)
    if content == nil then error("Custom sound content creation failed") end
    local donor = game.assets.get_resource("09086e2f-0ec5-4569-8be6-afbe4afd1db0", "keen::SoundResource", 0)
    if donor == nil then error("PCM donor missing") end
    local sound = game.assets.create_resource(donor.data, "keen::SoundResource")
    sound.data.channelConfiguration = "Mono"
    sound.data.format = "Uncompressed"
    sound.data.framesPerSecond = rate
    sound.data.frameCount = frames
    sound.data.duration.value = math.floor(frames * 1000000000 / rate)
    sound.data.data = {}
    sound.data.dataHash = game.guid.to_content_hash(content.guid)
    sound.data.debugName = label
    local source_container = game.assets.get_resource("e6da80f2-3534-459a-b605-75ff55d7caf7", "keen::SoundContainerResource", 0)
    if source_container == nil then error("Sound container donor missing") end
    local container = game.assets.create_resource(source_container.data, "keen::SoundContainerResource")
    container.data.entries = {{type="keen::SoundContainerResourceSoundEntry", value={chance=1.0, sound=sound.guid}}}
    container.data.loop = looping
    container.data.loopSameChosenEntry = true
    container.data.volume = 0.5
    container.data.volumeRandomness = 0
    container.data.pitch = 1
    container.data.pitchRandomness = 0
    container.data.sleep.value = 0
    container.data.sleepRandomness.value = 0
    container.data.hasPosition = true
    container.data.minDistance = 1
    container.data.maxDistance = 20
    print("[lightsaber] CUSTOM PCM " .. label .. " loop=" .. tostring(looping) .. " sound=" .. tostring(sound.guid))
    return container
end
