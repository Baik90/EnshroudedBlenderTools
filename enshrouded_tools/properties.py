import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
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


class ENSHROUDED_EquipmentBaseItem(PropertyGroup):
    name: StringProperty(name="Equipment Base")
    item_guid: StringProperty(name="Item GUID")
    model_name: StringProperty(name="RenderModel")
    model_guid: StringProperty(name="RenderModel GUID")
    equipment_slot: IntProperty(name="Equipment Slot", default=0)
    model_field: StringProperty(name="Model Field")


class ENSHROUDED_CraftingChoice(PropertyGroup):
    name: StringProperty()
    guid: StringProperty()


class ENSHROUDED_Ingredient(PropertyGroup):
    item: StringProperty(name="Ingredient")
    count: IntProperty(name="Count", default=1, min=1)


class ENSHROUDED_SoundEventItem(PropertyGroup):
    name: StringProperty(name="Event Name", default="Idle Sound")
    event_type: EnumProperty(name="Event Type", items=(
        ('IDLE', 'Idle', 'Audio attached to the equipped visual entity'),
        ('ATTACK_TEST_A', 'Attack', 'Sword swing sound across supported light combo attacks'),
        ('HIT_ENEMY', 'Hit (Experimental)', 'Tested sword base only: light and heavy hits; enemy-only filtering is not guaranteed'),
    ), default='IDLE')
    audio_donor: StringProperty(name="Audio Template")
    audio_source: EnumProperty(name="Source", items=(('VANILLA', 'Vanilla', 'Existing game audio template'), ('WAV', 'WAV File', 'PCM16, mono/stereo, exactly 48000 Hz')), default='VANILLA')
    audio_file: StringProperty(name="Sound WAV", subtype='FILE_PATH')
    audio_volume: FloatProperty(name="Volume", default=0.5, min=0.0, max=1.0)


