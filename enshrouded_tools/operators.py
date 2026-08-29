from pathlib import Path
import tempfile
import bpy
from bpy.types import Operator
from bpy_extras.io_utils import axis_conversion
from mathutils import Vector

from .core.kfc3_reader import KFC3Reader
from .core.material import MATERIAL_TYPE_HASH, make_dds, parse_material
from .core.render_model import decode_lod, list_render_models, parse_render_model, resolve_model

def _prefs(context):
    return context.preferences.addons[__package__].preferences


def _archive_paths(context):
    selected_path = Path(bpy.path.abspath(_prefs(context).game_path))
    candidates = (selected_path, *selected_path.parents)
    for game_path in candidates:
        kfc = game_path / "enshrouded.kfc"
        resources = game_path / "enshrouded.kfc_resources"
        executable = game_path / "enshrouded.exe"
        if executable.is_file() and kfc.is_file() and resources.is_file():
            return kfc, resources

    # Keep the error paths rooted at the selected directory. No recursive file
    # search is used, so Mods and other subdirectories can never become sources.
    return selected_path / "enshrouded.kfc", selected_path / "enshrouded.kfc_resources"


def _load_texture_image(reader, texture, material_name):
    if texture.dimension == 2 and texture.depth > 1:
        raise ValueError(
            f"Blender cannot load 3D DDS textures ({texture.width}x{texture.height}x{texture.depth})"
        )
    content_index, payload = reader.read_content(texture.content_hash)
    image_key = f"Enshrouded_{texture.content_hash.hex()}"
    image = bpy.data.images.get(image_key)
    if image is None:
        cache_dir = Path(tempfile.gettempdir()) / "enshrouded_blender_tools"
        cache_dir.mkdir(parents=True, exist_ok=True)
        dds_path = cache_dir / f"{texture.content_hash.hex()}.dds"
        dds_data = make_dds(texture, payload)
        if not dds_path.is_file() or dds_path.stat().st_size != len(dds_data):
            dds_path.write_bytes(dds_data)
        image = bpy.data.images.load(str(dds_path), check_existing=True)
        if not all(image.size):
            bpy.data.images.remove(image)
            raise ValueError("Blender could not decode the DDS texture")
        image.name = image_key
        image.pack()
    image.colorspace_settings.name = "sRGB" if "albedo" in texture.slot_name else "Non-Color"
    image["enshrouded_slot"] = texture.slot_name
    image["enshrouded_content_index"] = content_index
    image["enshrouded_content_hash"] = texture.content_hash.hex()
    image["enshrouded_vk_format"] = texture.vk_format
    return image


def _build_material(reader, reference, import_textures):
    resource_index = reader.find_resource_index(reference.guid, MATERIAL_TYPE_HASH)
    parsed = parse_material(reader.read_resource(resource_index))
    material = bpy.data.materials.new(parsed.debug_name)
    material["enshrouded_guid"] = reference.guid
    material["enshrouded_resource_index"] = resource_index
    material["enshrouded_variant"] = reference.variant
    material.use_nodes = True

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (600, 0)
    principled = nodes.new("ShaderNodeBsdfPrincipled")
    principled.location = (300, 0)
    links.new(principled.outputs["BSDF"], output.inputs["Surface"])

    errors = []
    texture_nodes = {}
    if import_textures:
        for index, texture in enumerate(parsed.textures):
            try:
                image = _load_texture_image(reader, texture, parsed.debug_name)
            except Exception as exc:
                errors.append(f"{texture.slot_name}: {exc}")
                continue
            texture_node = nodes.new("ShaderNodeTexImage")
            texture_node.name = texture.slot_name
            texture_node.label = texture.slot_name
            texture_node.image = image
            texture_node.location = (-500, 220 - index * 260)
            texture_nodes[texture.slot_name] = texture_node

            if "normal" in texture.slot_name:
                normal_map = nodes.new("ShaderNodeNormalMap")
                normal_map.location = (-100, texture_node.location.y)
                links.new(texture_node.outputs["Color"], normal_map.inputs["Color"])
                links.new(normal_map.outputs["Normal"], principled.inputs["Normal"])

        albedo_node = next(
            (node for name, node in texture_nodes.items() if "albedo" in name),
            None,
        )
        material_node = next(
            (node for name, node in texture_nodes.items() if "material" in name),
            None,
        )

        if material_node is not None:
            material_node.label = f"{material_node.name} (R=Metallic, G=Roughness, B=AO)"
            separate = nodes.new("ShaderNodeSeparateColor")
            separate.name = "Separate RMA"
            separate.label = "RMA Channels"
            separate.location = (-100, material_node.location.y)
            links.new(material_node.outputs["Color"], separate.inputs["Color"])
            links.new(separate.outputs["Red"], principled.inputs["Metallic"])
            links.new(separate.outputs["Green"], principled.inputs["Roughness"])

            if albedo_node is not None:
                ao_multiply = nodes.new("ShaderNodeMixRGB")
                ao_multiply.name = "Multiply Ambient Occlusion"
                ao_multiply.label = "Albedo × AO"
                ao_multiply.blend_type = "MULTIPLY"
                ao_multiply.inputs["Fac"].default_value = 1.0
                ao_multiply.location = (40, 180)
                links.new(albedo_node.outputs["Color"], ao_multiply.inputs["Color1"])
                links.new(separate.outputs["Blue"], ao_multiply.inputs["Color2"])
                links.new(ao_multiply.outputs["Color"], principled.inputs["Base Color"])
        elif albedo_node is not None:
            links.new(albedo_node.outputs["Color"], principled.inputs["Base Color"])

        if albedo_node is not None:
            links.new(albedo_node.outputs["Alpha"], principled.inputs["Alpha"])

    return material, errors


