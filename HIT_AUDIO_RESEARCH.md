# Hit Enemy audio research — 2026-09-16

Status: investigation only. HIT_ENEMY remains unavailable for export. No game
archives or active mods were modified. No in-game hit-audio test yet.

## Evidence from local build 1076226

- Reflection contains `keen::impact_nodes::ForEachHitEvent`, with weaponEntity,
  sourceEntity, targetEntity, targetRootEntity, position, normal, healthChange,
  and flags for blocked, parried, critical and killing hits.
- `keen::impact_nodes::IsEnemy` accepts entityAId and entityBId.
- `keen::impact_nodes::ItemBasedMaterialReaction` includes hitCombatTarget,
  itemId, usedItemId, materialId and impactMaterialId. A combat target is not
  necessarily a hostile enemy; this alone does not establish enemy filtering.
- `keen::MaterialFeedbackEffect` exposes sfx at byte 48 and vfx at byte 64.
  This is a possible audio endpoint, not a confirmed per-weapon enemy-hit hook.
- The archive contains 496 `keen::ImpactProgram` resources. Their executable
  representation includes code, codeShutdown, dataLayout and data, rather than
  a directly editable list of the reflected source nodes.
- Program `4b3320a6-01ae-4b73-bf0e-b96444d9b2a7`, previously identified through
  the sword's impact entity, has 603 variables and mostly attribute modifiers.
  Its existence is not proof that it handles contact sounds.
- Program `aa0edeab-c089-4f6f-be73-426a0826d477` has 15 variables including
  ForEachHitEvent rootEntity/targetRootEntity/healthChange, Faction_AllEnemies,
  ChanceValue and health-related attribute operations. This demonstrates an
  existing hit-processing candidate, but its owner and control flow remain
  unverified. Do not repurpose it as an audio program based on names alone.

## Next investigation

1. Resolve owners of small hit-processing programs and identify a vanilla
   on-hit effect that spawns an entity. Trace its compiled flow and references.
2. Check whether its filtering supports the attacking weapon and hostile target
   without changing damage, healing or other gameplay effects.
3. Prefer a cloned, isolated existing path with a short-lived audio-only entity;
   alternatively trace item material feedback and its combat-target selection.
   Neither approach is implemented or confirmed yet. Do not globally replace
   flesh/material sounds, since that would affect unrelated weapons.
4. Test misses, consecutive hits, heavy attacks, enemies, allies, walls, blocks,
   and multiple targets. Define whether a blocked hit should count before release.

## Reproduction

Read-only probe (uses the existing archive reader, no bpy in parsing):

```powershell
& 'E:\Programme\Blender 5.2\blender.exe' --background --factory-startup --python tools/probe_hit_audio.py -- 'D:\Steam\steamapps\common\Enshrouded\enshrouded.kfc'
```

Append `--guid <ImpactProgram GUID>` to inspect all variable names in one program.
Variable names provide leads; they do not prove execution order or conditions.

## Follow-up: resource owners

- `04e5c47a-6e5f-47fd-9fc7-3da0bbe7b0f2` is directly referenced by
  ItemInfo `042b6b77-e863-44ff-aae4-d8f85906848d`, debugName
  `T4_Gem_GemOfFocusedLight`. The GUID occurs at byte 312, confirmed by
  reflection as ItemInfo.equipment (260) + EquipmentSetup.program (52).
  Its variables include PrimerBuff, BuffTypeTier1/2/3, PlayerBuff,
  CreateDamageSetup, attack modifiers and hit position/normal/weaponEntity.
  This is evidence of an item-linked hit-processing program, NOT an isolated
  sound hook. Copying it unchanged could introduce gameplay effects.
- `19b143a8-24a1-415c-ae15-bc7484d27dba` occurs in template
  `3b874eb5-bae2-4b6d-a63e-17bdd35b11c4`, named
  `Explosion_Player_Skill_Shockwave`, at byte 636. This byte-match is an owner
  candidate; its component field has not yet been decoded. Its variable names
  include damage, stamina loss, collision streams and IsEnemy filtering.
- Next: resolve the gem program's typed constant references and control flow,
  especially buff/template spawning. Determine whether a minimal cloned
  program can retain per-weapon hit filtering while removing gameplay effects.
  Do not enable HIT_ENEMY export until that path is verified.

Probe now supports `--guid <GUID> --owners` for template references, and
`--guid <GUID> --owners --all-resources` for all part-zero resource types.
These searches report raw GUID byte matches, including self-references and
registries. They do not by themselves prove ownership or runtime execution.

