from pathlib import Path
import bpy
from bpy.props import StringProperty
from bpy.types import AddonPreferences

class ENSHROUDED_AddonPreferences(AddonPreferences):
    bl_idname = __package__

    game_path: StringProperty(
        name="Enshrouded Game Path",
        subtype="DIR_PATH",
        description="Folder containing enshrouded.kfc, enshrouded.kfc_resources and enshrouded_XXX.dat",
        default="",
    )
    texconv_path: StringProperty(
        name="Texconv Executable",
        subtype="FILE_PATH",
        description="Path to Microsoft's texconv.exe for BC texture compression",
        default="",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "game_path")
        layout.prop(self, "texconv_path")
        game = Path(bpy.path.abspath(self.game_path)) if self.game_path else None
        if game:
            ok = (game / "enshrouded.kfc").is_file() and (game / "enshrouded.kfc_resources").is_file()
            row = layout.row()
            row.label(text="KFC3 files found" if ok else "KFC3 files not found",
                      icon="CHECKMARK" if ok else "ERROR")
        if self.texconv_path:
            texconv = Path(bpy.path.abspath(self.texconv_path))
            layout.label(
                text="Texconv found" if texconv.is_file() else "Texconv not found",
                icon="CHECKMARK" if texconv.is_file() else "ERROR",
            )

_classes = (ENSHROUDED_AddonPreferences,)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
