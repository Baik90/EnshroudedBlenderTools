"""Simple placeable authoring UI and transform collection."""
import uuid
import bpy
from bpy.props import StringProperty
from bpy.types import Operator, UIList
from .core.object_functions import BASE_TEMPLATE, BASE_ITEM, BASE_MODEL


def simple(p):
    return p.ui_tab == 'NEW_RECIPE' and p.placeable_workflow == 'SIMPLE'


def source(context, p):
    return p.export_collection if p.export_scope == 'COLLECTION' else context.active_object


def prepare(context, p):
    owner = source(context, p)
    if owner is None:
        raise ValueError('Choose the object or collection to export')
    identity = owner.get('enshrouded_object_guid') or str(uuid.uuid4())
    uuid.UUID(identity)
    owner['enshrouded_object_guid'] = identity
    p.object_guid = identity
    p.base_asset_type = 'PLACEABLE'
    p.base_template_guid, p.base_item_guid = BASE_TEMPLATE, BASE_ITEM
    p.export_target_guid = BASE_MODEL


def profile(context, p, transform):
    functions = []
    for function in p.object_functions:
        if function.kind == 'DESTRUCTIBLE':
            from .operators import _archive_paths
            from .core.kfc3_reader import KFC3Reader
            from .core.object_functions import damage_feedback_donor
            if not any(f.kind == 'COLLIDER' for f in p.object_functions):
                raise ValueError('Add Collider before exporting a Destructible function')
            with KFC3Reader(*_archive_paths(context)) as reader:
                donor = damage_feedback_donor(reader, function.damage_material)
            functions.append(dict(kind='DESTRUCTIBLE', max_health=function.max_health,
                material=function.damage_material, donor_template=donor,
                destruction_effects=function.destruction_effects))
            continue
        if function.kind == 'COLLIDER':
            from .operators import _collider_patch_from_object, _collection_contains_object
            obj = function.collider
            if obj is None or obj.type != 'MESH' or obj.get('enshrouded_collider_shape') != 'BOX':
                raise ValueError('Create or select a box collider for ' + function.name)
            if p.export_scope == 'COLLECTION' and not _collection_contains_object(p.export_collection, obj):
                raise ValueError('Collider must belong to the export collection')
            patch = _collider_patch_from_object(obj, transform.inverted())
            functions.append(dict(kind='COLLIDER', position=list(patch.offset),
                                  rotation=list(patch.orientation), dimensions=list(patch.dimensions)))
            continue
        if function.anchor is None or function.anchor.type != 'EMPTY':
            raise ValueError('Create or select a position Empty for ' + function.name)
        matrix = transform @ function.anchor.matrix_world @ transform.inverted()
        position, rotation, scale = matrix.decompose()
        if any(abs(v - 1) > 0.0001 for v in scale):
            raise ValueError('Function Empty scale must be 1')
        record = dict(kind=function.kind, position=list(position),
                      rotation=[rotation.x, rotation.y, rotation.z, rotation.w])
        if function.kind == 'FX':
            effect = p.available_vfx.get(function.effect)
            if effect is None:
                raise ValueError('Load available FX and select an effect')
            record['guid'] = effect.guid
        functions.append(record)
    return dict(guid=p.object_guid, functions=functions)