## Buff follow-up: reapplication and effect templates

Reflection confirms BuffApplyType: Invalid=0, ResetTime=1,
ReplaceAtEnd=2, Replace=3. Its tooltip describes reapplication when another
buff is already active. All five inspected gem buffs use ResetTime.
This suggests a duration refresh, not a guaranteed onCreate on every hit.
Neither onCreate re-triggering nor Replace behavior has been tested in-game.

PrimerBuff `b3ce07a9-4729-4461-8b22-c7a2a2139649` references program
`c0543bf5-e33e-4cb4-825a-ea353959f566`. Its 12 variables include tier buff
references, wait durations, buff duration and target IDs. The tier references
are zero defaults with nonzero config IDs: they must not be interpreted as
proof that runtime references are missing.

PlayerBuff `1c779e72-2347-48e6-badf-630d971ce5bf` references program
`530597da-9acf-4cb2-9603-acbad2eed6a3`. Its 23 variables include player_chest,
locked target, blocking/aiming states, waitDuration and four template references:

| Tier | Template GUID |
| --- | --- |
| 0 | e4a078b7-7f7c-4b61-91d3-5868f1098ae8 |
| 1 | 9dc1d881-55e5-4dee-b59e-00f13333bd34 |
| 2 | 5536cc14-7306-4ae6-aeff-64b195c2f52f |
| 3 | b99fbda9-2a79-4f87-97e9-eeb7a3a0e19a |

Their debug names are VFX_WeaponGem_GemOfFocusedLight_SourceTarget_tier0..3.
Each includes AudioComponent, LifeTime, SlotAttachment and VFX components;
none lists AudioResourceComponent. AudioComponent presence alone does NOT prove
a sound is assigned or that playback occurs once per hit.

Conclusion: the gem leads to staged source-target effects, not a demonstrated
minimal enemy-hit sound. Do not clone the complete chain into the weapon yet.
Next unresolved work is compiled control flow and sound-source resolution;
changing ResetTime to Replace alone is not a verified fix.

`--values --types <types.json>` now also labels BuffApplyType and prints the
names/components of referenced templates. Both child programs were read
successfully with the probe; no game or export behavior was modified.

## Direct template audio inspection

The probe now reads AudioComponent fields and AudioResourceComponent.soundContainer
from referenced templates. All four FocusedLight tiers have identical inspected
audio fields: slot=0, stopOnDestroy=true, attach=false, attachedToEntity=0,
attachToParent=false, eight zero base bytes and identical offset bytes.
None contains AudioResourceComponent. Therefore no direct soundContainer
assignment was found in these templates. This does not exclude runtime or
VFX-driven audio, and does not prove silence in-game.

The existing `--values --types <types.json>` command automatically prints AUDIO
lines now. The four-template probe completed successfully against local archives.
This branch has not yielded a per-hit audio trigger. Next work should focus on
actual impact control flow or a simpler vanilla hit program, rather than assuming
these generic AudioComponents are evidence of a usable hit sound.

## 2026-09-17: command-word inspection

Reflection defines ImpactCommand as a four-byte typedef, not a reflected opcode
enum. Probe option `--code` reads code/codeShutdown/queryCallIds with stride 4.
With `--types`, exact matches to impact-node hashes are labeled HASH CANDIDATE;
these are not yet decoded instructions or verified execution paths.

Small program b33c94fa-b1e2-4ae5-8e91-fff1a9d8cb31 has 37 code words,
one shutdown word (0x1e), stackSize=256 and one variable (ForEachHitEvent::index).
Its code includes the nameHash of ForEachHitEvent (0x9f34f4ea).

Primer program c0543bf5-e33e-4cb4-825a-ea353959f566 has 228 code words.
Exact nameHash matches: GetRoot at word 4, GetLockedTarget at 14/30,
GetSelf at 20, IsSameEntity at 38, HasBuffNode at 53/79/92/105,
ApplyBuff at 120/134/157/180 and RemoveBuff at 143/166/204/213/222.
These matches occur in repeated sequences `0x13, <word>, <node nameHash>`.
The hypothesis is a native-node call encoding; operand and branch semantics
remain unverified. This is evidence beyond variable names, but not permission
to remove words from live programs. A complete control-flow decoder is still
required before safe bytecode rewriting.

Both raw command probes completed successfully; no runtime/mod changes made.

## Variable-index audit

