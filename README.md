# Enshrouded Blender Tools

Blender extension for browsing, importing, editing, and exporting Enshrouded
**KFC3/KFC4** static `keen::RenderModel` resources. The extension generates
EML-compatible mods, also used with ShroudForge, and never modifies the original
KFC or DAT archives itself. The selected loader applies the exported changes.

This README describes **0.29.11**, targeting **Blender 5.2 LTS or newer**.
`project_manifest.json` records the historical KFC3 regression fixture, not the
current compatibility matrix. See [KFC4_SUPPORT.md](KFC4_SUPPORT.md) for the
validated KFC4 build, layout details, tests, and limitations.

## Feature status

### Available

- Tabbed **3D View > Sidebar > Enshrouded** workspace:
  **Browser**, **Components**, **Placeables**, **Equipment**, **Model Replacement**,
  and **Mod Builder**, in that order
- Search RenderModels by debug name or GUID
- Import one LOD or all available LODs
- Import geometry, UVs, custom normals, tangents, and bitangent handedness
- Correct Enshrouded-to-Blender axis conversion and triangle winding
- Put every imported model in its own root collection
- Import and assign multiple materials
- Extract and connect albedo, normal, RMA, and supported emissive textures
- Browse entity templates and their component lists
- Import primitive gameplay colliders
- Export topology-preserving replacements
- Export full-topology models with regenerated vertex and index streams
- Export multiple existing target material slots
- Create isolated material copies with custom textures
- Generate complete EML mod folders in a selected Mods directory
- Create a new model, placeable item, and crafting recipe from an existing base
- Set a custom item/recipe name and item description
- Register the new recipe beside its selected base recipe
- Filter previously generated mod resources from the placeable-base list
- Simple decoration authoring with stable new resource identities
- Optional Seat, FX, new box Collider, and Destructible functions
- Floor (default), Wall, and Ceiling placement selection
- Custom recipe ingredients, output count, and workshop through a recipe template
- Equipment/weapon bases, configurable item level, and audio events
- Combine saved exports into one installed mod through Mod Builder

Supported collider primitives are Box, Sphere, Spheroid, Cylinder, Capsule,
and Tapered Capsule. Existing-template export supports editing Box, Sphere, and
Capsule helpers with the original count and shape sequence preserved. Simple
placeables separately support creating multiple new box colliders.

### Experimental or limited

- Full-topology export is limited to 65,535 generated vertices.
- All target LODs currently use the same generated replacement mesh.
- New models still derive template, ItemInfo, and recipe structure from native
  resources. Simple mode selects the base internally and strips unrelated behavior;
  Advanced / Legacy exposes the donor selection.
- Recipe ingredients and output count are configurable. The selected recipe
  template determines the workstation, menu grouping, unlock rules, and extra
  requirements. This does not create arbitrary new crafting stations.
- Custom icon UI texture registration is implemented. The old blanket limitation
  that icons are always blank no longer describes the exporter; verify display
  with your loader.
- Blender cannot load Enshrouded's 3D DDS dissolve-noise textures.
- Custom texture export requires Microsoft `texconv.exe`.
- Custom texture dimensions are supported; the compressed format and target slot
  must still be compatible. Arbitrary Blender shaders are not converted.
- A target material must already contain the texture slot being replaced.
- Components can be inspected, but arbitrary new component creation is not yet
  implemented.
- Generated topology is static; armature/skinning export is not implemented.
- Wall/ceiling placement and configurable destruction need further in-game tests.

## Installation

Install [enshrouded_tools.zip](enshrouded_tools.zip) through:

**Edit > Preferences > Get Extensions > Install from Disk**

The ZIP contains the extension folder and its `blender_manifest.toml`.
Enable **Enshrouded Tools** if Blender does not enable it
automatically.

Set the Enshrouded installation directory in the extension preferences. Do not
select an individual KFC, DAT, or Mods file. Configure `texconv.exe` there if
exporting custom textures. After reinstalling, check that Game Path is still set.
Restart Blender after updating the extension to unload older Python modules.

## Model import

