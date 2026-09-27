# Attack audio test A — 0.27.1

Enable `Attack Audio Test A` for equipment based on `wpn_sword_02`, then
re-export and restart the game. Idle audio can remain enabled.

The exporter checks the selected ItemInfo uses sequence
`23542042-4376-4ded-afc9-5d99cfd95aff` (LightChain1).
At mod load, a new ActorSequenceResource is created and only the custom item's
matching sequence references and sequence IDs are rebound. Original sequence
resources are not edited.

The first subsequence's event 24 (Lua index) is checked to be SfxNotifierEvent
with sound `2545c5f6-a36d-425b-95ee-64e69e04d33e`. Its sound is replaced with
`3bd1393e-9a96-49ea-9b51-d6915ca15a9e`, the existing sound from event 25.
Event timing and the second event remain unchanged; the second sound may now
be heard twice. Neither sound's audible role has been identified yet.

Test a single normal attack, allow the combo to reset, and repeat. Compare with
the same mod exported with the checkbox disabled. Check the console for
`Attack audio test A:` including the new sequence GUID and rebind count.
Jump/dodge attacks and later combo sequences are not intentionally changed.

Verified locally: selected source layout, replacement sound resource existence,
generated Lua with test enabled/disabled, Blender registration. Sequence cloning
and playback still require in-game verification.