Probe `--audit` scanned code and codeShutdown across all 496 programs:
16,914 words with upper bits 0xffff; every low-16-bit value is within that
program's dataLayout variable count (zero out-of-range candidates).
This strongly supports the variable-index hypothesis, but does not establish
instruction boundaries, read/write semantics or argument ordering.

In minimal program b33c94fa-b1e2-4ae5-8e91-fff1a9d8cb31, words 2 and 4 are
both ffff0000, corresponding to its only variable ForEachHitEvent::index.
They follow 0x18 and 0x0b respectively. The ForEachHitEvent nameHash occurs at
word 30. Interpreting this as an iterator setup/use remains a hypothesis.
No sound or spawning behavior has been demonstrated in this minimal program.

`--audit --guid <GUID>` prints candidate indices and corresponding variable
names; without --guid it checks all programs and reports aggregate results.
The scan does not execute or modify bytecode.

## 2026-09-18: arrow collision path (read-only)

Projectile_Player_ArrowT5_Steel, template
7acf2535-540c-4818-9933-f3f628dc4211, contains Collider/ClientCollider,
CastColliderShape, Projectile, Velocity, Gravity, Impact and ImpactConfiguration.
Its Impact.program is c0a8231a-f87f-467c-ad9d-6d4fe93ecda7.
Its directly attached audio resource is 97c732ec-1324-403e-9bbf-efc7218e46e0;
this alone does not establish whether it is flight or impact audio.

The impact program contains matched call patterns for OnEvent, FilterFriends,
FilterSameRoot, ForEachCollisionInStream, ItemBasedMaterialReaction, ApplyDamage,
ApplyBuff and TriggerNoise. Fields include collision position/normal/materialId,
isCombatTarget, UsedItem and Ammunition. This is an entity-attached collision
path, unlike the attempted equipment.program/ForEachHitEvent route.
Call order is observed in code words, not a fully decoded runtime control flow.
TriggerNoise must not be equated with audible SFX without further evidence.

Next: trace ItemBasedMaterialReaction and per-item material overrides; compare
the sword's actual collision/impact path before attempting any adaptation.
Do not transplant arrow damage/filter logic into a sword.

New read-only tools/probe_arrow_templates.py takes KFC path, types.json path
and optional name substring (default Projectile_Player_Arrow). No live mod was
changed. Latest archive scan reports 497 programs rather than the earlier 496;
cause not determined, so old aggregate counts are not current invariants.

## Material feedback probe (2026-09-18)

Added read-only `tools/probe_material_feedback.py`. Arguments after Blender's
`--`: KFC path, types.json path, optional repeated `--item` GUID/name substring.
Default compares both T5 steel arrow ammunition items with the Lightsaber base
item 4306631d-fd7c-4215-b20e-9747dd2e441d. Uses reflected field offsets and the
existing KFC3Reader; no game/mod writes.

Steel ammo a652f315-89b3-42ed-9b01-d08cb28669c7 and poison ammo
e67d8de0-acb8-4357-a0fb-34a0d3f1d21b both have materialInteraction.isSet=true,
materialId=0x69ff9049 and materialRef=ab891da0-2d26-491b-b92d-f85a16edb257.
Despite the reflected CollisionFeedbackMaterialReference type, this GUID
resolves to cooked keen::MaterialFeedback. Both spawn override GUIDs are zero.
The base sword's materialInteraction is unset with zero references/ID.

Collection 253a49ae-1fe4-4224-8a52-5e11a34c5a58 contains 1413 collision matrix
entries. Interpreting materialPairId as two uint32 IDs finds arrow matches.
Example pair 0x69ff9049/0x432b8845 has mask 0x7f and Hit/MediumHit/CriticalHit
sound 81e1e3d0-3a4e-4034-bf95-2c5d5098fb1e, resolved as SoundContainerResource.
Collision slot names come from reflected keen::ecs::CollisionType, not guesses.
The arrow MaterialFeedback itself has collisionTypeMask=0, so inspecting only
its default effects would miss these matrix assignments.

This establishes stored sound assignments, not audible runtime selection or
an enemy-only route. Pair packing is a matching hypothesis; target material
identity and the sword's fallback/category path remain to be traced. Do not
globally replace shared matrix sounds or transplant arrow damage logic.

### Sword template follow-up (2026-09-18)

Extended the material probe to print equipment template components and direct
Impact.program references. `--scan-programs` inventories raw call-pattern
candidates for ItemBasedMaterialReaction / SendBaseHitEvent and their direct
template Impact owners. This is not control-flow decoding or a runtime trace.