1. Open **3D View > Sidebar > Enshrouded > Browser**.
2. Refresh the RenderModel list.
3. Filter by a debug-name fragment or GUID.
4. Select the desired LOD and import options.
5. Click **Import Model**.

The imported mesh stores its source model GUID and resource metadata as Blender
custom properties. The game coordinate convention is converted using
**Forward -Z / Up +Y**.

Imported material textures use these conventions:

- BC7 sRGB: albedo
- BC5: normal map
- BC1/compatible RMA: red = Metalness, green = Roughness, blue = Ambient Occlusion
- Supported BC6H HDR maps: emission

## Components, colliders, and materials

The **Components** workspace finds entity templates that reference the selected
RenderModel and lists their known and unknown components.

Collider import creates editable Blender objects in a `Colliders` collection.
Move, rotate, or scale these objects and enable **Export Colliders** when
exporting a replacement. Preserve count and shapes in this existing-template
workflow; use Simple mode's Add Collider for new box colliders.

To replace a material texture, use the folder button beside its named slot in
the Materials section. Custom image dimensions are supported. Enable
**Export Custom Textures**. The exporter compresses the image with `texconv.exe`,
creates a new `keen::RenderMaterialResource`, and assigns that copy only to the
exported model. Other game models continue using the original material.

## Model replacement

Select an imported mesh, or choose a collection where supported, and open the
**Model Replacement** workspace.

### Topology Preserving

Use this for edits that keep the original vertex count. It retains the source
index layout and unchanged vertex data while exporting edited positions.

### Full Topology

Use this to regenerate the complete 24-byte static vertex stream and uint16
index stream from the evaluated Blender mesh. Polygons are triangulated and
loop corners become independent game vertices. Positions, UVs, normals,
tangents, handedness, bounds, mesh ranges, and buffer ranges are regenerated.

The **Target GUID** determines which game RenderModel is replaced. It defaults
to the selected imported model.

## Placeables

The **Placeables** workspace creates a separate RenderModel, entity template,
ItemInfo, and recipe rather than replacing an existing model.

Choose **Simple** or **Advanced / Legacy**. Immediately below are **Item Name**,
**Description**, **Item Icon**, and placement: **Floor** (default), **Wall**, or
**Ceiling**. Icons must be 512 x 512, 8-bit RGBA PNG files. Names and descriptions
are added to localization collections with the same entered text for all languages.

For a multi-object model, choose **Export Source: Collection** and select the
collection containing the meshes and helpers. Selecting only one mesh does not
export the entire collection. Placement selection controls allowed surfaces in
the build cursor; it does not automatically rotate or reposition Blender geometry.
Wall/ceiling placement and orientation still require in-game verification.

### Simple functions

Simple creates a decoration from an internal known base with stable new resource
identities. You do not need to find a donor matching the desired behavior.
It still derives low-level item/template/recipe structure from game resources.

| Function | Configuration |
| --- | --- |
| Chair / Seat | Create a position Empty and move/rotate it to define the seat |
| FX | Load Available FX, select an effect, and position its Empty |
| Collider | Add one or more wireframe box helpers |
| Destructible | Set 1–65,535 health, Wood/Stone/Metal, and optional base destruction effects |

One Seat, one FX, and one Destructible function are supported per object;
multiple box colliders are supported. Seat/FX Empties must keep unit scale.
Edit collider position, rotation, and scale in **Object Mode**: do not apply
scale or edit helper mesh vertices. Helpers are excluded from rendered geometry.

Destructible requires a Collider function. Gameplay material controls damage
susceptibility and hit feedback, independently of visible Blender materials.
Optional destruction effects reuse the base wooden stool's `OnDestroy` behavior;
custom loot drops are not provided. Without this function, inherited base health
remains unchanged.

Placement, seating, colliders, and FX have been tested in-game. The displaced
seat prompt and inability to pick up the object when using FX were subsequently
reported fixed by the user. Configurable health/material and optional destruction
effects still need their own in-game verification.

See [OBJECT_AUTHORING.md](OBJECT_AUTHORING.md) for implementation history and
validation details. Older dated observations there describe earlier builds.

### Advanced / Legacy

