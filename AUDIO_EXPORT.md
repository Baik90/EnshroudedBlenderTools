# Audio export 0.28.7

Attack notifier lifetime test: custom Attack SfxNotifierEvents now have a 100 ms
duration and cancelFromActorSequence=true, both standalone and combined with Hit.
The native LightChain1 swing has duration=0 and cancelFromActorSequence=false;
the exported custom sound already had loop=false despite indefinite repetition.
This change needs in-game verification: one swing, wait five seconds, then combo,
heavy attack (combined Hit path), interruption and sheathing. Check both absence
of repetitions and whether the sample finishes without truncation. Hit's tested
100 ms entity lifetime and Idle behavior are unchanged. This is a notifier test,
not yet proof that notifier duration behaves like the Hit entity lifetime.

In New Model + Recipe / equipment, enable Custom Audio and add Idle, Attack or
Hit (Experimental). Each event selects Vanilla (load audio templates and choose
a donor) or WAV File and an independent volume. Draw/Sheathe research is parked.

WAV export accepts exactly 48000 Hz, uncompressed PCM16, mono/stereo, nonempty
complete frame data. Unsupported formats/rates abort export; no silent resampling.
Stereo is averaged to mono. Source files are not changed. PCM payloads are copied
into the staged mod/custom_audio directory, so the installed mod needs no source
paths. Looping: own Idle WAV loops; Vanilla Idle retains donor settings. Attack
and Hit containers disable their outer loop (nested Vanilla containers may have
their own behavior). Volume is per selected container.

Hit keeps the in-game tested light/heavy sword program path and the 100ms
sound-entity lifetime workaround. Only confirmed base item
4306631d-fd7c-4215-b20e-9747dd2e441d is accepted. Enemy-only filtering is not
guaranteed. Attack alone uses the existing three-light-combo implementation;
combined Attack+Hit also changes the matching swing sound in the heavy clone.
Combined generation is tested offline, not yet confirmed in game.

Multiple Attack or Hit rows form a native Random parent container, with one
equally weighted child per row. Selection occurs per playback, not at export or
mod initialization. Repeated selection of the same row is allowed; this is not
round-robin. Vanilla and WAV rows may be mixed; per-row volume stays on each child.
Single-row behavior stays unchanged. Parent containers do not loop and do not
add volume/pitch variation. Nested Vanilla source behavior is otherwise retained.
Generation tests pass; in-game confirmation of the new random parent is pending.

Only one Idle event is accepted. The previous multi-Idle entry merge did not
establish simultaneous playback, so it remains blocked pending a layered
implementation. Existing selections remain saved; remove duplicate Idle rows.

Run tools/test_audio_export.py with Blender Python for syntax/generation tests,
48kHz rejection checks, PCM conversion and staged asset checks. In-game acceptance:
Idle loops and stops on sheath, Attack at swing, Hit once on light/heavy contact,
no Hit on misses, damage/stun unchanged. Live Lightsaber test is not overwritten
by building the add-on; export the desired events after installation.
