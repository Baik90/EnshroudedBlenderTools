# Simple placeable authoring — experimental 0.29.0

Update 0.29.2: KFC4 Simple/Legacy static export is implemented and the writer gate
is removed. Geometry roundtrips, texture mip/tail generation, Blender export and
Lua syntax are checked. Begin the in-game test with decoration and no functions;
then test seating and FX separately. No successful game execution of these new
paths is claimed yet. This supersedes the earlier reader/export boundary below.

Update 0.29.1: the archive reader and tested static imports now support KFC4.
See KFC4_SUPPORT.md. Export still requires migration to the new RenderModel and
material schemas; the Simple/Legacy KFC4 writer is blocked explicitly. The
historical investigation notes below describe the earlier 0.29.0 boundary.

Placeables now defaults to Simple. Advanced / Legacy retains manual template
selection and the previous helper/collider workflow. Equipment is unchanged.

Simple assigns a persistent authoring UUID to the exported mesh or collection.
Model, template, item, name, description and recipe UUIDs are derived from that
identity. Re-exporting the same source preserves these IDs. Duplicating Blender
objects/collections can copy custom properties; remove `enshrouded_object_guid`
on a duplicate before exporting it as a distinct item. Avoid loading the same
object identity from two mods at once.

The user does not choose a base template. Internally this first implementation
uses the existing tested roughwood stool model/item/template chain as a donor.
It creates distinct resources and strips template components to an explicit
render/transform allowlist before applying optional functions. This is not yet
a completely donor-free resource writer. No physical collision is generated in
Simple. Placement rules/material capacity still originate from the donor; the
existing exporter validates its mesh/material limits. Without a custom recipe,
the donor's recipe is used. Custom Recipe remains available.

Add Chair Function adds a seating entry and Create Position Empty makes an
ARROWS helper. Move/rotate the Empty to define the seat's guest offset. Add FX
Function adds an effect entry with a position Empty and searchable Load Available
FX list. FX resources are enumerated rather than assigned guessed display names.
One seat and one FX are supported initially, since duplicate ECS component types
must not be appended blindly. Removing a function retains its Empty to avoid
deleting authoring work. Empty scale must remain 1. Helpers can be outside the
export collection; only explicitly referenced helpers are exported.

## Evidence and unresolved validation

- 0.29.10 adds one optional Destructible function: maxHealth 1..65535, gameplay
  material Wood/Stone/Metal and opt-in base-stool OnDestroy effects. A Collider
  function is required. Export resolves a native template with the selected
  susceptibility and copies its material reference and materialId, but not its
  loot, item reference, health or other behavior. Defaults remain backward
  compatible: without this function the inherited base-stool health is unchanged.
  Render materials/textures remain independent. Blender regression tests cover
  configuration snapshots, bounds, duplicates and opt-in notifier generation.
  All three material donors resolve in the local KFC4 archive. Actual damage,
  health initialization and destruction effects need in-game verification.

- 2026-10-20: user reports 0.29.8 did not change prompt/pickup behavior. Read-only
  inspection confirms the installed generated Lua and patched KFC contain both
  0.29.8 changes, and the loader marks the mod applied. Component-array audit:
  12,268 templates, 12,267 sorted by qualified component name; the only unsorted
  template is our custom object dc7f678e-7ae4-5591-ae9e-87e88875d756. Version
  0.29.9 restores that ordering after adding all functions and rejects duplicate
  component types. This corrects an observed structural discrepancy, but static
  inspection does not prove the engine requires sorting or that it explains
  the reported runtime symptoms. A new game test remains necessary.

- 2026-10-20: user confirms seating and box collision with FX, but reports a
  displaced sit prompt and inability to pick up the placed object. Version
  0.29.8 explicitly sets UiOffsets.interactionPromptOffset to the seat anchor
  plus 0.6 m world-up, preserves the donor's Destructible marker, and adds
  DismantleOverride/PickUp without bypassing build-zone checks. It does not
  restore donor OnDestroy or loot behavior. These are candidate corrections:
  the specific reason FX moves the prompt is not established by static data,
  and prompt placement/pickup after the changes still require an in-game test.

- 2026-10-20 FX failure: ShroudForge startup log reports `at value.fxHandle:
  expected keen::ecs::LoopedFxHandle, got nil`, then restores the baseline without
  asset mods. This explains the missing custom recipe, rather than an FX recipe
  visibility rule. Version 0.29.7 supplies inherited FxComponent fields
  fxHandle={value=0}, toggleModifier={} and explicitly attaches to Self/Root.
  Current reflection confirms the handle struct and modifier bitmask types.
  In-game loading and rendering after this fix remain unverified.

- 2026-10-20: user confirmed KFC4 placement and custom box collision in game.
  Seating still shows a locked interaction and incorrect attachment behavior.
  Current KFC4 stool and chair templates have enableWaterLock=true and include
  IsInWaterCheck. The first seat allowlist copied the lock but omitted that
  dependency. Version 0.29.6 copies it and rejects an incomplete water-lock donor.
  Prompt, animation and attachment alignment after this fix need a fresh game test.
  Keep an explicit Collider function for interaction targeting.

- Source inspection: existing export creates clones, reads ItemInfo equipment
  placedEntity, and handles effect offsets through a basis conjugation.
- Static reflection cache for build 1076226: InteractionAttachment has
  guestOffset (ecs::Offset) at 0, containing localOffset, worldOffset and
  orientationOffset. VfxComponent has attachmentOffset at 8; its paired resource
  component contains vfx at 0. VfxResource debugName is at 116.
- Local archive inspected 2026-10-19: enshrouded.kfc magic is KFC4. The current
  reader rejects this format; old cached type layouts cannot establish current
  KFC4 compatibility. No archive was altered. Reader errors explain the boundary.
- Seat function copies the known donor's interaction component set and checks
  for exactly one InteractionAttachment and InteractionOffer. The completeness
  of that set and actual animation alignment are NOT verified in-game.
- Decoration rendering, placement persistence, item placement bounds, FX
  attachment and seat behavior need live verification after KFC4 support is
  implemented. Do not label this version ready for the updated game.
- REA MCP/CLI unavailable in the session; observations above came from the
  existing format parser, exported fixtures and JSON reflection, not REA output.

Checks: tools/test_object_authoring.py verifies stable IDs, transformed seat
helpers, generated decoration/seat/FX code, snapshot export and Legacy isolation.
Existing audio and Mod Builder tests also pass. These checks do not execute Lua
inside the game. tools/probe_placeable_functions.py is a read-only inventory for
the supported KFC3 layout and currently reports the KFC4 boundary.
# Box colliders (0.29.4)

In Simple mode, choose **Add Collider** in the functions list. Each entry creates
an editable wireframe box in the export collection. Multiple boxes are supported.
Move, rotate and scale these helpers in **Object Mode**. Do not apply scale or
edit their mesh vertices: export uses the stored primitive dimensions and object
transform. Helpers are excluded from render geometry. Removing a function stops
exporting its collider but keeps the Blender helper so it can be reused.

Export retains the donor's static collision configuration and box flags, replaces
its shape list, and does not add chair, destructibility or other unrelated behavior.
Blender tests cover multiple boxes, coordinate conversion and positive dimensions.
Runtime collision behavior still requires an in-game test.

