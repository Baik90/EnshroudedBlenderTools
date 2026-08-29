import bpy
from bpy.types import Panel, UIList


class ENSHROUDED_UL_render_models(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.name if self.layout_type != "GRID" else "", icon="MESH_DATA")

    def draw_filter(self, context, layout):
        layout.prop(context.scene.enshrouded, "model_filter", text="", icon="VIEWZOOM")

    def filter_items(self, context, data, property_name):
        items = getattr(data, property_name)
        query = data.model_filter.strip().casefold()
        if not query:
            return [], []
        return [
            self.bitflag_filter_item
            if query in item.name.casefold() or query in item.guid.casefold()
            else 0 for item in items
        ], []


class ENSHROUDED_UL_templates(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.label(text="", icon="FILE_3D")
            return
        row = layout.row(align=True)
        row.label(text=item.name, icon="FILE_3D")
        if item.collider_count:
            row.label(text=str(item.collider_count), icon="PHYSICS")


class ENSHROUDED_UL_components(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.label(text="", icon="MODIFIER")
            return
        row = layout.row(align=True)
        row.label(text=item.name, icon="CHECKMARK" if item.supported else "DOT")
        row.label(text=item.type_hash)


class _EnshroudedPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Enshrouded"


class ENSHROUDED_PT_models(_EnshroudedPanel, Panel):
    bl_label = "Model Browser"
    bl_idname = "ENSHROUDED_PT_models"

    def draw(self, context):
        layout = self.layout
        props = context.scene.enshrouded
        prefs = context.preferences.addons[__package__].preferences
        game = layout.box()
        game.label(text="Game", icon="FILE_FOLDER")
        game.label(text=prefs.game_path or "Set game path in Add-on Preferences")
        header = layout.row(align=True)
        header.label(text=f"RenderModels ({len(props.models)})", icon="MESH_DATA")
        header.operator("enshrouded.load_model_list", text="", icon="FILE_REFRESH")
        layout.template_list(
            "ENSHROUDED_UL_render_models", "", props, "models", props, "model_index", rows=9
        )
        if props.resolved_guid:
            layout.label(text=props.resolved_name)
            row = layout.row(align=True)
            row.prop(props, "resolved_guid", text="GUID")
            row.operator("enshrouded.copy_guid", text="", icon="COPYDOWN")


class ENSHROUDED_PT_import(_EnshroudedPanel, Panel):
    bl_label = "Model Import"
    bl_idname = "ENSHROUDED_PT_import"

    def draw(self, context):
        layout = self.layout
        props = context.scene.enshrouded
        layout.prop(props, "lod")
        layout.prop(props, "import_uvs")
        layout.prop(props, "import_materials")
        row = layout.row()
        row.enabled = props.import_materials
        row.prop(props, "import_textures")
        layout.prop(props, "import_all_lods")
        layout.prop(props, "import_colliders")
        row = layout.row()
        row.enabled = bool(props.resolved_guid)
        row.operator("enshrouded.import_model", icon="IMPORT")


class ENSHROUDED_PT_components(_EnshroudedPanel, Panel):
    bl_label = "Components"
    bl_idname = "ENSHROUDED_PT_components"

    def draw(self, context):
        layout = self.layout
        props = context.scene.enshrouded
        row = layout.row()
        row.enabled = bool(props.resolved_guid)
        row.operator("enshrouded.load_components", icon="FILE_REFRESH")
        layout.label(text=f"Referencing Templates ({len(props.templates)})")
        layout.template_list(
            "ENSHROUDED_UL_templates", "", props, "templates", props, "template_index", rows=4
        )
        if not 0 <= props.template_index < len(props.templates):
            layout.label(text="Load templates for the selected model", icon="INFO")
            return
        template = props.templates[props.template_index]
        layout.prop(props, "template_guid", text="Template GUID")
        layout.label(text=f"Components ({len(template.components)})")
        layout.template_list(
            "ENSHROUDED_UL_components", "", template, "components", props, "component_index", rows=7
        )
        if 0 <= props.component_index < len(template.components):
            component = template.components[props.component_index]
            layout.label(text=f"Mapped data size: {component.data_size} bytes")


class ENSHROUDED_PT_colliders(_EnshroudedPanel, Panel):
    bl_label = "Colliders"
    bl_idname = "ENSHROUDED_PT_colliders"

    def draw(self, context):
        layout = self.layout
        props = context.scene.enshrouded
        if 0 <= props.template_index < len(props.templates):
            template = props.templates[props.template_index]
            layout.label(text=template.name, icon="FILE_3D")
            layout.label(text=f"Gameplay colliders: {template.collider_count}", icon="PHYSICS")
        else:
            layout.label(text="Select a template in Components", icon="INFO")
        layout.operator("enshrouded.import_template_colliders", icon="IMPORT")
        layout.label(text="Box, Sphere and Capsule supported", icon="INFO")
        layout.label(text="Edit with Move, Rotate and Scale", icon="ORIENTATION_LOCAL")


class ENSHROUDED_PT_materials(_EnshroudedPanel, Panel):
    bl_label = "Materials"
    bl_idname = "ENSHROUDED_PT_materials"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            layout.label(text="Select an imported model mesh", icon="INFO")
            return
        slots = ("albedo_map_0", "normal_map_0", "material_map_0", "emissive_map_0")
        for material_slot in obj.material_slots:
            material = material_slot.material
            if material is None:
                continue
            box = layout.box()
            box.label(text=material.name, icon="MATERIAL")
            guid = material.get("enshrouded_guid", "")
            if guid:
                box.label(text=guid)
            if not material.use_nodes:
                continue
            for slot_name in slots:
                node = material.node_tree.nodes.get(slot_name)
                if node is None or node.type != "TEX_IMAGE":
                    node = next(
                        (
                            candidate for candidate in material.node_tree.nodes
                            if candidate.type == "TEX_IMAGE"
                            and candidate.get("enshrouded_slot", "") == slot_name
                        ),
                        None,
                    )
                row = box.row(align=True)
                row.label(text=slot_name)
                if node is not None:
                    row.template_ID(node, "image")
                    image = node.image
                else:
                    row.label(text="Not assigned")
                    image = None
                choose = row.operator(
                    "enshrouded.select_material_texture", text="", icon="FILE_FOLDER"
                )
                choose.material_name = material.name
                choose.slot_name = slot_name
                if image is not None and (
                    not image.get("enshrouded_content_hash", "")
                    or image.get("enshrouded_slot", "") != slot_name
                ):
                    box.label(text=f"Custom: {slot_name}", icon="CHECKMARK")


class ENSHROUDED_PT_export(_EnshroudedPanel, Panel):
    bl_label = "Export Mod"
    bl_idname = "ENSHROUDED_PT_export"

    def draw(self, context):
        layout = self.layout
        props = context.scene.enshrouded
        layout.prop(props, "export_mode")
        layout.prop(props, "export_target_guid")
        layout.prop(props, "export_colliders")
        if props.export_colliders:
            layout.label(text="Collider count and shapes must remain unchanged", icon="INFO")
        layout.prop(props, "export_textures")
        if props.export_textures:
            layout.label(text="Uses external images and texconv.exe", icon="IMAGE_DATA")
        row = layout.row(align=True)
        row.prop(props, "export_directory")
        row.operator("enshrouded.use_default_export_folder", text="", icon="LOOP_BACK")
        layout.prop(props, "mod_id")
        layout.prop(props, "mod_name")
        row = layout.row(align=True)
        row.prop(props, "mod_version")
        row.prop(props, "mod_author")
        if props.export_mode == "FULL_REPLACEMENT":
            layout.label(text="Experimental: regenerates topology", icon="ERROR")
            layout.label(text="Uses existing target material slots", icon="INFO")
        elif props.export_mode == "REPLACEMENT":
            layout.label(text="Keep original vertex count", icon="INFO")
        layout.label(text="Existing mod folder will be replaced", icon="ERROR")
        row = layout.row()
        active = context.active_object
        row.enabled = bool(
            props.export_mode in {"REPLACEMENT", "FULL_REPLACEMENT"}
            and active is not None and active.type == "MESH" and active.get("enshrouded_guid")
        )
        row.operator("enshrouded.export_replacement", icon="EXPORT")
        layout.prop(props, "show_debug", toggle=True)
        if props.show_debug:
            layout.label(text=f"Resource index: {props.resource_index}")
            layout.label(text=f"Content index: {props.content_index}")


_classes = (
    ENSHROUDED_UL_render_models,
    ENSHROUDED_UL_templates,
    ENSHROUDED_UL_components,
    ENSHROUDED_PT_models,
    ENSHROUDED_PT_import,
    ENSHROUDED_PT_components,
    ENSHROUDED_PT_colliders,
    ENSHROUDED_PT_materials,
    ENSHROUDED_PT_export,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