class ENSHROUDED_UL_object_functions(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.prop(item, 'name', text='', emboss=False)
        row.label(text={'SEAT': 'Chair / Seat', 'FX': 'FX', 'COLLIDER': 'Collider',
                        'DESTRUCTIBLE': 'Destructible'}[item.kind])


class ENSHROUDED_OT_object_function(Operator):
    bl_idname = 'enshrouded.object_function'
    bl_label = 'Object Function'
    action: StringProperty()

    def execute(self, context):
        p = context.scene.enshrouded
        try:
            if self.action == 'LOAD_FX':
                from .operators import _archive_paths, _prefs
                from .core.kfc3_reader import KFC3Reader
                from .core.object_functions import list_vfx
                if not _prefs(context).game_path.strip():
                    raise ValueError('Set Enshrouded Game Path in Edit > Preferences > Add-ons > Enshrouded Blender Tools')
                kfc, resources = _archive_paths(context)
                if not kfc.is_file() or not resources.is_file():
                    raise ValueError('Game archives not found at ' + str(kfc.parent.resolve()) +
                                     '; select the Enshrouded installation folder in Add-on Preferences')
                with KFC3Reader(kfc, resources) as reader:
                    entries = list_vfx(reader)
                p.available_vfx.clear()
                for name, guid in entries:
                    row = p.available_vfx.add()
                    row.name, row.guid = name + ' [' + guid[:8] + ']', guid
            elif self.action in {'SEAT', 'FX', 'COLLIDER', 'DESTRUCTIBLE'}:
                if self.action != 'COLLIDER' and any(f.kind == self.action for f in p.object_functions):
                    raise ValueError('Only one function of each type is currently supported')
                collider = None
                if self.action == 'COLLIDER':
                    from .operators import _create_collider_object, _source_to_blender_matrix
                    from .core.collision import Collider
                    collection = p.export_collection if p.export_scope == 'COLLECTION' else context.collection
                    if collection is None:
                        raise ValueError('Choose an export collection first')
                    collider = _create_collider_object(
                        Collider('BOX', (0,0,0), (0,0,0,1), (.5,.5,.5), 'Decoration', BASE_TEMPLATE),
                        collection, _source_to_blender_matrix(), len(p.object_functions))
                    collider.hide_render = True
                row = p.object_functions.add()
                row.kind = self.action
                row.name = {'SEAT': 'Seat', 'FX': 'Visual Effect', 'COLLIDER': 'Collider',
                            'DESTRUCTIBLE': 'Destructible'}[self.action]
                row.collider = collider
                p.object_function_index = len(p.object_functions) - 1
            elif self.action == 'REMOVE':
                if 0 <= p.object_function_index < len(p.object_functions):
                    p.object_functions.remove(p.object_function_index)
                    p.object_function_index = min(p.object_function_index, len(p.object_functions) - 1)
            elif self.action == 'ANCHOR':
                row = p.object_functions[p.object_function_index]
                if row.anchor is None:
                    obj = bpy.data.objects.new('EBT_' + row.name, None)
                    collection = p.export_collection if p.export_scope == 'COLLECTION' else context.collection
                    if collection is None:
                        raise ValueError('Choose an export collection first')
                    collection.objects.link(obj)
                    obj.empty_display_type = 'ARROWS'
                    obj.empty_display_size = 0.2
                    row.anchor = obj
                    self.report({'INFO'}, 'Position and rotate the Empty; scale must stay 1')
            elif self.action == 'IDENTITY':
                prepare(context, p)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def draw(layout, context, p):
    layout.label(text='New Decoration')
    layout.label(text='Experimental: seat / FX require in-game verification', icon='INFO')
    owner = source(context, p)
    identity = owner.get('enshrouded_object_guid', '') if owner else ''
    layout.label(text='GUID: ' + (identity or 'Assigned automatically on export'))
    row = layout.row(align=True)
    for kind, label in (('SEAT', 'Add Chair Function'), ('FX', 'Add FX Function'), ('COLLIDER', 'Add Collider')):
        row.operator('enshrouded.object_function', text=label, icon='ADD').action = kind
    layout.operator('enshrouded.object_function', text='Add Destructible', icon='ADD').action = 'DESTRUCTIBLE'
    layout.template_list('ENSHROUDED_UL_object_functions', '', p, 'object_functions', p, 'object_function_index', rows=3)
    if 0 <= p.object_function_index < len(p.object_functions):
        function = p.object_functions[p.object_function_index]
        box = layout.box()
        row = box.row()
        row.prop(function, 'name')
        row.operator('enshrouded.object_function', text='', icon='X').action = 'REMOVE'
        if function.kind == 'DESTRUCTIBLE':
            box.prop(function, 'max_health')
            box.prop(function, 'damage_material')
            box.prop(function, 'destruction_effects')
            box.label(text='Gameplay material does not change Blender textures', icon='INFO')
            if not any(f.kind == 'COLLIDER' for f in p.object_functions):
                box.label(text='Requires a Collider function', icon='ERROR')
            return
        if function.kind == 'COLLIDER':
            box.prop(function, 'collider')
            box.label(text='Box: move, rotate and scale in Object Mode', icon='INFO')
            box.label(text='Do not apply scale or edit the helper mesh')
            return
        box.prop(function, 'anchor')
        box.operator('enshrouded.object_function', text='Create Position Empty', icon='EMPTY_ARROWS').action = 'ANCHOR'
        if function.kind == 'FX':
            from .operators import _prefs
            if not _prefs(context).game_path.strip():
                box.label(text='Set Game Path in Add-on Preferences first', icon='ERROR')
            box.operator('enshrouded.object_function', text='Load Available FX').action = 'LOAD_FX'
            box.prop_search(function, 'effect', p, 'available_vfx')
        else:
            box.label(text='Experimental: seat position/orientation from Empty', icon='INFO')
            if not any(f.kind == 'COLLIDER' for f in p.object_functions):
                box.label(text='Add Collider for interaction targeting', icon='INFO')
    layout.label(text='No functions: decoration only; no physical collision')


def register():
    bpy.utils.register_class(ENSHROUDED_UL_object_functions)
    bpy.utils.register_class(ENSHROUDED_OT_object_function)


def unregister():
    bpy.utils.unregister_class(ENSHROUDED_OT_object_function)
    bpy.utils.unregister_class(ENSHROUDED_UL_object_functions)
