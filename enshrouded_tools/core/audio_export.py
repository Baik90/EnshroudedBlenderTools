"""Audio assets and composition for the tested sword workflow (no bpy)."""
import array
import json
import sys
import uuid
import wave
from pathlib import Path
from .idle_audio import idle_audio_lua
from .attack_audio import attack_audio_lua, TEST_SOUND
from .hit_audio import hit_audio_lua

DONOR = '262ce15c-5f01-470a-a2b7-7079c6200c29'


def read_wav(path):
    try:
        with wave.open(str(path), 'rb') as w:
            if w.getframerate() != 48000:
                raise ValueError('Sound WAV must be resampled to 48000 Hz before export')
            if w.getsampwidth() != 2 or w.getnchannels() not in (1, 2) or w.getcomptype() != 'NONE':
                raise ValueError('Sound WAV must be PCM16 mono or stereo')
            frames = w.getnframes()
            data = w.readframes(frames)
            if not frames or len(data) != frames * w.getnchannels() * 2:
                raise ValueError('Sound WAV is empty or truncated')
            samples = array.array('h', data)
            if sys.byteorder != 'little':
                samples.byteswap()
            if w.getnchannels() == 2:
                samples = array.array('h', (int((samples[i]+samples[i+1])/2) for i in range(0,len(samples),2)))
            if sys.byteorder != 'little':
                samples.byteswap()
            return frames, samples.tobytes()
    except (wave.Error, OSError, EOFError) as exc:
        raise ValueError(f'Cannot read sound WAV {path}: {exc}') from exc


def stage_audio(events, directory):
    for i, event in enumerate(events):
        if event['source'] == 'WAV':
            frames, data = read_wav(event['path'])
            if frames != event['frames']:
                raise ValueError('Sound WAV changed after validation; export again')
            folder = Path(directory) / 'custom_audio'
            folder.mkdir(exist_ok=True)
            (folder / f'event_{i}.pcm').write_bytes(data)


def audio_lua(events):
    definitions = Path(__file__).with_name('custom_audio.lua').read_text(encoding='utf-8')
    sources = {}
    groups = {}
    for i, e in enumerate(events):
        kind = e['type']
        if kind == 'IDLE' and kind in groups:
            raise ValueError('Only one Idle event is supported; simultaneous idle layers are not yet verified')
        var = f'ebt_audio_{i}'
        if e['source'] == 'WAV':
            definitions += f'\nlocal {var} = custom_pcm_sound("custom_audio/event_{i}.pcm",48000,{int(e["frames"])},{str(kind == "IDLE").lower()},"{kind}")\n'
        else:
            donor = str(uuid.UUID(e['donor']))
            definitions += f'''\nlocal {var}
do
 local donor = game.assets.get_resource("{donor}", "keen::ecs::TemplateResource", 0)
 if donor == nil then error("Audio donor missing") end
 local count = 0
 for _, c in ipairs(donor.data.components) do
  if c.type == "keen::ecs::AudioResourceComponent" then
   local source = game.assets.get_resource(c.value.soundContainer, "keen::SoundContainerResource", 0)
   if source == nil then error("Audio container missing") end
   {var} = game.assets.create_resource(source.data, "keen::SoundContainerResource")
   count = count + 1
  end
 end
 if count ~= 1 then error("Audio donor requires one sound container") end
end
'''
        volume = float(e.get('volume', .5))
        if not 0 <= volume <= 1:
            raise ValueError('Audio volume must be between 0 and 1')
        definitions += f'{var}.data.volume = {volume}\n'
        if kind != 'IDLE':
            definitions += f'{var}.data.loop = false\n'
        groups.setdefault(kind, []).append(var)
    for kind, variants in groups.items():
        if len(variants) == 1:
            sources[kind] = variants[0]
            continue
        # Native random container selects a child per playback, not at mod load.
        # One entry per UI row preserves equal row weights and child volume.
        parent = f'ebt_random_{kind}'
        entries = ',\n'.join(
            '{type="keen::SoundContainerResourceContainerEntry", value={chance=1.0, container=' + child + '.guid}}'
            for child in variants)
        definitions += f'''
local {parent} = game.assets.create_resource({variants[0]}.data, "keen::SoundContainerResource")
if {parent} == nil then error("Random audio container creation failed") end
{parent}.data.entries = {{{entries}}}
{parent}.data.mode = "Random"
{parent}.data.loop = false
{parent}.data.loopSameChosenEntry = false
{parent}.data.avoidRepeatingLastX = 0
{parent}.data.volume = 1
{parent}.data.volumeRandomness = 0
{parent}.data.pitch = 1
{parent}.data.pitchRandomness = 0
{parent}.data.sleep.value = 0
{parent}.data.sleepRandomness.value = 0
{parent}.data.hasRandomPosition = false
print("EBT random audio: {kind} variants={len(variants)}")
'''
        sources[kind] = parent
    idle = definitions
    if 'IDLE' in sources:
        idle += idle_audio_lua(DONOR)
        idle += f'\ncustom_template.data.components[#custom_template.data.components].value.soundContainer = {sources["IDLE"]}.guid\n'
    attack = ''
    if 'HIT_ENEMY' in sources:
        attack = hit_audio_lua(DONOR)
        anchor = '    for _, c in ipairs(audio.data.components) do\n        if c.type == "keen::ecs::AudioResourceComponent" then c.value.soundContainer=chosen end'
        if anchor not in attack:
            raise ValueError('Hit audio generator changed')
        attack = attack.replace(anchor, f'    chosen = {sources["HIT_ENEMY"]}.guid\n' + anchor)
        if 'ATTACK_TEST_A' in sources:
            anchor = 'local impact_changes = 0'
            attack = attack.replace(anchor, f'''for _, event in ipairs(attack_sub.events) do
 if event.type == "keen::SfxNotifierEvent" and tostring(event.value.sound) == "2545c5f6-a36d-425b-95ee-64e69e04d33e" then
  event.value.sound = {sources['ATTACK_TEST_A']}.guid
  event.value.duration.value = 100000000
  event.value.cancelFromActorSequence = true
 end
end
''' + anchor)
    elif 'ATTACK_TEST_A' in sources:
        attack = attack_audio_lua().replace(f'attack_event.value.sound = "{TEST_SOUND}"', f'attack_event.value.sound = {sources["ATTACK_TEST_A"]}.guid')
    return idle, attack
