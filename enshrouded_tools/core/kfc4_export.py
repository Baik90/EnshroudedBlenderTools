"""Build 1269579 static export layout and streamed-texture metadata."""
from .material import _BLOCK_BYTES


def topology_lua(payload, mod_id):
    ranges = payload.material_mesh_ranges
    lines = [f'''if #model.meshes < {len(ranges)} or #model.lods < 1 then
 error("[{mod_id}] base has insufficient reusable meshes/LODs")
end
if #model.materials < {max(m for m, _, _ in ranges)+1} then error("Missing material slots") end
local exported_meshes = {{}}
''']
    for i, (material, offset, count) in enumerate(ranges, 1):
        lines.append(f'''do
 local mesh = model.meshes[{i}]
 mesh.materialIndex = {material}
 mesh.vertexCount = {payload.vertex_count}
 mesh.indexOffset = {offset}
 mesh.indexCount = {count}
 mesh.vertexDataByteOffset = 0
 mesh.meshletOffset = 0
 mesh.meshletCount = 0
 mesh.blendShapeByteOffset = 0
 mesh.skinVertexOffset = 0
 mesh.vertexFormat = "PNTCT"
 mesh.vertexStride = 24
 mesh.positionQuantization = "x21y21z21_unorm"
 mesh.clothMeshIndex = 0
 table.insert(exported_meshes, mesh)
end
''')
    lines.append(f'''model.meshes = exported_meshes
model.meshlets = {{}}
model.hasCardClusterLod = false
model.vertexData.start = 0
model.vertexData.count = {payload.vertex_data_size}
model.indexData.start = {payload.vertex_data_size}
model.indexData.count = {payload.index_count*2}
model.meshletData.start = 0
model.meshletData.count = 0
model.skinningData.start = 0
model.skinningData.count = 0
model.blendShapeData.start = 0
model.blendShapeData.count = 0
model.blendShapes = {{}}
model.blendShapeMask = 0
for _, lod in ipairs(model.lods) do
 lod.meshOffset = 0
 lod.meshCount = {len(ranges)}
end
''')
    return '\n'.join(lines)


def texture_stream(patch):
    try:
        block = _BLOCK_BYTES[patch.vk_format]
    except KeyError:
        raise ValueError('KFC4 texture requires a supported Vulkan BC format') from None
    if patch.width < 1 or patch.height < 1 or patch.mip_count != max(patch.width, patch.height).bit_length():
        raise ValueError('KFC4 textures require a complete mip chain')
    width, height = patch.width, patch.height
    sizes = []
    for _ in range(patch.mip_count):
        sizes.append(max(1,(width+3)//4)*max(1,(height+3)//4)*block)
        width, height = max(1,width//2), max(1,height//2)
    if sum(sizes) != len(patch.data):
        raise ValueError('KFC4 texture mip chain size mismatch')
    offset, ranges = 0, []
    for size in sizes:
        remaining = len(patch.data)-offset
        if remaining <= 4096:
            break
        ranges.append((offset, remaining))
        offset += size
    return patch.data[offset:], tuple(ranges)


def texture_lua(code, patches):
    if not patches:
        return code
    for anchor in ('if image.debugName == texture.slot then',
                   'target_image = image',
                   'target_image.data = game.guid.to_content_hash(texture_content.guid)'):
        if code.count(anchor) != 1:
            raise ValueError('Texture generator changed; KFC4 migration anchor missing')
    code = code.replace('if image.debugName == texture.slot then',
        'if image.texture.debugName:sub(-#texture.slot) == texture.slot then')
    code = code.replace('target_image = image', 'target_image = image.texture')
    code = code.replace('target_image.data = game.guid.to_content_hash(texture_content.guid)',
                        'target_image.content.hash = game.guid.to_content_hash(texture_content.guid)')
    streams = []
    for patch in patches:
        _tail, ranges = texture_stream(patch)
        entries = ','.join(f'{{start={start},count={count}}}' for start,count in ranges)
        # Slot and material jointly identify a texture; filenames contain only
        # generated indices/GUIDs and validated slot names.
        streams.append(f'''if patch.materialIndex == {patch.material_index+1} and texture.slot == "{patch.slot_name}" then
 local tail_buffer = io.read(texture.file .. ".tail")
 if tail_buffer == nil then error("Texture mip tail missing") end
 local tail = game.assets.create_content(tail_buffer)
 if tail == nil then error("Could not create texture mip tail") end
 target_image.mipTailContent.hash = game.guid.to_content_hash(tail.guid)
 target_image.mipChainContentRanges = {{{entries}}}
end''')
    return code.replace('        print("[', '\n'.join(streams) + '\n        print("[', 1)


def migrate_registration(code):
    code = code.replace('model.renderData = game.guid.to_content_hash(content.guid)',
                        'model.renderData.hash = game.guid.to_content_hash(content.guid)')
    code = code.replace('localization.data.keenglishDataHash', 'localization.data.keenglishData.hash')
    code = code.replace('language.dataHash', 'language.data.hash')
    code = code.replace('sound.data.dataHash =', 'sound.data.streamedData.hash =')
    code = code.replace('local icon_resource = game.assets.create_resource({',
        'local native_icon_source = game.assets.get_resource(source_item.guid, "keen::UiTextureResource", 0)\n'
        'local icon_resource = game.assets.create_resource({')
    code = code.replace('data = game.guid.to_content_hash(icon_content.guid),',
        'data = native_icon_source and native_icon_source.data.data or {hash = game.guid.to_content_hash(icon_content.guid)},')
    code = code.replace('-- Item thumbnails are companion resources keyed by ItemInfo GUID + texture type.',
        'icon_resource.data.data.hash = game.guid.to_content_hash(icon_content.guid)\n'
        '-- Item thumbnails are companion resources keyed by ItemInfo GUID + texture type.')
    code = code.replace('model.boundingSphere.radius = sphere_r',
                        'model.boundingSphere.radius = sphere_r\nmodel.wholeModelRadius = sphere_r')
    return code