class ENSHROUDED_SceneProperties(PropertyGroup):
    crafting_items: CollectionProperty(type=ENSHROUDED_CraftingChoice)
    crafting_recipes: CollectionProperty(type=ENSHROUDED_CraftingChoice)
    crafting_recipe: StringProperty(name="Workshop / Recipe Template")
    crafting_ingredients: CollectionProperty(type=ENSHROUDED_Ingredient)
    crafting_output: IntProperty(name="Output Count", default=1, min=1)
    custom_recipe: BoolProperty(name="Custom Recipe", default=False)
    custom_audio_enabled: BoolProperty(name="Enable Custom Audio", default=False)
    sound_events: CollectionProperty(type=ENSHROUDED_SoundEventItem)
    sound_event_index: IntProperty(default=-1)
    idle_audio_donors: CollectionProperty(type=ENSHROUDED_CraftingChoice)
    equipment_level_mode: EnumProperty(name="Equipment Level", default='INHERIT', items=(
        ('INHERIT', 'Inherit Base', 'Keep the original item level range'),
        ('FIXED', 'Fixed Level', 'Set minimum and maximum to the same level'),
        ('RANGE', 'Level Range', 'Set the permitted item level range')))
    equipment_level: IntProperty(name="Level", default=25, min=1, max=105)
    equipment_min_level: IntProperty(name="Minimum Level", default=1, min=1, max=105)
    equipment_max_level: IntProperty(name="Maximum Level", default=25, min=1, max=105)
    export_scope: EnumProperty(
        name="Export Source", items=[("OBJECT", "Active Object", "Export the active mesh"),
        ("COLLECTION", "Collection", "Export meshes recursively, including modifiers")],
        default="OBJECT",
    )
    export_collection: PointerProperty(name="Collection", type=bpy.types.Collection)
    export_effects: BoolProperty(
        name="Export Effect Anchors",
        description="Apply moved VFX and audio helper transforms to the cloned template",
        default=True,
    )

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

    def _equipment_filter_changed(self, context):
        query = self.equipment_filter.strip().casefold()
        if not self.equipment_bases:
            self.equipment_index = -1
            return
        self.equipment_index = next((
            index for index, item in enumerate(self.equipment_bases)
            if not query or query in item.name.casefold()
            or query in item.item_guid.casefold()
            or query in item.model_name.casefold()
            or query in item.model_guid.casefold()
        ), -1)

    def _equipment_changed(self, context):
        if 0 <= self.equipment_index < len(self.equipment_bases):
            item = self.equipment_bases[self.equipment_index]
            self.base_item_guid = item.item_guid
            self.base_template_guid = ""
            self.export_target_guid = item.model_guid
            self.resolved_name = item.model_name
            self.resolved_guid = item.model_guid
            self.resource_index = -1

    def _workspace_changed(self, context):
        self.export_mode = (
            "NEW_MODEL" if self.ui_tab in {"NEW_RECIPE", "EQUIPMENT"} else self.replacement_mode
        )
        if self.ui_tab == "NEW_RECIPE":
            self.base_asset_type = "PLACEABLE"
            self._placeable_changed(context)
        elif self.ui_tab == "EQUIPMENT":
            self.base_asset_type = "EQUIPMENT"
            self._equipment_changed(context)

    def _replacement_mode_changed(self, context):
        if self.ui_tab == "REPLACEMENT":
            self.export_mode = self.replacement_mode

    ui_tab: EnumProperty(
        name="Workspace",
        items=(
            ("MODELS", "Browser", "Browse and import RenderModels", "FILEBROWSER", 0),
            (
                "COMPONENTS",
                "Components",
                "Components, colliders and materials",
                "TOOL_SETTINGS",
                1,
            ),
            (
                "REPLACEMENT",
                "Model Replacement",
                "Export a RenderModel replacement",
                "CON_ROTLIKE",
                2,
            ),
            (
                "NEW_RECIPE",
                "Placeables",
                "Create a new model, item and recipe",
                "IMPORT",
                3,
            ),
            ("EQUIPMENT", "Equipment", "Create equipment and recipes", "MOD_CLOTH", 4),
            ("MOD_BUILDER", "Mod Builder", "Manage exports in one mod", "FILE_FOLDER", 5),
        ),
        default="MODELS",
        update=_workspace_changed,
    )

    builder_directory: StringProperty(name="Project Directory", subtype='DIR_PATH')
    builder_project: StringProperty(name="Project File", subtype='FILE_PATH', update=lambda s, c: setattr(s, 'builder_summary', ''))
    builder_summary: StringProperty(options={'HIDDEN'})
    builder_output: StringProperty(name="Build Directory", subtype='DIR_PATH')
    builder_update_id: StringProperty(options={'HIDDEN'})
    builder_mods: StringProperty(default='[]', options={'HIDDEN', 'SKIP_SAVE'})
    builder_expanded: StringProperty(default='[]', options={'HIDDEN'})

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
    import_weights: BoolProperty(name="Import Vertex Weights", default=True,
        description="Experimental skinning groups named by joint index and hash; no armature")
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
    replacement_mode: EnumProperty(
        name="Replacement Type",
        items=(
            ("REPLACEMENT", "Topology Preserving", "Keep the original vertex count"),
            (
                "FULL_REPLACEMENT",
                "Full Topology (Experimental)",
                "Regenerate a static vertex/index stream with arbitrary topology",
            ),
        ),
        default="REPLACEMENT",
        update=_replacement_mode_changed,
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
    base_asset_type: EnumProperty(
        name="Base Type",
        items=(("PLACEABLE", "Placeable", "Items with a placed entity template"),
               ("EQUIPMENT", "Equipment", "Equipment with a direct static RenderModel")),
        default="PLACEABLE",
    )
    equipment_filter: StringProperty(
        name="Search Equipment Base", default="", update=_equipment_filter_changed,
    )
    base_template_guid: StringProperty(name="Base Template GUID", default="")
    base_item_guid: StringProperty(name="Base Item GUID", default="")
    item_name: StringProperty(
        name="Item Name",
        description="Displayed name of the new item and recipe",
        default="Custom Item",
    )
    item_description: StringProperty(
        name="Description",
        description="Displayed inventory description of the new item",
        default="Custom item created with Enshrouded Blender Tools.",
    )
    item_icon_path: StringProperty(
        name="Item Icon",
        description="Optional 512x512 RGBA PNG used for the new recipe and inventory item",
        subtype="FILE_PATH",
        default="",
    )

    models: CollectionProperty(type=ENSHROUDED_RenderModelItem)
    model_index: IntProperty(default=-1, update=_selection_changed)
    templates: CollectionProperty(type=ENSHROUDED_TemplateItem)
    template_index: IntProperty(default=-1, update=_template_changed)
    template_guid: StringProperty(name="Template GUID", default="")
    component_index: IntProperty(default=-1)
    placeable_bases: CollectionProperty(type=ENSHROUDED_PlaceableBaseItem)
    placeable_index: IntProperty(default=-1, update=_placeable_changed)
    equipment_bases: CollectionProperty(type=ENSHROUDED_EquipmentBaseItem)
    equipment_index: IntProperty(default=-1, update=_equipment_changed)

_classes = (
    ENSHROUDED_RenderModelItem,
    ENSHROUDED_ComponentItem,
    ENSHROUDED_TemplateItem,
    ENSHROUDED_PlaceableBaseItem,
    ENSHROUDED_EquipmentBaseItem,
    ENSHROUDED_CraftingChoice,
    ENSHROUDED_Ingredient,
    ENSHROUDED_SoundEventItem,
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
