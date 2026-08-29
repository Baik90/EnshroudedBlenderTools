#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Optional

KFC3_MAGIC = b"KFC3"


@dataclass(frozen=True)
class KFCLocation:
    offset: int
    count: int


@dataclass(frozen=True)
class ResourceChunkInfo:
    offset: int
    size: int
    compressed_size: int
    uncompressed_offset: int
    uncompressed_size: int


@dataclass(frozen=True)
class ResourceEntry:
    offset: int
    size: int


@dataclass(frozen=True)
class ContentEntry:
    offset: int
    container_index: int


@dataclass(frozen=True)
class ResourceId:
    guid_bytes: bytes
    type_hash: int
    part_index: int

    @staticmethod
    def _guid_to_string(data: bytes) -> str:
        if len(data) != 16:
            raise ValueError("GUID must be exactly 16 bytes")
        a = int.from_bytes(data[0:4], "little")
        b = int.from_bytes(data[4:6], "little")
        c = int.from_bytes(data[6:8], "little")
        d = int.from_bytes(data[8:10], "big")
        e = int.from_bytes(data[10:14], "big")
        f = int.from_bytes(data[14:16], "big")
        return f"{a:08x}-{b:04x}-{c:04x}-{d:04x}-{e:08x}{f:04x}"

    @property
    def guid(self) -> str:
        return self._guid_to_string(self.guid_bytes)

    @property
    def qualified(self) -> str:
        return f"{self.guid}_{self.type_hash:08x}_{self.part_index}"


@dataclass(frozen=True)
class KFC3Header:
    file_size_field: int
    unk0: int
    version: KFCLocation
    containers: KFCLocation
    unused0: KFCLocation
    unused1: KFCLocation
    resource_locations: KFCLocation
    resource_indices: KFCLocation
    content_buckets: KFCLocation
    content_keys: KFCLocation
    content_values: KFCLocation
    resource_buckets: KFCLocation
    resource_keys: KFCLocation
    resource_values: KFCLocation
    resource_bundle_buckets: KFCLocation
    resource_bundle_keys: KFCLocation
    resource_bundle_values: KFCLocation
    resource_chunks: KFCLocation


