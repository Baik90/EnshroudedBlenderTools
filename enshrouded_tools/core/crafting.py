"""Read KFC3/KFC4 crafting choices; no Blender dependency."""
import struct
import uuid
from .collision import ITEM_INFO_TYPE_HASH, _fnv1a32, _relative_array, _relative_string


def crafting_catalog(reader):
    items, workshops, recipes = {}, {}, {}
    # Retail archives omit many ItemInfo.debugName strings. The registry keeps
    # parallel itemRefs/dbgNames arrays even when those strings are stripped.
    registry_names = {}
    for i, rid in enumerate(reader.resource_ids):
        if rid.part_index or rid.type_hash != _fnv1a32('keen::ItemRegistryResource'):
            continue
        p = reader.read_resource(i)
        refs, ref_count = _relative_array(p, 0, 16)
        names, name_count = _relative_array(p, 56, 8)
        if ref_count != name_count:
            raise ValueError('Item registry itemRefs/dbgNames counts differ')
        for n in range(ref_count):
            guid = str(uuid.UUID(bytes_le=p[refs+n*16:refs+(n+1)*16]))
            name = _relative_string(p, names+n*8)
            if name:
                registry_names[guid] = name
    for i, rid in enumerate(reader.resource_ids):
        if rid.part_index == 0 and rid.type_hash == ITEM_INFO_TYPE_HASH:
            p = reader.read_resource(i)
            name = (_relative_string(p, 2080 if reader.format == 'KFC4' else 1936)
                    or registry_names.get(rid.guid))
            # Distinguish identically named items without Blender silently
            # renaming collection entries and invalidating selection lookup.
            items[rid.guid] = name + ' [' + rid.guid[:8] + ']' if name else rid.guid
    for i, rid in enumerate(reader.resource_ids):
        if rid.part_index or rid.type_hash != 2833930532:
            continue
        p = reader.read_resource(i)
        for field in (0, 8):
            start, count = _relative_array(p, field, 56)
            for n in range(count):
                o = start + n * 56
                wid = struct.unpack_from('<I', p, o + 20)[0]
                guid = str(uuid.UUID(bytes_le=p[o+32:o+48]))
                workshops[wid] = items.get(guid, 'Workshop ' + str(wid))
    for i, rid in enumerate(reader.resource_ids):
        if rid.part_index or rid.type_hash != 1599308495:
            continue
        p = reader.read_resource(i)
        start, count = _relative_array(p, 8, 168)
        for n in range(count):
            o = start + n * 168
            guid = str(uuid.UUID(bytes_le=p[o:o+16]))
            wid = struct.unpack_from('<I', p, o+36)[0]
            # A donor preserves the workstation's existing UI group and rules.
            label = workshops.get(wid, 'Workshop ' + str(wid))
            name = _relative_string(p, o+120) or guid
            recipes[guid] = label + ' / ' + name + ' [' + guid[:8] + ']'
    return items, recipes
