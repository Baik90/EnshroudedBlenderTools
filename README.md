# Enshrouded Blender Tools

Blender extension for browsing, importing, editing, and exporting Enshrouded
KFC3 `keen::RenderModel` resources. The extension works through EML-generated
mods and never modifies the original KFC or DAT archives.

The current target is Blender 5.2 LTS and the Enshrouded game build documented
in `project_manifest.json`.

## Feature status

### Available

- Tabbed **3D View > Sidebar > Enshrouded** workspace:
  **Models**, **Components**, **Replacement**, and **New Model + Recipe**
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

Supported collider primitives are Box, Sphere, Spheroid, Cylinder, Capsule,
and Tapered Capsule. Collider export currently edits imported collider groups;
their number and shape must remain unchanged.

### Experimental or limited

- Full-topology export is limited to 65,535 generated vertices.
- All target LODs currently use the same generated replacement mesh.
- New models must clone an existing placeable template, ItemInfo, and recipe.
- Recipe ingredients, crafting station, category, comfort properties, and unlock
  conditions are inherited from the selected base recipe.
- Custom item icons are exported experimentally but are currently blank in the
  game UI. The required UI texture registration path is still unresolved.
- Blender cannot load Enshrouded's 3D DDS dissolve-noise textures.
- Custom texture export requires Microsoft `texconv.exe`.
- Custom textures must retain the target slot's dimensions and compressed format.
- A target material must already contain the texture slot being replaced.
- Components can be inspected, but arbitrary new component creation is not yet
  implemented.

## Installation

Install [enshrouded_tools.zip](enshrouded_tools.zip) through:

**Edit > Preferences > Get Extensions > Install from Disk**

The ZIP is a Blender extension package with `blender_manifest.toml` at its
archive root. Enable **Enshrouded Tools** if Blender does not enable it
automatically.

Set the Enshrouded installation directory in the extension preferences. Do not
select an individual KFC, DAT, or Mods file.

## Model import

1. Open **3D View > Sidebar > Enshrouded > Models**.
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
exporting a replacement. Do not add, remove, or change collider shapes yet.

To replace a material texture, use the folder button beside its named slot in
the Materials section. Keep the original dimensions and enable
**Export Custom Textures**. The exporter compresses the image with `texconv.exe`,
creates a new `keen::RenderMaterialResource`, and assigns that copy only to the
exported model. Other game models continue using the original material.

## Model replacement

Select an imported mesh and open the **Replacement** workspace.

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

## New model and recipe

The **New Model + Recipe** workspace creates a separate resource chain instead
of replacing the selected RenderModel:

1. Import and edit a game model to use as the mesh source.
2. Refresh **Placeable Bases**.
3. Select an original game item with the desired placement, comfort, crafting,
   and unlock behavior.
4. Enter the new item name and description.
5. Optionally select a 512 x 512, 8-bit RGBA PNG icon. Icon display is not yet
   working in-game.
6. Configure the Mod ID and export.

The exporter creates a new RenderModel, entity template, ItemInfo, and recipe.
The new recipe is inserted beside the selected base recipe in the crafting UI.
Name and description are added to every available localization collection, so
the entered text is currently the same for all languages.

Never select an item generated by another mod as the base. The extension hides
installed generated entries and validates stale selections before export.

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
```

Texture and icon files are included only when used. An existing folder matching
the exact Mod ID is replaced. Original files such as `enshrouded.kfc`,
`enshrouded.kfc_resources`, and `enshrouded_XXX.dat` are never patched by the
Blender extension.

## Current workflow

```text
Game Path -> Browse Model -> Import -> Edit -> Replacement or New Model + Recipe -> Export Mod
```

![Enshrouded Blender Tools](https://github.com/user-attachments/assets/6ae3c82c-4d0b-4ced-8448-9674cc6f7b25)
