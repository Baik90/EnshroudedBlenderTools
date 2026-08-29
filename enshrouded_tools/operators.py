from pathlib import Path
import re
import tempfile
import bpy
import bmesh
from bpy.types import Operator
from bpy_extras.io_utils import axis_conversion
from mathutils import Matrix, Quaternion, Vector

from .core.collision import find_model_colliders
from .core.kfc3_reader import KFC3Reader
from .core.material import MATERIAL_TYPE_HASH, make_dds, parse_material
from .core.replacement_export import (
    build_full_topology_payload,
    build_replacement_payload,
    write_replacement_mod,
)
from .core.render_model import (
    decode_lod,
    list_render_models,
    looks_like_guid,
    parse_render_model,
    resolve_model,
)

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


def _default_export_directory(kfc_path):
    return Path(kfc_path).parent / "mods"


def _export_directory(props, kfc_path):
    if props.export_directory.strip():
        return Path(bpy.path.abspath(props.export_directory)).resolve()
    return _default_export_directory(kfc_path).resolve()


def _fallback_tangent(normal):
    axis = Vector((1.0, 0.0, 0.0)) if abs(normal.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    return normal.cross(axis).normalized()


def _source_to_blender_matrix():
    """Convert Enshrouded's left-handed -Z/+Y space to Blender space."""
    axis_rotation = axis_conversion(from_forward="-Z", from_up="Y").to_4x4()
    handedness = Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0))
    return axis_rotation @ handedness


def _transform_new_geometry(bm, before, matrix):
    geometry = [element for element in bm.verts if element not in before]
    bmesh.ops.transform(bm, matrix=matrix, verts=geometry)


def _add_uv_sphere(bm, radius, center_y=0.0):
    before = set(bm.verts)
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=12, radius=radius)
    _transform_new_geometry(bm, before, Matrix.Translation((0.0, center_y, 0.0)))


def _add_y_cone(bm, radius_bottom, radius_top, depth):
    if depth <= 0.0:
        return
    before = set(bm.verts)
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=20,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=depth,
    )
    rotate_to_y = Matrix.Rotation(-1.5707963267948966, 4, "X")
    _transform_new_geometry(bm, before, rotate_to_y)


def _create_collider_object(collider, collection, source_to_blender, index):
    bm = bmesh.new()
    try:
        dimensions = collider.dimensions
        if collider.shape == "BOX":
            bmesh.ops.create_cube(bm, size=2.0)
            bmesh.ops.scale(bm, vec=Vector(dimensions), verts=bm.verts)
        elif collider.shape == "SPHERE":
            _add_uv_sphere(bm, dimensions[0])
        elif collider.shape == "SPHEROID":
            _add_uv_sphere(bm, 1.0)
            bmesh.ops.scale(
                bm,
                vec=Vector((dimensions[0], dimensions[1], dimensions[0])),
                verts=bm.verts,
            )
        elif collider.shape in {"CYLINDER", "CAPSULE", "TAPERED_CAPSULE"}:
            if collider.shape == "TAPERED_CAPSULE":
                radius_bottom, radius_top, length = dimensions
            else:
                radius_bottom = radius_top = dimensions[0]
                length = dimensions[1]
            _add_y_cone(bm, radius_bottom, radius_top, length)
            if collider.shape in {"CAPSULE", "TAPERED_CAPSULE"}:
                _add_uv_sphere(bm, radius_bottom, -length * 0.5)
                _add_uv_sphere(bm, radius_top, length * 0.5)
        else:
            raise ValueError(f"unsupported collider shape {collider.shape}")

        x, y, z, w = collider.orientation
        source_transform = (
            Matrix.Translation(collider.offset)
            @ Quaternion((w, x, y, z)).normalized().to_matrix().to_4x4()
        )
        bmesh.ops.transform(
            bm,
            matrix=source_to_blender @ source_transform,
            verts=bm.verts,
        )
        mesh = bpy.data.meshes.new(f"COL_{collider.shape}_{index:02d}")
        bm.to_mesh(mesh)
    finally:
        bm.free()

    obj = bpy.data.objects.new(mesh.name, mesh)
    collection.objects.link(obj)
    obj.display_type = "WIRE"
    obj.color = (1.0, 0.15, 0.05, 1.0)
    obj["enshrouded_collider_shape"] = collider.shape
    obj["enshrouded_template_guid"] = collider.template_guid
    obj["enshrouded_template_name"] = collider.template_name
    return obj


