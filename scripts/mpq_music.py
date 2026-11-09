"""Write a classic MPQ with shared, uncompressed MP3 payloads.

Each name has its own block-table record, while identical records share a payload.
This preserves native archive enumeration and avoids storing the same D3
track hundreds of times when replacing shared WoW music families.
"""
import hashlib
import struct as S
from pathlib import Path
import mpyq
from assets import member, require, digest
from mpq_read import read_file


def encrypt_table(data, key):
    seed = 0xEEEEEEEE
    result = bytearray()
    for (plain,) in S.iter_unpack('<I', data):
        seed = (seed + mpyq.MPQArchive.encryption_table[0x400 + (key & 255)]) & 0xFFFFFFFF
        result.extend(S.pack('<I', (plain ^ (key + seed)) & 0xFFFFFFFF))
        key = (((~key << 21) + 0x11111111) | (key >> 11)) & 0xFFFFFFFF
        seed = (plain + seed + (seed << 5) + 3) & 0xFFFFFFFF
    return bytes(result)


def pack_music(files, output):
    output = Path(output).resolve()
    require(not output.exists(), 'MPQ output already exists')
    index = object.__new__(mpyq.MPQArchive)
    records = []
    seen = set()
    for name, path in files.items():
        name = member(name)
        require(name.lower().endswith('.mp3') and name.isascii(), 'Expected ASCII MP3 archive name')
        require(name.lower() not in seen, 'Duplicate archive name')
        seen.add(name.lower())
        path = Path(path)
        records.append(dict(path=name, source=path, bytes=path.stat().st_size, sha256=digest(path)))
    require(records, 'Empty music archive')
    capacity = 1
    while capacity < (len(records) + 1) * 2:
        capacity *= 2
    hashes = [b'\xff' * 16] * capacity
    blocks = []
    names = []
    unique = {}

    def add_hash(name, block):
        name = name.replace('/', '\\')
        at = index._hash(name, 'TABLE_OFFSET') % capacity
        while hashes[at] != b'\xff' * 16:
            at = (at + 1) % capacity
        hashes[at] = S.pack('<IIHHI', index._hash(name, 'HASH_A'), index._hash(name, 'HASH_B'), 0, 0, block)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(bytes(32))
        for record in records:
            key = (record['sha256'], record['bytes'])
            if key not in unique:
                data = record['source'].read_bytes()
                unique[key] = S.pack('<4I', stream.tell(), len(data), len(data), 0x81000000)
                stream.write(data)
            add_hash(record['path'], len(blocks))
            blocks.append(unique[key])
            names.append(record['path'].replace('/', '\\'))
        listing = ('\r\n'.join(sorted(names) + ['(listfile)']) + '\r\n').encode('ascii')
        add_hash('(listfile)', len(blocks))
        blocks.append(S.pack('<4I', stream.tell(), len(listing), len(listing), 0x81000000))
        stream.write(listing)
        hash_offset = stream.tell()
        stream.write(encrypt_table(b''.join(hashes), index._hash('(hash table)', 'TABLE')))
        block_offset = stream.tell()
        stream.write(encrypt_table(b''.join(blocks), index._hash('(block table)', 'TABLE')))
        size = stream.tell()
        require(size < 2**32, 'Classic MPQ exceeds 4 GiB')
        stream.seek(0)
        stream.write(S.pack('<4sIIHH4I', b'MPQ\x1a', 32, size, 0, 3, hash_offset, block_offset, capacity, len(blocks)))
    verified_blocks = {}
    with output.open('rb') as stream:
        archive = mpyq.MPQArchive(stream)
        require({n.decode().replace('\\', '/') for n in archive.files if not n.startswith(b'(')} == {r['path'] for r in records}, 'MPQ listfile mismatch')
        for record in records:
            name = record['path'].replace('/', '\\')
            entry = archive.get_hash_table_entry(name)
            require(entry is not None, 'Missing music alias')
            if entry.block_table_index not in verified_blocks:
                data = read_file(archive, name)
                verified_blocks[entry.block_table_index] = (hashlib.sha256(data).hexdigest(), len(data))
            require(verified_blocks[entry.block_table_index] == (record['sha256'], record['bytes']), 'Music payload mismatch')
    return dict(mpq=str(output), sha256=digest(output), archive_members_verified=len(records), unique_audio_blocks=len(unique),
                files=[{k: v for k, v in r.items() if k != 'source'} for r in records])