Sword equipment.impactEntity points to 7100f7c2-480f-44da-a354-91c08786011b,
Base_Impact_Equipment. Its Impact.program is
4b3320a6-01ae-4b73-bf0e-b96444d9b2a7. Existing call probe recognizes GetParent
and 122 ApplyChange occurrences, but no hit-processing node. 122 raw call
candidates remain unresolved, so absence is not proof of runtime behavior.
The visual template d0ab698d-f4c2-449b-95c0-27b1182d298c,
Visuals_Sword_02_Light, has no direct material feedback component or Impact.
equipment.program is zero in the unmodified source item.
Weapon category reference d52db28f-dcba-4319-b4dc-24630fe53cd0 does not resolve
as a standalone part-zero resource; do not treat this as a missing game asset.

The new scan completes successfully and finds 30 material-reaction/base-hit
program candidates, with many direct owners identified as projectile templates.
The actual sword attack collision/material source remains unresolved. Next:
trace attack sequence collision setup / player-side configuration rather than
patching the shared Base_Impact_Equipment attribute program. No mod deployed.

### Direct light-combo impact reference (2026-09-18)

Added read-only tools/probe_attack_impacts.py (KFC and types.json positional
arguments after --). It inventories SpawnImpact events in player one-handed
attack subsequences, following ConfigurationArray typedefs to variant arrays.
Successfully executed under Blender; no live mod changes.

All three current Attack_Player_1H_Single_LightChain sequences reference
program 0c3a7176-9336-47a3-ae98-d9433ac5ffbb in SpawnImpact events:
chain1 events 18/21/22; chain2 18/21/22; chain3 15/18/22 (one-based).
This is a direct reflected event-field reference, not a raw byte match.
The program has 47 variables and recognized calls GetParent, OnEvent,
FilterConsecutiveHits, FilterFriends, ForEachCollisionInStream, two ApplyDamage,
SpawnEntity, RandomBranchNode, ApplyBuff. All 10 raw call patterns resolved.
No ItemBasedMaterialReaction or SendBaseHitEvent call pattern was found here;
the earlier scan restricted to those two nodes missed this real melee program.

Material::valueId defaults to zero with config ID 0xbf09083f. The scanned
SpawnImpact configurations contain no MaterialIdImpactConfig. Actual material
source remains unresolved, but program includes SpawnTemplate_OnHit::value:
this is a more direct test candidate than equipment.program. Inspect SpawnEntity
control flow/inputs before configuring it; do not assume an enemy-only gate.

The earlier candidate 7874874d-15f6-4151-90e3-6003732774e2 has raw references
in seven ActorSequenceResources, whereas e7dd1879-75b8-4341-8a36-ed479541a353
only appeared in itself and the program registry. Neither establishes ownership
by the selected sword. Prioritize the directly linked combo program above.

### Test H: direct melee on-hit spawn

Staged as example/mods/lightsaber_hit_test/test-h.lua, based on unchanged Test G
export assets. Removes the entire G equipment-program experiment and VFX donor.
Clones native melee program 0c3a7176-9336-47a3-ae98-d9433ac5ffbb without code
changes. Replaces only the zero SpawnTemplate_OnHit::value default with the
sanitized audio template and clears that variable's configId (original
0x2c9f18a9), preventing configuration override of the test constant.
Audio uses confirmed Stresstest_Explosion SoundContainerResource
e6da80f2-3534-459a-b605-75ff55d7caf7, without damage/collision/VFX components.

Clones all three current light combo sequences and redirects their nine native
SpawnImpact events to the cloned program. Reconnects combo follow-ups, appends
clones to copied shared sequence collections and rebinds only the custom item's
sequence entries. Original attack sounds, damage defaults and bytecode remain
unchanged. No equipment.program binding. Heavy attacks are outside this test.
Guards check constant name/size/config/default, three impact events per chain,
and required registries. Runtime marker: [lightsaber] HIT TEST H.

Archive inspection and static review done; no Lua parser installed, no in-game
validation yet. Test light attacks into air, enemy (normal/critical), and wall
separately. Enemy-only gating and possible multiple sounds remain unproven.

### Test H confirmed; heavy attack follow-up

User confirmed light hits play the test sound; air swings retain only normal
swing audio. Voxel walls show no weapon hit feedback also with vanilla weapons.
Heavy hits do not play the test sound (not included in H). Enemy-only semantics
versus destructible props remain untested.

