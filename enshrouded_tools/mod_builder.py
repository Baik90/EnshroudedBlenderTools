import json
from pathlib import Path
import bpy
from bpy.props import StringProperty
from bpy.types import Operator
from .core import mod_project


def refresh(p):
    p.builder_summary = json.dumps(mod_project.load(bpy.path.abspath(p.builder_project)))


def ready(p):
    return bool(p.builder_project and p.builder_summary
                and Path(bpy.path.abspath(p.builder_project)).is_file())


def mods_directory(context):
    addon = context.preferences.addons.get(__package__)
    if addon is None or not addon.preferences.game_path:
        return None
    return Path(bpy.path.abspath(addon.preferences.game_path)).resolve() / 'mods'


def scan_mods(context):
    p = context.scene.enshrouded
    root = mods_directory(context)
    rows = mod_project.scan(root) if root else []
    # Keep explicitly opened projects visible even when stored outside the game.
    if ready(p) and not any(r['project'] == str(Path(bpy.path.abspath(p.builder_project)).resolve()) for r in rows):
        data = mod_project.load(bpy.path.abspath(p.builder_project))
        rows.append(dict(path=str(Path(p.builder_project).parent), name=data['name'],
                         project=p.builder_project, entries=data['entries'], error=''))
    p.builder_mods = json.dumps(rows)


def auto_scan():
    # No disk access in draw/dropdown callbacks. Refresh only while this tab is open.
    try:
        context = bpy.context
        if context.scene and context.scene.enshrouded.ui_tab == 'MOD_BUILDER':
            scan_mods(context)
    except (AttributeError, OSError, ValueError, KeyError):
        pass
    return 3.0


class ENSHROUDED_OT_mod_project(Operator):
    bl_idname = 'enshrouded.mod_project'
    bl_label = 'Mod Project'
    action: StringProperty()
    entry_id: StringProperty()
    project_path: StringProperty()

    def execute(self, context):
        p = context.scene.enshrouded
        try:
            if self.action == 'SCAN':
                scan_mods(context)
                return {'FINISHED'}
            if self.action == 'EXPAND':
                expanded = set(json.loads(p.builder_expanded))
                if self.project_path in expanded:
                    expanded.remove(self.project_path)
                else:
                    expanded.add(self.project_path)
                p.builder_expanded = json.dumps(sorted(expanded))
                return {'FINISHED'}
            if self.action == 'ACTIVATE':
                if p.builder_project == self.project_path:
                    p.builder_project = ''
                    p.builder_update_id = ''
                    return {'FINISHED'}
                mod_project.load(self.project_path)
                p.builder_project = self.project_path
            if self.action == 'ADOPT':
                directory = mods_directory(context)
                source = Path(self.project_path).resolve()
                if directory is None or source.parent != directory.resolve():
                    raise ValueError('Select a mod in the configured game mods folder')
                p.builder_project = str(mod_project.adopt(source))
            elif self.action == 'CREATE':
                directory = mods_directory(context)
                if directory is None:
                    raise ValueError('Set the game path in Add-on Preferences')
                p.builder_project = str(mod_project.create(directory,
                    p.mod_id, p.mod_name, p.mod_version, p.mod_author))
            elif self.action == 'SELECT':
                data = mod_project.load(bpy.path.abspath(p.builder_project))
                entry = next(e for e in data['entries'] if e['id'] == self.entry_id)
                p.builder_update_id = entry['id']
                p.ui_tab = {'PLACEABLE': 'NEW_RECIPE', 'EQUIPMENT': 'EQUIPMENT',
                            'REPLACEMENT': 'REPLACEMENT'}[entry['kind']]
                self.report({'INFO'}, 'Configure the source and export settings, then click Update Mod Entry')
            elif self.action == 'SAVE':
                data = mod_project.load(bpy.path.abspath(p.builder_project))
                data.update(name=p.mod_name, version=p.mod_version, author=p.mod_author)
                mod_project.save(bpy.path.abspath(p.builder_project), data)
            elif self.action in {'TOGGLE', 'REMOVE'}:
                data = mod_project.load(bpy.path.abspath(p.builder_project))
                entry = next(e for e in data['entries'] if e['id'] == self.entry_id)
                if self.action == 'REMOVE':
                    data['entries'].remove(entry)
                else:
                    entry['enabled'] = not entry['enabled']
                mod_project.save(bpy.path.abspath(p.builder_project), data)
            elif self.action == 'BUILD':
                directory = mods_directory(context)
                if directory is None:
                    raise ValueError('Set the game path in Add-on Preferences')
                result = mod_project.build_installed(bpy.path.abspath(p.builder_project), directory,
                    dict(name=p.mod_name, version=p.mod_version, author=p.mod_author))
                self.report({'INFO'}, 'Built mod: ' + str(result))
            refresh(p)
            if self.action in {'OPEN', 'CREATE', 'ACTIVATE', 'ADOPT'}:
                p.builder_update_id = ''
                data = json.loads(p.builder_summary)
                p.mod_id, p.mod_name = data['id'], data['name']
                p.mod_version, p.mod_author = data['version'], data['author']
            scan_mods(context)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'}