def _import_colliders(context, model_name, colliders, source_to_blender):
    if not colliders:
        return []
    collection = bpy.data.collections.new(f"{model_name}_Colliders")
    context.collection.children.link(collection)
    return [
        _create_collider_object(collider, collection, source_to_blender, index)
        for index, collider in enumerate(colliders)
    ]


def _full_topology_records(export_mesh, object_to_source):
    export_mesh.calc_loop_triangles()
    uv_layer = export_mesh.uv_layers.active
    has_tangents = False
    if uv_layer is not None:
        try:
            export_mesh.calc_tangents(uvmap=uv_layer.name)
            has_tangents = True
        except RuntimeError:
            has_tangents = False

    direction_matrix = object_to_source.to_3x3()
    normal_matrix = direction_matrix.inverted_safe().transposed()
    handedness_flip = -1.0 if direction_matrix.determinant() < 0.0 else 1.0
    records = []
    indices = []
    for triangle in export_mesh.loop_triangles:
        triangle_indices = []
        for loop_index in triangle.loops:
            loop = export_mesh.loops[loop_index]
            position = object_to_source @ export_mesh.vertices[loop.vertex_index].co
            normal = (normal_matrix @ loop.normal).normalized()
            if has_tangents:
                tangent = (direction_matrix @ loop.tangent).normalized()
                bitangent_sign = float(loop.bitangent_sign) * handedness_flip
            else:
                tangent = _fallback_tangent(normal)
                bitangent_sign = 1.0
            if uv_layer is not None:
                uv = uv_layer.data[loop_index].uv
                game_uv = (float(uv.x), 1.0 - float(uv.y))
            else:
                game_uv = (0.0, 0.0)
            triangle_indices.append(len(records))
            records.append(
                (
                    tuple(position),
                    tuple(normal),
                    tuple(tangent),
                    bitangent_sign,
                    game_uv,
                    b"\xff\xff\xff\xff",
                )
            )
        # The Blender-to-game transform changes handedness. Keeping Blender's
        # loop order therefore produces Keen's opposite front-face winding.
        indices.extend(triangle_indices)

    if has_tangents:
        export_mesh.free_tangents()
    return tuple(records), tuple(indices)


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
        if not props.export_directory.strip():
            props.export_directory = str(_default_export_directory(kfc))

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
                colliders = (
                    find_model_colliders(reader, props.resolved_guid)
                    if props.import_colliders else ()
                )

            lod_indices = range(len(model.lods)) if props.import_all_lods else (props.lod,)
            source_to_blender = _source_to_blender_matrix()
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

            imported_colliders = _import_colliders(
                context, model.debug_name, colliders, source_to_blender
            )

            for selected in context.selected_objects:
                selected.select_set(False)
            for obj in imported:
                obj.select_set(True)
            if imported:
                context.view_layer.objects.active = imported[0]
            props.content_index = content_index
            props.export_target_guid = props.resolved_guid
        except Exception as exc:
            self.report({"ERROR"}, f"Import failed: {exc}")
            return {"CANCELLED"}

        triangle_count = sum(len(obj.data.polygons) for obj in imported)
        self.report(
            {"INFO"},
            f"Imported {len(imported)} model(s), {triangle_count} triangles and "
            f"{len(imported_colliders)} collider(s) from content {content_index}"
        )
        return {"FINISHED"}


class ENSHROUDED_OT_copy_guid(Operator):
    bl_idname = "enshrouded.copy_guid"
    bl_label = "Copy GUID"
    bl_description = "Copy the selected RenderModel GUID to the clipboard"

    def execute(self, context):
        guid = context.scene.enshrouded.resolved_guid
        if not guid:
            self.report({"WARNING"}, "No RenderModel GUID selected")
            return {"CANCELLED"}
        context.window_manager.clipboard = guid
        self.report({"INFO"}, "RenderModel GUID copied")
        return {"FINISHED"}


