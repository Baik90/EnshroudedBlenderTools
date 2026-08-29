## Feature status

### Available

- ✅ Browse and search KFC3 `keen::RenderModel` resources
- ✅ Resolve models by debug name or GUID
- ✅ Import selectable LODs and all available LODs
- ✅ Import geometry with correct axis conversion and triangle winding
- ✅ Import UVs, custom normals, tangents, and bitangent handedness
- ✅ Import material names, albedo maps, normal maps, and RMA maps
- ✅ Import BC6H HDR emissive maps with a basic emission shader connection
- ✅ Export custom replacements for existing albedo, normal, RMA, and emissive slots
- ✅ Import and assign multiple materials
- ✅ Export multiple existing target material slots with full topology
- ✅ Import gameplay Box, Sphere, and Capsule colliders from entity templates
- ✅ Browse referencing entity templates and their existing components
- ✅ Export transformed existing Box, Sphere, and Capsule colliders as template patches
- ✅ Export topology-preserving RenderModel replacement mods
- ✅ Choose a target GUID and custom mod export folder
- ✅ Generate complete EML mod folders without modifying game archives

### Experimental or limited

- ⚠️ Full-topology RenderModel replacement export is experimental
- ⚠️ Full-topology export supports multiple existing target material slots
- ⚠️ Full-topology export is limited to 65,535 generated vertices
- ⚠️ All target LODs currently use the same generated replacement mesh
- ⚠️ Blender cannot import Enshrouded's 3D DDS dissolve-noise textures
- ⚠️ Custom texture export requires Microsoft `texconv.exe`
- ⚠️ Custom textures must retain the target slot's resolution and compressed format

### Not available yet

- ❌ In-game-verified arbitrary-topology replacement export
- ❌ Multiple meshes and materials in full-topology export
- ❌ Creating a completely new `keen::RenderModel` with a new GUID
- ❌ Creating furniture, decoration resources, or crafting recipes
- ❌ Creating new material resources or adding texture slots

## Installation (Blender 5.2 LTS)

Install `enshrouded_tools.zip` through Blender's **Edit > Preferences > Get
Extensions > Install from Disk**. The ZIP is a Blender extension package and has
`blender_manifest.toml` at its archive root.

After installation, enable **Enshrouded Tools** if Blender does not enable it
automatically. The panel is available in **3D View > Sidebar > Enshrouded**.

Configure the Enshrouded game directory in the add-on preferences, then click
the refresh button in the RenderModels panel. The searchable list uses Blender's
native scrolling list. Select a model and LOD, then use **Import Model** to create
the Blender mesh with packed positions, triangle indices, UVs and custom normals.
Decoded tangents and bitangent signs are retained as mesh point attributes.
Referenced Keen materials are imported with their debug names. BC7 albedo and
BC5 normal textures are connected to Principled BSDF. The BC1 RMA material map
uses red for Metallic, green for Roughness, and blue as an Ambient Occlusion
multiplier on the albedo.

The game model convention is converted with Blender's standard import settings
**Forward -Z / Up +Y**.

## Replacement export

Select an imported Enshrouded mesh and choose **Model Replacement** in the
Export Mod panel. The first exporter is deliberately topology-preserving: the
vertex count and original renderData layout must remain unchanged. It exports
edited positions while retaining the original index buffer, UVs, vertex-frame
bytes, colors, and material references.

The editable **Target GUID** determines which RenderModel is replaced and is
pre-filled from the selected/imported model. The model-browser GUID is shown in
a selectable text field and can also be copied with the adjacent button.

The generated EML mod contains `mod.json`, `src/mod.lua`, `render_data.bin`, and
`validation.json` below `<game>/mods/<mod_id>`. An existing folder with exactly
the selected Mod ID is replaced. Original KFC and DAT archives are never
modified.

The export folder can be selected in the panel. Its default is `<Game Path>/mods`;
the reset button beside the field restores that location.

### Custom texture replacement

Set the path to Microsoft's `texconv.exe` in the add-on preferences. In the
Materials panel, use the folder button beside `albedo_map_0`, `normal_map_0`,
`material_map_0`, or `emissive_map_0` to assign an externally saved image.
Keep the original image dimensions, enable **Export Custom Textures**, and
export the replacement mod. The exporter compresses each changed image to the
target slot's original BC format and mip count and writes the payload below the
mod's `textures` directory.

This replaces existing texture content only. It does not yet create a new
material resource or add a texture slot that the target material does not have.

### Experimental full-topology replacement

Choose **Full Topology Replacement (Experimental)** to regenerate the complete
24-byte static vertex stream and uint16 index stream from the evaluated Blender
mesh. Polygons are triangulated, loop corners become independent game vertices,
and positions, UVs, normals, tangents, handedness, bounds, and buffer ranges are
written anew. All target LOD entries are redirected to the generated mesh, which
uses material slot 0 of the target RenderModel.

This path is structurally validated but still requires in-game testing. It is
limited to 65,535 generated vertices and one target material/mesh.

The target user workflow is:

`Game Path -> Model name/GUID -> Import Model -> Edit -> Export Replacement Mod`.
<img width="1920" height="1032" alt="grafik" src="https://github.com/user-attachments/assets/6ae3c82c-4d0b-4ced-8448-9674cc6f7b25" />