probe_attack_impacts.py now accepts an optional name substring, or
--item-sequences to inspect actual source sword ItemInfo sequence references.
This identifies heavy sequence 565411c6-b057-4997-ae4e-f95e9e0ff48a,
Attack_Player_Melee_Heavy_Sword_Diagonal, with SpawnImpact events 16/17/18
referencing 7874874d-15f6-4151-90e3-6003732774e2. This resolves the previously
unowned candidate through sequence ownership, not equipment template ownership.

Unlike the light program, heavy has GroundHitTemplate::value (config 0xf6a785cd,
offset 304) already referencing e2f935c2-5687-4d8d-a111-117fd0f6bf19,
VFX_Weapon_Arrow_Stun_Impact. It does NOT have SpawnTemplate_OnHit.
Each heavy SpawnImpact has six simple configs, no template override, and no
scaled configs. Do not swap in the light program (would alter heavy gameplay)
or blindly replace GroundHitTemplate (existing VFX behavior must be preserved;
its trigger conditions are not yet verified).
Game was running during this investigation. Test H remains installed; no heavy
test was deployed. Next inspect GroundHitSpawn control flow and donor template
before adding sound to an isolated clone or adding a separate hit spawn.

### Test I deployed: native heavy effect sound diagnostic

test-i.lua retains confirmed light Test H and clones heavy sequence
565411c6-b057-4997-ae4e-f95e9e0ff48a plus its 468-word program. No bytecode,
damage or event timing changes. Its GroundHitTemplate default points to a clone
of e2f935c2-5687-4d8d-a111-117fd0f6bf19; configId cleared only for this constant.
The cloned effect retains all components/VFX/lifetime, replaces its existing
sound 48aef822-b86f-41d3-9d9e-ca072b4e2bd0 with Stresstest_Explosion.
Three heavy SpawnImpact references rebound; light combo remains intact.

This tests the native ground-effect trigger, NOT a proven every-heavy-hit hook.
Raw code places GroundHitSpawn before combatCollider/IsEnemy branches; actual
branch semantics remain unverified. Compare heavy enemy hits, empty swings,
and ground/prop collisions. Negative enemy result would reject this route.
Installed after process/hash checks; prior H saved as pre-i-20260918-184326.lua.
Installed SHA256 733E80699CFFB6A5DCDBD9594DEF11200C78890017497B9BCE6187AE2CC0487A.
No in-game validation yet; no local Lua parser available. Runtime guards check
donor sound, constant bytes/layout and three impacts per sequence.

### Test J: heavy sequence playback control (2026-09-19)

User reports Test I silent on heavy, light hits audible. EML log at
2026-09-18T16:45:49 confirms I loaded, heavy sequence cloned (links=1),
itemRebinds=2. This proves initialization, not playback of that clone.

Test J removes I's heavy program/effect changes and uses original heavy impact.
Only the cloned Heavy_Sword_Diagonal SfxNotifierEvent with source sound
2545c5f6-a36d-425b-95ee-64e69e04d33e (event 27) changes to explosion sound.
All light hit behavior remains H. Test heavy swing into empty air: explosion
would establish playback of the modified heavy sequence. This is intentionally
NOT a hit-only test. Silence would point to sequence selection/playback/audio
rather than establish a failed heavy hit branch. No damage bytecode changes.
Staged test-j.lua and deployed with process/hash checks and pre-j backup.
Runtime marker [lightsaber] TEST J CONTROL. In-game result pending.

### Test K: experimental heavy post-damage spawn

User confirmed J heavy swing audible, then closed game. K removes swing marker.
Clones heavy program with original GroundHitTemplate/data intact; adds independent
audio template constant at aligned data end, layout index 61 (zero-based).
Redirects ApplyDamage calls at words 213,356,409,461 to appended trampolines.
Each trampoline runs original call, copies native spawn setup words 101..119,
changes only template operand to ffff003d, and jumps to original call successor.
Original code addresses remain fixed; 468 -> 564 words. Source layouts/calls
and native spawn block guarded before writes. Original damage parameters,
ground effect and configuration unchanged; light H test retained.

IMPORTANT: VM stack preservation (damage return below spawn arguments), jump
semantics and runtime behavior are still hypotheses, not validated guarantees.
No Lua parser available. This is a reversible experimental in-game test, not
exporter-ready code. May sound on blocked/unsuccessful damage attempts, or repeat
per collider. Verify heavy air/enemy hits plus damage/stun behavior. If crashes
or altered combat, restore H/J; do not claim enemy-only or damage-success gating.
Staged test-k.lua, backed up J with pre-k timestamp and hash-checked deployment.

