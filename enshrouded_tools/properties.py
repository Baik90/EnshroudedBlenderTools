import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


class ENSHROUDED_RenderModelItem(PropertyGroup):
    name: StringProperty(name="Name")
    guid: StringProperty(name="GUID")
    resource_index: IntProperty(name="Resource Index", default=-1)


class ENSHROUDED_SceneProperties(PropertyGroup):
    def _selection_changed(self, context):
        if 0 <= self.model_index < len(self.models):
            item = self.models[self.model_index]
            self.resolved_name = item.name
            self.resolved_guid = item.guid
            self.resource_index = item.resource_index
            self.content_index = -1
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
    show_debug: BoolProperty(name="Debug", default=False)

    models: CollectionProperty(type=ENSHROUDED_RenderModelItem)
    model_index: IntProperty(default=-1, update=_selection_changed)

_classes = (ENSHROUDED_RenderModelItem, ENSHROUDED_SceneProperties)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.enshrouded = PointerProperty(type=ENSHROUDED_SceneProperties)

def unregister():
    del bpy.types.Scene.enshrouded
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
