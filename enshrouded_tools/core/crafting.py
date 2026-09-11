"""Read crafting choices from build 1076226; no Blender dependency."""
import struct
import uuid
from .collision import ITEM_INFO_TYPE_HASH, _relative_array, _relative_string


def crafting_catalog(reader):
    items, workshops, recipes = {}, {}, {}
    for i, rid in enumerate(reader.resource_ids):
        if rid.part_index == 0 and rid.type_hash == ITEM_INFO_TYPE_HASH:
            p = reader.read_resource(i)
            items[rid.guid] = _relative_string(p, 1936) or rid.guid
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