class KFC3Reader:
    """Read-only reader for Enshrouded KFC3 + KFC3 resource store.

    The .kfc file stores tables/indexes. The .kfc_resources file stores
    independently Zstandard-compressed logical chunks.
    """

    def __init__(self, kfc_path: os.PathLike | str, resources_path: os.PathLike | str | None = None):
        self.kfc_path = Path(kfc_path)
        if resources_path is None:
            # enshrouded.kfc -> enshrouded.kfc_resources
            resources_path = self.kfc_path.with_suffix(".kfc_resources")
        self.resources_path = Path(resources_path)

        self._kfc: BinaryIO = self.kfc_path.open("rb")
        self._resources: BinaryIO = self.resources_path.open("rb")
        self.header = self._read_header()
        self.version = self._read_version()
        self.chunks = self._read_chunks()
        self.resource_ids = self._read_resource_ids()
        self.resource_entries = self._read_resource_entries()
        self._resource_index_by_key = {
            (resource_id.guid, resource_id.type_hash, resource_id.part_index): index
            for index, resource_id in enumerate(self.resource_ids)
        }
        self.content_keys = self._read_content_keys()
        self.content_entries = self._read_content_entries()
        self._content_index_by_key = {key: index for index, key in enumerate(self.content_keys)}
        self._chunk_cache: dict[int, bytes] = {}

        if len(self.resource_ids) != len(self.resource_entries):
            raise ValueError(
                f"resource key/value count mismatch: {len(self.resource_ids)} != {len(self.resource_entries)}"
            )
        if len(self.content_keys) != len(self.content_entries):
            raise ValueError(
                f"content key/value count mismatch: {len(self.content_keys)} != {len(self.content_entries)}"
            )

    def close(self) -> None:
        self._kfc.close()
        self._resources.close()

    def __enter__(self) -> "KFC3Reader":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @staticmethod
    def _u32(f: BinaryIO) -> int:
        data = f.read(4)
        if len(data) != 4:
            raise EOFError("unexpected EOF while reading u32")
        return struct.unpack("<I", data)[0]

    @staticmethod
    def _read_location(f: BinaryIO) -> KFCLocation:
        # KFC stores a relative u32 offset, relative to the location of the
        # offset field itself (not to the end of KFCLocation).
        pos = f.tell()
        rel = KFC3Reader._u32(f)
        count = KFC3Reader._u32(f)
        absolute = 0 if rel == 0 else pos + rel
        return KFCLocation(absolute, count)

    def _read_header(self) -> KFC3Header:
        f = self._kfc
        f.seek(0)
        magic = f.read(4)
        if magic != KFC3_MAGIC:
            raise ValueError(f"not KFC3: magic={magic!r}")
        file_size_field = self._u32(f)
        unk0 = self._u32(f)
        padding = f.read(4)
        if padding != b"\0\0\0\0":
            raise ValueError(f"unexpected non-zero header padding: {padding.hex()}")

        names = [
            "version", "containers", "unused0", "unused1",
            "resource_locations", "resource_indices",
            "content_buckets", "content_keys", "content_values",
            "resource_buckets", "resource_keys", "resource_values",
            "resource_bundle_buckets", "resource_bundle_keys", "resource_bundle_values",
            "resource_chunks",
        ]
        loc = {name: self._read_location(f) for name in names}
        return KFC3Header(file_size_field=file_size_field, unk0=unk0, **loc)

    def _read_version(self) -> str:
        loc = self.header.version
        self._kfc.seek(loc.offset)
        return self._kfc.read(loc.count).decode("utf-8", errors="replace")

    def _read_chunks(self) -> list[ResourceChunkInfo]:
        loc = self.header.resource_chunks
        self._kfc.seek(loc.offset)
        chunks = []
        for _ in range(loc.count):
            raw = self._kfc.read(20)
            if len(raw) != 20:
                raise EOFError("unexpected EOF in ResourceChunkInfo table")
            chunks.append(ResourceChunkInfo(*struct.unpack("<IIIII", raw)))
        return chunks

    def _read_resource_ids(self) -> list[ResourceId]:
        loc = self.header.resource_keys
        self._kfc.seek(loc.offset)
        out = []
        for _ in range(loc.count):
            raw = self._kfc.read(32)
            if len(raw) != 32:
                raise EOFError("unexpected EOF in ResourceId table")
            guid = raw[0:16]
            type_hash, part_index, reserved0, reserved1 = struct.unpack("<IIII", raw[16:32])
            if reserved0 != 0 or reserved1 != 0:
                raise ValueError("ResourceId reserved fields are non-zero")
            out.append(ResourceId(guid, type_hash, part_index))
        return out

    def _read_resource_entries(self) -> list[ResourceEntry]:
        loc = self.header.resource_values
        self._kfc.seek(loc.offset)
        out = []
        for _ in range(loc.count):
            raw = self._kfc.read(8)
            if len(raw) != 8:
                raise EOFError("unexpected EOF in ResourceEntry table")
            out.append(ResourceEntry(*struct.unpack("<II", raw)))
        return out

    def _read_content_keys(self) -> list[bytes]:
        loc = self.header.content_keys
        self._kfc.seek(loc.offset)
        out = []
        for _ in range(loc.count):
            raw = self._kfc.read(16)
            if len(raw) != 16:
                raise EOFError("unexpected EOF in content key table")
            out.append(raw)
        return out

    def _read_content_entries(self) -> list[ContentEntry]:
        loc = self.header.content_values
        self._kfc.seek(loc.offset)
        out = []
        for _ in range(loc.count):
            raw = self._kfc.read(16)
            if len(raw) != 16:
                raise EOFError("unexpected EOF in content value table")
            offset, container_word, reserved0, reserved1 = struct.unpack("<IIII", raw)
            if reserved0 != 0 or reserved1 != 0:
                raise ValueError("content value reserved fields are non-zero")
            out.append(ContentEntry(offset=offset, container_index=container_word >> 16))
        return out

    @staticmethod
    def _decompress_zstd(data: bytes, expected_size: int) -> bytes:
        # Python 3.14+
        try:
            from compression import zstd as std_zstd  # type: ignore
            out = std_zstd.decompress(data)
            if len(out) != expected_size:
                raise ValueError(f"zstd size mismatch: expected {expected_size}, got {len(out)}")
            return out
        except ImportError:
            pass

        # Common third-party module
        try:
            import zstandard as zstd  # type: ignore
            out = zstd.ZstdDecompressor().decompress(data, max_output_size=expected_size)
            if len(out) != expected_size:
                raise ValueError(f"zstd size mismatch: expected {expected_size}, got {len(out)}")
            return out
        except ImportError:
            pass

        # Dependency-free fallback if zstd executable is available.
        exe = shutil.which("zstd")
        if not exe:
            raise RuntimeError(
                "No Zstandard decoder found. Install Python package 'zstandard' "
                "or put the 'zstd' executable in PATH."
            )
        proc = subprocess.run(
            [exe, "-d", "-q", "-c"],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"zstd failed: {proc.stderr.decode(errors='replace')}")
        out = proc.stdout
        if len(out) != expected_size:
            raise ValueError(f"zstd size mismatch: expected {expected_size}, got {len(out)}")
        return out

    def decompress_chunk(self, index: int, *, cache: bool = True) -> bytes:
        if index < 0 or index >= len(self.chunks):
            raise IndexError(index)
        if index in self._chunk_cache:
            return self._chunk_cache[index]
        c = self.chunks[index]
        self._resources.seek(c.offset)
        packed = self._resources.read(c.compressed_size)
        if len(packed) != c.compressed_size:
            raise EOFError(f"chunk {index}: compressed data truncated")
        out = self._decompress_zstd(packed, c.uncompressed_size)
        if cache:
            self._chunk_cache[index] = out
        return out

    def clear_chunk_cache(self) -> None:
        """Release decompressed resource chunks held by this reader."""
        self._chunk_cache.clear()

    def logical_size(self) -> int:
        if not self.chunks:
            return 0
        c = self.chunks[-1]
        return c.uncompressed_offset + c.uncompressed_size

    def find_chunk_for_offset(self, offset: int) -> int:
        # Chunk count is tiny (~81), linear scan is fine and easy to verify.
        for i, c in enumerate(self.chunks):
            if c.uncompressed_offset <= offset < c.uncompressed_offset + c.uncompressed_size:
                return i
        raise ValueError(f"logical offset 0x{offset:x} is outside chunk map")

    def read_logical(self, offset: int, size: int) -> bytes:
        if size < 0 or offset < 0:
            raise ValueError("offset and size must be >= 0")
        if size == 0:
            return b""
        end = offset + size
        if end > self.logical_size():
            raise ValueError(f"logical read exceeds resource store: 0x{end:x} > 0x{self.logical_size():x}")

        out = bytearray()
        pos = offset
        while pos < end:
            i = self.find_chunk_for_offset(pos)
            c = self.chunks[i]
            data = self.decompress_chunk(i)
            local = pos - c.uncompressed_offset
            take = min(end - pos, c.uncompressed_size - local)
            out += data[local:local + take]
            pos += take
        return bytes(out)

    def resource(self, index: int) -> tuple[ResourceId, ResourceEntry]:
        return self.resource_ids[index], self.resource_entries[index]

    def find_resource_index(self, guid: str, type_hash: int, part_index: int = 0) -> int:
        try:
            return self._resource_index_by_key[(guid.lower(), type_hash, part_index)]
        except KeyError as exc:
            raise KeyError(
                f"resource not found: {guid}_{type_hash:08x}_{part_index}"
            ) from exc

    def read_resource(self, index: int) -> bytes:
        _, entry = self.resource(index)
        return self.read_logical(entry.offset, entry.size)

    def content_index(self, content_hash: bytes) -> int:
        if len(content_hash) != 16:
            raise ValueError("ContentHash must be exactly 16 bytes")
        try:
            return self._content_index_by_key[content_hash]
        except KeyError as exc:
            raise KeyError(f"ContentHash not found: {content_hash.hex()}") from exc

    def read_content(self, content_hash: bytes) -> tuple[int, bytes]:
        """Resolve a ContentHash and read its payload from the matching DAT."""
        index = self.content_index(content_hash)
        entry = self.content_entries[index]
        size = struct.unpack_from("<I", content_hash, 0)[0]
        dat_path = self.kfc_path.with_name(
            f"{self.kfc_path.stem}_{entry.container_index:03d}.dat"
        )
        with dat_path.open("rb") as dat_file:
            dat_file.seek(entry.offset)
            payload = dat_file.read(size)
        if len(payload) != size:
            raise EOFError(
                f"content {index} truncated in {dat_path.name}: expected {size}, got {len(payload)}"
            )
        return index, payload

    def resources_containing_offset(self, logical_offset: int) -> list[int]:
        return [
            i for i, e in enumerate(self.resource_entries)
            if e.offset <= logical_offset < e.offset + e.size
        ]

    def search_ascii(self, text: str, *, first_only: bool = False) -> Iterator[int]:
        needle = text.encode("utf-8")
        if not needle:
            return
        overlap = max(0, len(needle) - 1)
        tail = b""
        for i, c in enumerate(self.chunks):
            data = self.decompress_chunk(i, cache=False)
            combined = tail + data
            base = c.uncompressed_offset - len(tail)
            start = 0
            while True:
                pos = combined.find(needle, start)
                if pos < 0:
                    break
                absolute = base + pos
                yield absolute
                if first_only:
                    return
                start = pos + 1
            tail = data[-overlap:] if overlap else b""

    def print_info(self) -> None:
        h = self.header
        print(f"KFC:               {self.kfc_path}")
        print(f"Resources:         {self.resources_path}")
        print(f"Version/build:     {self.version}")
        print(f"KFC size field:    0x{h.file_size_field:x} ({h.file_size_field})")
        print(f"KFC actual size:   0x{self.kfc_path.stat().st_size:x} ({self.kfc_path.stat().st_size})")
        print(f"unk0:              {h.unk0}")
        print(f"Resource count:    {len(self.resource_entries)}")
        print(f"Resource chunks:   {len(self.chunks)}")
        print(f"Logical store:     0x{self.logical_size():x} ({self.logical_size()} bytes)")
        print()
        print("First chunks:")
        for i, c in enumerate(self.chunks[:8]):
            print(
                f"  {i:3}: file=0x{c.offset:08x} reserved=0x{c.size:08x} "
                f"packed=0x{c.compressed_size:08x} logical=0x{c.uncompressed_offset:08x} "
                f"raw=0x{c.uncompressed_size:08x}"
            )


