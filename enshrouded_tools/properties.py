import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


class ENSHROUDED_RenderModelItem(PropertyGroup):
    name: StringProperty(name="Name")
    guid: StringProperty(name="GUID")
    resource_index: IntProperty(name="Resource Index", default=-1)


class ENSHROUDED_ComponentItem(PropertyGroup):
    name: StringProperty(name="Component")
    type_hash: StringProperty(name="Type Hash")
    data_size: IntProperty(name="Data Size", default=0)
    supported: BoolProperty(name="Supported", default=False)


class ENSHROUDED_TemplateItem(PropertyGroup):
    name: StringProperty(name="Template")
    guid: StringProperty(name="GUID")
    resource_index: IntProperty(name="Resource Index", default=-1)
    collider_count: IntProperty(name="Colliders", default=0)
    components: CollectionProperty(type=ENSHROUDED_ComponentItem)


class ENSHROUDED_PlaceableBaseItem(PropertyGroup):
    name: StringProperty(name="Placeable Base")
    template_guid: StringProperty(name="Template GUID")
    item_guid: StringProperty(name="Item GUID")


class ENSHROUDED_SceneProperties(PropertyGroup):
    def _selection_changed(self, context):
        self.templates.clear()
        self.template_index = -1
        self.template_guid = ""
        self.component_index = -1
        if 0 <= self.model_index < len(self.models):
            item = self.models[self.model_index]
            self.resolved_name = item.name
            self.resolved_guid = item.guid
            self.resource_index = item.resource_index
            self.content_index = -1
            self.export_target_guid = item.guid
        else:
            self.resolved_name = ""
            self.resolved_guid = ""
            self.resource_index = -1
            self.content_index = -1

    def _filter_changed(self, context):
        query = self.model_filter.strip().casefold()
        if not self.models:
            self.model_index = -1
            return
        if not query:
            self.model_index = 0
            return
        self.model_index = next(
            (
                index for index, item in enumerate(self.models)
                if query in item.name.casefold() or query in item.guid.casefold()
            ),
            -1,
        )

    def _template_changed(self, context):
        self.component_index = -1
        if 0 <= self.template_index < len(self.templates):
            self.template_guid = self.templates[self.template_index].guid
        else:
            self.template_guid = ""

    def _placeable_filter_changed(self, context):
        query = self.placeable_filter.strip().casefold()
        if not self.placeable_bases:
            self.placeable_index = -1
            return
        self.placeable_index = next(
            (
                index for index, item in enumerate(self.placeable_bases)
                if not query
                or query in item.name.casefold()
                or query in item.template_guid.casefold()
                or query in item.item_guid.casefold()
            ),
            -1,
        )

    def _placeable_changed(self, context):
        if 0 <= self.placeable_index < len(self.placeable_bases):
            item = self.placeable_bases[self.placeable_index]
            self.base_template_guid = item.template_guid
            self.base_item_guid = item.item_guid
        else:
            self.base_template_guid = ""
            self.base_item_guid = ""

    ui_tab: EnumProperty(
        name="Workspace",
        items=(
            ("MODELS", "Models", "Browse and import RenderModels", "MESH_DATA", 0),
            (
                "COMPONENTS",
                "Components",
                "Components, colliders and materials",
                "MODIFIER",
                1,
            ),
            ("EXPORT", "Export", "Replacement mod export", "EXPORT", 2),
        ),
        default="MODELS",
    )

    model_query: StringProperty(
        name="Model / GUID",
        description="Debug name or RenderModel GUID",
        default="global_props_roughwood_table_01_a_broken",
    )
    model_filter: StringProperty(
        name="Search",
        description="Filter RenderModels by name or GUID",
        default="",
        update=_filter_changed,
    )
    resolved_name: StringProperty(name="Resolved Name", default="")
    resolved_guid: StringProperty(name="Resolved GUID", default="")
    resource_index: IntProperty(name="Resource Index", default=-1)
    content_index: IntProperty(name="Content Index", default=-1)
    lod: IntProperty(name="LOD", default=0, min=0)
    import_uvs: BoolProperty(name="Import UVs", default=True)
    import_materials: BoolProperty(name="Import Materials", default=True)
    import_textures: BoolProperty(name="Import Textures", default=True)
    import_all_lods: BoolProperty(name="Import All LODs", default=False)
    import_colliders: BoolProperty(
        name="Import Colliders",
        description="Import gameplay collider primitives from referencing entity templates",
        default=False,
    )
    show_debug: BoolProperty(name="Debug", default=False)

    export_mode: EnumProperty(
        name="Export Type",
        items=(
            ("REPLACEMENT", "Model Replacement", "Replace the selected object's source RenderModel"),
            (
                "FULL_REPLACEMENT",
                "Full Topology Replacement (Experimental)",
                "Regenerate a single static vertex/index stream with arbitrary topology",
            ),
            (
                "NEW_MODEL",
                "New Model + Recipe (Experimental)",
                "Clone a selected base template, item and recipe with a new RenderModel",
            ),
        ),
        default="REPLACEMENT",
    )
    mod_id: StringProperty(
        name="Mod ID",
        description="Folder and identifier below the game's Mods directory",
        default="model_replacement",
    )
    mod_name: StringProperty(name="Mod Name", default="Model Replacement")
    mod_version: StringProperty(name="Version", default="0.1.0")
    mod_author: StringProperty(name="Author", default="Unknown")
    export_target_guid: StringProperty(
        name="Target GUID",
        description="GUID of the keen::RenderModel that the generated mod replaces",
        default="",
    )
    export_directory: StringProperty(
        name="Export Folder",
        description="Folder that receives the generated mod directory; empty uses <Game Path>/mods",
        subtype="DIR_PATH",
        default="",
    )
    export_colliders: BoolProperty(
        name="Export Colliders",
        description="Patch imported gameplay colliders in their original entity templates",
        default=True,
    )
    export_textures: BoolProperty(
        name="Export Custom Textures",
        description="Compress external replacement images and patch existing material slots",
        default=False,
    )
    placeable_filter: StringProperty(
        name="Search Placeable Base",
        default="",
        update=_placeable_filter_changed,
    )
    base_template_guid: StringProperty(name="Base Template GUID", default="")
    base_item_guid: StringProperty(name="Base Item GUID", default="")

    models: CollectionProperty(type=ENSHROUDED_RenderModelItem)
    model_index: IntProperty(default=-1, update=_selection_changed)
    templates: CollectionProperty(type=ENSHROUDED_TemplateItem)
    template_index: IntProperty(default=-1, update=_template_changed)
    template_guid: StringProperty(name="Template GUID", default="")
    component_index: IntProperty(default=-1)
    placeable_bases: CollectionProperty(type=ENSHROUDED_PlaceableBaseItem)
    placeable_index: IntProperty(default=-1, update=_placeable_changed)

_classes = (
    ENSHROUDED_RenderModelItem,
    ENSHROUDED_ComponentItem,
    ENSHROUDED_TemplateItem,
    ENSHROUDED_PlaceableBaseItem,
    ENSHROUDED_SceneProperties,
)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.enshrouded = PointerProperty(type=ENSHROUDED_SceneProperties)

def unregister():
    del bpy.types.Scene.enshrouded
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