### Export integration 0.28.4

User confirmed K: normal/heavy hits audible, misses silent, damage/stun normal.
Added core/hit_audio.py + packaged hit_audio.lua derived from K. Select an
in-game audio template in Hit (Experimental); its sound replaces the test tone.
Only the confirmed sword base is accepted for now. Attack Test A combination
is rejected because both independently clone/rebind the same sequences.
This does not add WAV/OGG import or prove enemy-only filtering.

Multiple Idle rows are accepted experimentally. A cloned SoundContainerResource
combines donor entries while a single weapon AudioComponent controls lifecycle;
the first donor supplies spatial settings. Simultaneous playback, looping and
sheath stopping of the combined entries require in-game testing. Single-idle
behavior remains unchanged. No live Lightsaber files changed by integration.
Python syntax and generated Lua string smoke checks passed; EML execution of
the generalized exporter and merged idle container not yet tested.

## Call-pattern audit and smaller alternatives

`--calls --types <types.json>` scans all programs for raw 0x13 words followed
two words later by reflected impact-node nameHash values. Results: 4,399 raw
0x13 occurrences, 384 unresolved, and zero recognized node hashes without
that prefix. Unresolved occurrences may be operands or other calls; do not
treat this as a complete disassembler. Counts include code and codeShutdown.

The probe ranks programs containing both ForEachHitEvent and SpawnEntity
patterns by total word count. Short alternatives to the gem chain:

- ab62b3ad-c260-46f9-9979-9628ed9e23d6: 83 words; ForEachHitEvent,
  GetRoot, IsSameEntity, SpawnEntity. Earlier variables include wasKillingBlow:
  likely needs kill-filter investigation, not automatically suitable for every hit.
- 82169841-f83e-49cb-a950-e7f0f8c22a11: 84 words; ForEachHitEvent,
  HasAttackCategory, SpawnEntity. Variables include wasCrit.
- decb17b9-9db5-43bd-a8be-8dee9659a097: 84 words; ForEachHitEvent,
  GetRoot, IsSameEntity, SpawnEntity. Variables include wasBlockBroken.

These are materially smaller investigation targets. Shared node presence does
not establish a path from hit to spawn or its conditions. Next: resolve owners,
spawn templates and conditional arguments for these candidates before cloning.
All scans completed read-only; no runtime changes or in-game verification.

## Small candidate resolved: Heal_Martyr

Program ab62b3ad-c260-46f9-9979-9628ed9e23d6 has 82 main words + one
shutdown word and eight variables. TemplateMartyr::value (configId 0x5653316e)
defaults to template 262ce15c-5f01-470a-a2b7-7079c6200c29, debugName Heal_Martyr.
The template contains AudioComponent AND AudioResourceComponent. The latter
directly references SoundContainer 6f25cc5e-67d5-42f3-82a2-9660aadcb847;
the referenced resource was successfully resolved as type 0xf257640c.
This is an actual assigned sound resource, not proof of audible playback.

The same template contains Impact, ImpactConfiguration, colliders and
SelectedTargets; it must NOT be reused unchanged as an audio-only effect.
wasKillingBlow is variable index 1. Raw words 40..45 are
`0x16, 0xffff0001, 0x09, 0x2e, 0x08, 0x03`: a plausible kill-condition
branch, still not a verified decoder. Root/target matching semantics also remain
unresolved. This may be a death response rather than an attacker-owned kill proc.

Full part-zero GUID-reference scan found only the program itself and resource
c4933fae-59c0-4b17-9482-669789d87e15. Reflection identifies the latter as
keen::ImpactRegistryResource (programs array at offset 0). It is a registry,
not evidence of item ownership; activation may use another identifier.

Comparison: decb17b9-9db5-43bd-a8be-8dee9659a097 references
4c2ae8b0-1f8d-45fd-912f-f0d9e93cbc9f,
Buff_Intelligence_Damage_Until_SpellDamage_10, with Impact/configuration,
LifeTime and StaticTransform but no direct audio resource. It includes
wasBlockBroken, so is not yet a generic hit-audio donor either.

Next decisive work: determine activation/ownership of the small hit program and
decode its root/target and kill-condition branches. A future audio-only template
clone must exclude healing/collision gameplay and have a verified lifetime.
No live mod changed; HIT_ENEMY remains blocked pending this work.
