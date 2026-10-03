# Mod Builder

0.28.15: Standalone BlenderTools exports can be adopted in place. Expand the
mod row and click Adopt into Mod Builder. The existing export is copied into
a snapshot and becomes the first project entry; metadata is inherited from
mod.json. The new project is selected automatically. Existing runtime files
remain intact until Build Mod is pressed. Mesh size/hash is verified against
validation.json. Foreign mods and invalid existing project files are not
overwritten. A valid standalone export requires its generated src/mod.lua,
mod.json, validation.json and render_data.bin. No manual project.json copying
is necessary. Tests: tools/test_mod_adoption.py.

0.28.11: Metadata and Create Mod appear above the mod tree. Project File,
Open/Refresh Project, Save Metadata and Build Directory are no longer shown.
Build Mod saves Name/Version/Author and installs the build into the checked
project's existing game/mods/<mod-id> folder. Mod ID remains fixed after creation.
Only src, entries and mod.json are replaced; project.json and snapshots remain.
Previous build files are backed up outside mods in game/.ebt-backups; failed
installation rolls back replaced paths. Close the game before building.
This supersedes the separate-build-directory workflow described below.

0.28.10: The builder shows an expandable mod/export tree. While its tab is open,
the game's `mods` directory is scanned every three seconds, outside UI drawing.
Refresh triggers a manual scan. Create Mod now uses that directory automatically.
The checkbox selects the single write target (click it again to clear it); it
does not enable/disable mods in EML. Foreign mods without a valid project.json
are displayed read-only. Explicitly opened external projects remain visible.
Entry visibility buttons still control inclusion in a build, separately from
the parent mod's write-target checkbox. Build deployment remains unchanged.

The last workspace tab manages BlenderTools projects (`project.json`), not
arbitrary existing EML mods. Create a project in a workspace directory, or select
an existing project file and click Open / Refresh Project. Mod ID is fixed on
creation; Save Name / Version / Author updates the remaining metadata.

In Placeables, Equipment or Model Replacement, configure the source and export
settings as usual and click Add to Mod. This creates an independent snapshot,
without installing or overwriting a game mod. The button is disabled until a
project is created/opened. Export Mod remains the standalone export workflow.

The builder lists saved entries, their type and UTC export time. Checkbox buttons
enable/disable entries. X removes an entry from the manifest; its files remain
in `snapshots` for recovery. The refresh button selects an update target and
opens its export tab. Select the correct Blender object/collection and configure
its settings before clicking Update Mod Entry. This does NOT restore Blender
objects or export settings from the snapshot. Updates retain the entry ID and
old snapshot directory. Adding always creates a separate entry.

Build Mod produces a fresh `<mod-id>_build_<suffix>` directory containing one
top-level EML mod. Install only one build of that mod. This intentionally does
not replace an installed mod. Export filenames are scoped under entry IDs;
entry Lua locals and io.read paths are isolated. Recipe selection uses the
currently bound registry so successive entries preserve earlier additions.
Conflicting replacements/base models are rejected. Builds use stored snapshots,
not later unexported Blender changes. Older projects' snapshots must be updated
to receive changes to the export generator.

Automated snapshot/build/UI-registration checks: `tools/test_mod_project.py`.
Combined recipes, materials and audio still require in-game validation. Start
with two simple placeables, then add equipment. The known Attack sound looping
issue is not changed by this UI/project feature.
