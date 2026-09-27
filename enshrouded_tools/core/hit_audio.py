"""Experimental sword hit audio, based on in-game confirmed Test K. No bpy."""
import uuid
from pathlib import Path
from .attack_audio import validate_attack_test


def validate_hit_audio(reader, item_guid):
    validate_attack_test(reader, item_guid)
    if item_guid.lower() != '4306631d-fd7c-4215-b20e-9747dd2e441d':
        raise ValueError('Hit audio currently supports only the tested sword base 4306631d-fd7c-4215-b20e-9747dd2e441d')


def hit_audio_lua(donor):
    donor = str(uuid.UUID(donor))
    return Path(__file__).with_name('hit_audio.lua').read_text(encoding='utf-8').replace('__DONOR__', donor)