Use **Load Placeable Bases** to explicitly select an original template, ItemInfo,
and RenderModel. This exposes the earlier donor workflow for specialized behavior;
comfort and other properties can remain inherited. Import Base Helpers allows
editing supported collider and effect attachment helpers.

Never select another mod's generated item as the base. The extension hides
installed generated entries and validates stale selections.

### Custom Recipe

Enable **Custom Recipe**, then **Load Crafting Choices**. Choose a
**Workshop / Recipe Template**, ingredient items/counts, and output count.
Items are shown with readable internal names and short GUIDs for disambiguation.
The recipe template determines the workshop and inherited extra rules; without a
custom recipe, the base recipe is used. New recipes are inserted alongside their
selected donor in the crafting UI.

## Equipment and audio

**Equipment** includes equipment and weapon bases. Export requires a compatible
base and supported visual model/template structure. Equipment level can be
inherited, fixed, or restricted to a configured range within **1–105**.

Enable **Custom Audio**, then **Add Sound Event** for Idle, Attack, or Hit with
vanilla game audio templates or custom WAV files.

- Custom audio must be **uncompressed PCM16 WAV, exactly 48,000 Hz**, mono or stereo.
- Export validates sample rate, format, and contents. Stereo is mixed to mono.
- Custom Idle WAVs loop; vanilla Idle retains its source loop settings. Idle
  stops when the weapon is put away.
- The current event exporter accepts **one Idle event**. Multiple simultaneous
  Idle layers are not verified and are rejected by this path.
- Multiple Attack or Hit entries select a random variant per playback, not a
  sequential one. Hit does not guarantee enemy-only filtering.
- Attack/Hit integration uses the tested sword workflow, not every weapon or
  animation. Draw and Sheathe are not exposed in the current add-on UI.

Development tests include light/heavy sword hits. Specialized Attack/Hit bytecode
validation remains tied to older layouts and can reject KFC4 assets. These earlier
tests do not establish general compatibility with the current game build.

## Mod Builder

The last tab combines multiple saved exports into one installed mod.

1. Set Mod ID, name, version, and author, then **Create Mod**, or choose an existing
   editable project in the automatically scanned game Mods directory.
2. Check the intended mod. Only **one export target** can be active. This checkmark
   does not change the mod loader's enabled state.
3. In an export tab, choose **Add to Mod**. It is disabled without an editable target.
4. Inspect saved entries in the tree. Entries can be selected for update, enabled/
   disabled, or removed. After editing in Blender, use **Update Mod Entry**.
5. Close the game and use **Build Mod** to write the checked mod to the Mods directory.

Entries are **saved export snapshots**, not live links to Blender objects. Scene
edits do not update snapshots until you export again. Recognized standalone
BlenderTools exports can be made editable with **Adopt into Mod Builder**;
unrecognized third-party mods remain read-only.

Builds preserve backups under `<Enshrouded>/.ebt-backups/`. Mixed KFC3/KFC4
snapshots and snapshots incompatible with the installed archive format are
rejected: update old entries before building.

## Generated mod

By default, export writes to:

```text
<Enshrouded>/mods/<mod_id>/
```

Typical output:

```text
mod.json
validation.json
render_data.bin
src/mod.lua
textures/...
item_icon.png
crafting.json
custom_audio/...
```

Texture, icon, crafting, and audio files are included only when used. Builder
projects additionally use `project.json`, `snapshots/`, and assembled `entries/`.
Standalone **Export Mod** replaces the folder matching the exact Mod ID. Keep
backups and do not export over unrelated mods. Close the game before replacing
an installed mod. Original files such as `enshrouded.kfc`,
`enshrouded.kfc_resources`, and `enshrouded_XXX.dat` are never patched by the
Blender extension. The selected loader has its own archive application, backup,
and recovery behavior.

## Current workflow

```text
Game Path -> Browser -> Import/Edit -> Placeables / Equipment / Model Replacement
                                     -> Export Mod
                                     -> Add to Mod -> Mod Builder -> Build Mod
```

![Enshrouded Blender Tools](https://github.com/user-attachments/assets/6ae3c82c-4d0b-4ced-8448-9674cc6f7b25)