class ENSHROUDED_OT_use_default_export_folder(Operator):
    bl_idname = "enshrouded.use_default_export_folder"
    bl_label = "Use Game Mods Folder"
    bl_description = "Set the export folder to <Game Path>/mods"

    def execute(self, context):
        kfc, resources = _archive_paths(context)
        if not kfc.is_file() or not resources.is_file():
            self.report({"ERROR"}, "Set a valid Enshrouded game path in Add-on Preferences")
            return {"CANCELLED"}
        context.scene.enshrouded.export_directory = str(_default_export_directory(kfc))
        return {"FINISHED"}


class ENSHROUDED_OT_export_replacement(Operator):
    bl_idname = "enshrouded.export_replacement"
    bl_label = "Export Replacement Mod"
    bl_description = "Export the selected imported mesh as an EML RenderModel replacement mod"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == "MESH"

    def execute(self, context):
        props = context.scene.enshrouded
        if props.export_mode not in {"REPLACEMENT", "FULL_REPLACEMENT"}:
            self.report({"ERROR"}, "New Model export is not implemented yet")
            return {"CANCELLED"}

        obj = context.active_object
        source_guid = obj.get("enshrouded_guid", "")
        if not source_guid:
            self.report({"ERROR"}, "Selected object has no Enshrouded source GUID")
            return {"CANCELLED"}

        target_guid = props.export_target_guid.strip().lower() or source_guid
        if not looks_like_guid(target_guid):
            self.report({"ERROR"}, "Target GUID is not a valid GUID")
            return {"CANCELLED"}

        mod_id = props.mod_id.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", mod_id):
            self.report({"ERROR"}, "Mod ID may contain only lowercase letters, digits, '_' and '-'")
            return {"CANCELLED"}

        kfc, resources = _archive_paths(context)
        if not kfc.is_file() or not resources.is_file():
            self.report({"ERROR"}, "Set a valid Enshrouded game path in Add-on Preferences")
            return {"CANCELLED"}

        evaluated_object = obj.evaluated_get(context.evaluated_depsgraph_get())
        export_mesh = evaluated_object.to_mesh(
            preserve_all_data_layers=True,
            depsgraph=context.evaluated_depsgraph_get(),
        )
        try:
            blender_to_source = _source_to_blender_matrix().inverted()
            object_to_source = blender_to_source @ evaluated_object.matrix_world
            if props.export_mode == "FULL_REPLACEMENT":
                vertex_records, indices = _full_topology_records(export_mesh, object_to_source)
                positions = None
            else:
                positions = tuple(
                    tuple(object_to_source @ vertex.co)
                    for vertex in export_mesh.vertices
                )
                vertex_records = indices = None
        finally:
            evaluated_object.to_mesh_clear()

        try:
            with KFC3Reader(kfc, resources) as reader:
                lookup = resolve_model(reader, target_guid)
                if lookup is None:
                    raise ValueError(f"target RenderModel not found: {target_guid}")
                model = parse_render_model(reader.read_resource(lookup.resource_index))
                _content_index, original_data = reader.read_content(model.render_data_hash)
            if props.export_mode == "FULL_REPLACEMENT":
                replacement = build_full_topology_payload(vertex_records, indices)
            else:
                replacement = build_replacement_payload(model, original_data, positions)
            model_name = model.debug_name
        except Exception as exc:
            self.report({"ERROR"}, f"Replacement build failed: {exc}")
            return {"CANCELLED"}

        try:
            target = write_replacement_mod(
                _export_directory(props, kfc),
                mod_id,
                props.mod_name.strip() or mod_id,
                props.mod_version.strip() or "0.1.0",
                props.mod_author.strip() or "Unknown",
                target_guid,
                model_name,
                replacement,
            )
        except Exception as exc:
            self.report({"ERROR"}, f"Mod export failed: {exc}")
            return {"CANCELLED"}

        obj["enshrouded_last_export_path"] = str(target)
        self.report(
            {"INFO"},
            f"Exported {mod_id}: {replacement.vertex_count} vertices, {len(replacement.data)} bytes"
        )
        return {"FINISHED"}

_classes = (
    ENSHROUDED_OT_load_model_list,
    ENSHROUDED_OT_resolve_model,
    ENSHROUDED_OT_import_model,
    ENSHROUDED_OT_copy_guid,
    ENSHROUDED_OT_use_default_export_folder,
    ENSHROUDED_OT_export_replacement,
)

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
