bl_info = {
    "name": "Enshrouded Tools",
    "author": "Andreas / reverse-engineering project",
    "version": (0, 29, 11),
    "blender": (5, 2, 0),
    "location": "3D View > Sidebar > Enshrouded",
    "description": "Inspect/import Enshrouded KFC3/KFC4 keen::RenderModel resources",
    "category": "Import-Export",
}

from . import preferences, properties, operators, ui, mod_builder, object_authoring

_modules = (preferences, properties, operators, mod_builder, object_authoring, ui)

def register():
    for module in _modules:
        module.register()

def unregister():
    for module in reversed(_modules):
        module.unregister()