def _parse_int(s: str) -> int:
    return int(s, 0)


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Read-only Enshrouded KFC3 reader")
    p.add_argument("kfc", type=Path, help="Path to enshrouded.kfc")
    p.add_argument("--resources", type=Path, help="Path to enshrouded.kfc_resources")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="Show parsed KFC3 metadata")

    ps = sub.add_parser("search", help="Search ASCII/UTF-8 text in logical resource store")
    ps.add_argument("text")
    ps.add_argument("--first", action="store_true")

    pr = sub.add_parser("resource-at", help="Show KFC resources containing a logical offset")
    pr.add_argument("offset", type=_parse_int)

    pe = sub.add_parser("extract-index", help="Extract a resource by resource table index")
    pe.add_argument("index", type=int)
    pe.add_argument("output", type=Path)

    pd = sub.add_parser("dump-range", help="Dump bytes from the logical resource store")
    pd.add_argument("offset", type=_parse_int)
    pd.add_argument("size", type=_parse_int)
    pd.add_argument("output", type=Path)

    args = p.parse_args(argv)
    with KFC3Reader(args.kfc, args.resources) as r:
        if args.cmd == "info":
            r.print_info()
        elif args.cmd == "search":
            found = False
            for off in r.search_ascii(args.text, first_only=args.first):
                found = True
                print(f"0x{off:08x} ({off})")
                for idx in r.resources_containing_offset(off):
                    rid, e = r.resource(idx)
                    print(
                        f"  resource[{idx}] {rid.qualified} "
                        f"range=0x{e.offset:08x}..0x{e.offset + e.size:08x} size=0x{e.size:x}"
                    )
            if not found:
                return 1
        elif args.cmd == "resource-at":
            matches = r.resources_containing_offset(args.offset)
            if not matches:
                print("No resource contains this offset")
                return 1
            for idx in matches:
                rid, e = r.resource(idx)
                print(
                    f"resource[{idx}] {rid.qualified} "
                    f"offset=0x{e.offset:x} size=0x{e.size:x} end=0x{e.offset + e.size:x}"
                )
        elif args.cmd == "extract-index":
            rid, e = r.resource(args.index)
            data = r.read_resource(args.index)
            args.output.write_bytes(data)
            print(f"Wrote {len(data)} bytes: {args.output}")
            print(f"ResourceId: {rid.qualified}")
            print(f"Logical range: 0x{e.offset:x}..0x{e.offset + e.size:x}")
        elif args.cmd == "dump-range":
            data = r.read_logical(args.offset, args.size)
            args.output.write_bytes(data)
            print(f"Wrote {len(data)} bytes: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
