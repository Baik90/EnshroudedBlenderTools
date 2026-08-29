import bpy
from bpy.types import Panel, UIList


class ENSHROUDED_UL_render_models(UIList):
    """Compact, searchable RenderModel list with Blender-native scrolling."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.label(text=item.name, icon="MESH_DATA")
        else:
            layout.alignment = "CENTER"
            layout.label(text="", icon="MESH_DATA")

    def draw_filter(self, context, layout):
        layout.prop(
            context.scene.enshrouded,
            "model_filter",
            text="",
            icon="VIEWZOOM",
        )

    def filter_items(self, context, data, property_name):
        items = getattr(data, property_name)
        query = data.model_filter.strip().casefold()
        if not query:
            return [], []
        flags = [
            self.bitflag_filter_item
            if query in item.name.casefold() or query in item.guid.casefold()
            else 0
            for item in items
        ]
        return flags, []

class ENSHROUDED_PT_main(Panel):
    bl_label = "Enshrouded"
    bl_idname = "ENSHROUDED_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Enshrouded"

    def draw(self, context):
        layout = self.layout
        props = context.scene.enshrouded
        prefs = context.preferences.addons[__package__].preferences

        box = layout.box()
        box.label(text="Game", icon="FILE_FOLDER")
        if prefs.game_path:
            box.label(text=prefs.game_path)
        else:
            box.label(text="Set game path in Add-on Preferences", icon="ERROR")
        box.label(text="Main archives only; Mods ignored", icon="LOCKED")

        box = layout.box()
        header = box.row(align=True)
        header.label(text=f"RenderModels ({len(props.models)})", icon="MESH_DATA")
        header.operator("enshrouded.load_model_list", text="", icon="FILE_REFRESH")
        box.template_list(
            "ENSHROUDED_UL_render_models",
            "",
            props,
            "models",
            props,
            "model_index",
            rows=9,
        )

        if props.resolved_guid:
            details = box.column(align=True)
            details.label(text=props.resolved_name)
            guid_row = details.row(align=True)
            guid_row.prop(props, "resolved_guid", text="GUID")
            guid_row.operator("enshrouded.copy_guid", text="", icon="COPYDOWN")

        box = layout.box()
        box.label(text="Import Settings")
        box.prop(props, "lod")
        box.prop(props, "import_uvs")
        box.prop(props, "import_materials")
        texture_row = box.row()
        texture_row.enabled = props.import_materials
        texture_row.prop(props, "import_textures")
        box.prop(props, "import_all_lods")
        box.prop(props, "import_colliders")
        row = box.row()
        row.enabled = bool(props.resolved_guid)
        row.operator("enshrouded.import_model", icon="IMPORT")

        box = layout.box()
        box.label(text="Export Mod", icon="PACKAGE")
        box.prop(props, "export_mode")
        box.prop(props, "export_target_guid")
        folder_row = box.row(align=True)
        folder_row.prop(props, "export_directory")
        folder_row.operator("enshrouded.use_default_export_folder", text="", icon="LOOP_BACK")
        box.prop(props, "mod_id")
        box.prop(props, "mod_name")
        row = box.row(align=True)
        row.prop(props, "mod_version")
        row.prop(props, "mod_author")
        if props.export_mode == "FULL_REPLACEMENT":
            box.label(text="Experimental: regenerates topology", icon="ERROR")
            box.label(text="Uses target material slot 0", icon="INFO")
        elif props.export_mode == "REPLACEMENT":
            box.label(text="First exporter: positions only", icon="INFO")
            box.label(text="Keep original vertex count", icon="INFO")
        box.label(text="Existing mod folder will be replaced", icon="ERROR")
        row = box.row()
        active = context.active_object
        row.enabled = bool(
            props.export_mode in {"REPLACEMENT", "FULL_REPLACEMENT"}
            and active is not None
            and active.type == "MESH"
            and active.get("enshrouded_guid")
        )
        row.operator("enshrouded.export_replacement", icon="EXPORT")

        layout.prop(props, "show_debug", toggle=True)
        if props.show_debug:
            box = layout.box()
            box.label(text=f"Resource index: {props.resource_index}")
            box.label(text=f"Content index: {props.content_index}")

_classes = (ENSHROUDED_UL_render_models, ENSHROUDED_PT_main)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