class ENSHROUDED_OT_load_model_list(Operator):
    bl_idname = "enshrouded.load_model_list"
    bl_label = "Load RenderModels"
    bl_description = "Read all keen::RenderModel resources from the configured game archives"

    def execute(self, context):
        props = context.scene.enshrouded
        kfc, resources = _archive_paths(context)
        if not kfc.is_file() or not resources.is_file():
            self.report({"ERROR"}, "Set a valid Enshrouded game path in Add-on Preferences")
            return {"CANCELLED"}

        try:
            with KFC3Reader(kfc, resources) as reader:
                models = list_render_models(reader)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not load RenderModels: {exc}")
            return {"CANCELLED"}

        props.models.clear()
        for model in models:
            item = props.models.add()
            item.name = model.name
            item.guid = model.guid
            item.resource_index = model.resource_index

        props.model_index = 0 if models else -1
        self.report({"INFO"}, f"Loaded {len(models)} RenderModels")
        return {"FINISHED"}

class ENSHROUDED_OT_resolve_model(Operator):
    bl_idname = "enshrouded.resolve_model"
    bl_label = "Resolve"
    bl_description = "Resolve a RenderModel debug name or GUID"

    def execute(self, context):
        props = context.scene.enshrouded
        kfc, resources = _archive_paths(context)

        if not kfc.is_file() or not resources.is_file():
            self.report({"ERROR"}, "Set a valid Enshrouded game path in Add-on Preferences")
            return {"CANCELLED"}

        try:
            with KFC3Reader(kfc, resources) as reader:
                result = resolve_model(reader, props.model_query)
        except Exception as exc:
            self.report({"ERROR"}, f"KFC3 error: {exc}")
            return {"CANCELLED"}

        if result is None:
            self.report({"WARNING"}, "RenderModel not found (generic name resolver is still TODO)")
            return {"CANCELLED"}

        props.resolved_name = result.name
        props.resolved_guid = result.guid
        props.resource_index = result.resource_index
        props.content_index = result.content_index
        return {"FINISHED"}