def draw(layout, context, p):
    layout.label(text='Mod Builder')
    root = mods_directory(context)
    if root is None:
        layout.label(text='Set the game path in Preferences', icon='ERROR')
    for field in ('mod_id', 'mod_name', 'mod_version', 'mod_author'):
        layout.prop(p, field)
    layout.operator('enshrouded.mod_project', text='Create Mod', icon='ADD').action = 'CREATE'
    row = layout.row()
    row.label(text='Mods / exports')
    row.operator('enshrouded.mod_project', text='', icon='FILE_REFRESH').action = 'SCAN'
    tree = layout.box().column(align=True)
    expanded = set(json.loads(p.builder_expanded))
    for mod in json.loads(p.builder_mods):
        row = tree.row(align=True)
        opened = mod['path'] in expanded
        op = row.operator('enshrouded.mod_project', text='',
                          icon='TRIA_DOWN' if opened else 'TRIA_RIGHT', emboss=False)
        op.action, op.project_path = 'EXPAND', mod['path']
        row.label(text=mod['name'], icon='PACKAGE')
        choose = row.row(align=True)
        choose.enabled = bool(mod['project']) and not mod['error']
        active = bool(mod['project']) and p.builder_project == mod['project']
        op = choose.operator('enshrouded.mod_project', text='',
                             icon='CHECKBOX_HLT' if active else 'CHECKBOX_DEHLT', emboss=False)
        op.action, op.project_path = 'ACTIVATE', mod['project']
        if opened:
            if not mod['project'] or mod['error']:
                if mod.get('adoptable') and not mod['error']:
                    op = tree.operator('enshrouded.mod_project', text='Adopt into Mod Builder', icon='IMPORT')
                    op.action, op.project_path = 'ADOPT', mod['path']
                else:
                    tree.label(text='    Read-only: no valid BlenderTools project', icon='INFO')
            for entry in mod['entries']:
                child = tree.row(align=True)
                child.label(text='    ' + entry['name'], icon='OBJECT_DATA')
                actions = child.row(align=True)
                actions.enabled = active
                for action, icon in (('SELECT', 'FILE_REFRESH'), ('TOGGLE', 'HIDE_OFF' if entry['enabled'] else 'HIDE_ON'), ('REMOVE', 'X')):
                    op = actions.operator('enshrouded.mod_project', text='', icon=icon, emboss=False)
                    op.action, op.entry_id = action, entry['id']
    layout.label(text='Checkmark = single export target', icon='INFO')
    if not ready(p):
        layout.label(text='Create or check a mod to add exports', icon='INFO')
        return
    data = json.loads(p.builder_summary)
    layout.label(text=data['name'] + ' — ' + data['id'])
    layout.operator('enshrouded.mod_project', text='Build Mod', icon='EXPORT').action = 'BUILD'
    layout.label(text='Build writes to the checked mod; close the game first', icon='INFO')


def register():
    bpy.utils.register_class(ENSHROUDED_OT_mod_project)
    bpy.app.timers.register(auto_scan, first_interval=0.5, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(auto_scan):
        bpy.app.timers.unregister(auto_scan)
    bpy.utils.unregister_class(ENSHROUDED_OT_mod_project)
