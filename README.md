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

The target user workflow is:

`Game Path -> Model name/GUID -> Resolve -> Import Model`.