class ENSHROUDED_OT_import_model(Operator):
    bl_idname = "enshrouded.import_model"
    bl_label = "Import Model"
    bl_description = "Import the resolved keen::RenderModel into Blender"

    def execute(self, context):
        props = context.scene.enshrouded
        if not props.resolved_guid:
            self.report({"ERROR"}, "Resolve a RenderModel first")
            return {"CANCELLED"}

        kfc, resources = _archive_paths(context)
        if not kfc.is_file() or not resources.is_file():
            self.report({"ERROR"}, "Set a valid Enshrouded game path in Add-on Preferences")
            return {"CANCELLED"}

        try:
            with KFC3Reader(kfc, resources) as reader:
                descriptor = reader.read_resource(props.resource_index)
                model = parse_render_model(descriptor)
                content_index, render_data = reader.read_content(model.render_data_hash)
                blender_materials = []
                if props.import_materials:
                    for reference in model.materials:
                        try:
                            material, texture_errors = _build_material(
                                reader,
                                reference,
                                props.import_textures,
                            )
                            blender_materials.append(material)
                            for error in texture_errors:
                                self.report({"WARNING"}, f"Texture skipped: {error}")
                        except Exception as exc:
                            placeholder = bpy.data.materials.new(
                                f"Enshrouded Material {reference.guid}"
                            )
                            placeholder["enshrouded_guid"] = reference.guid
                            placeholder["enshrouded_import_error"] = str(exc)
                            blender_materials.append(placeholder)
                            self.report({"WARNING"}, f"Material fallback: {exc}")

            lod_indices = range(len(model.lods)) if props.import_all_lods else (props.lod,)
            source_to_blender = axis_conversion(
                from_forward="-Z",
                from_up="Y",
            ).to_4x4()
            direction_to_blender = source_to_blender.to_3x3()
            imported = []
            for lod_index in lod_indices:
                decoded = decode_lod(model, render_data, lod_index)
                mesh = bpy.data.meshes.new(f"{model.debug_name}_LOD{lod_index}")
                mesh.from_pydata(decoded.vertices, [], decoded.triangles)
                mesh.transform(source_to_blender)
                mesh.update()

                for material in blender_materials:
                    mesh.materials.append(material)
                for polygon, material_index in zip(mesh.polygons, decoded.triangle_materials):
                    if 0 <= material_index < len(blender_materials):
                        polygon.material_index = material_index

                transformed_normals = [
                    tuple((direction_to_blender @ Vector(normal)).normalized())
                    for normal in decoded.normals
                ]
                transformed_tangents = [
                    tuple((direction_to_blender @ Vector(tangent)).normalized())
                    for tangent in decoded.tangents
                ]
                mesh.normals_split_custom_set_from_vertices(transformed_normals)

                tangent_attribute = mesh.attributes.new(
                    name="enshrouded_tangent",
                    type="FLOAT_VECTOR",
                    domain="POINT",
                )
                sign_attribute = mesh.attributes.new(
                    name="enshrouded_bitangent_sign",
                    type="FLOAT",
                    domain="POINT",
                )
                for index, tangent in enumerate(transformed_tangents):
                    tangent_attribute.data[index].vector = tangent
                    sign_attribute.data[index].value = decoded.bitangent_signs[index]

                if props.import_uvs and decoded.uvs:
                    uv_layer = mesh.uv_layers.new(name="UVMap")
                    for loop in mesh.loops:
                        uv_layer.data[loop.index].uv = decoded.uvs[loop.vertex_index]

                obj = bpy.data.objects.new(mesh.name, mesh)
                context.collection.objects.link(obj)
                obj["enshrouded_guid"] = props.resolved_guid
                obj["enshrouded_model_name"] = model.debug_name
                obj["enshrouded_resource_index"] = props.resource_index
                obj["enshrouded_content_index"] = content_index
                obj["enshrouded_lod"] = lod_index
                obj["enshrouded_forward_axis"] = "-Z"
                obj["enshrouded_up_axis"] = "+Y"
                obj["enshrouded_vertex_frame_format"] = "A2B10G10R10_SNORM"
                imported.append(obj)

            for selected in context.selected_objects:
                selected.select_set(False)
            for obj in imported:
                obj.select_set(True)
            if imported:
                context.view_layer.objects.active = imported[0]
            props.content_index = content_index
        except Exception as exc:
            self.report({"ERROR"}, f"Import failed: {exc}")
            return {"CANCELLED"}

        triangle_count = sum(len(obj.data.polygons) for obj in imported)
        self.report(
            {"INFO"},
            f"Imported {len(imported)} object(s), {triangle_count} triangles from content {content_index}"
        )
        return {"FINISHED"}

_classes = (
    ENSHROUDED_OT_load_model_list,
    ENSHROUDED_OT_resolve_model,
    ENSHROUDED_OT_import_model,
)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
