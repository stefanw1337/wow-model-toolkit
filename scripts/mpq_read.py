"""Read MPQ data sectors using mpyq's index, including uncompressed sectors.

mpyq 0.2.5 compares each sector's stored size with the remaining *file* size.
Mixed compressed/uncompressed sectors need the remaining *sector* size instead.
"""
import bz2
import struct
import zlib


def read_file(archive, name):
    entry = archive.get_hash_table_entry(name)
    if entry is None:
        return None
    block = archive.block_table[entry.block_table_index]
    if not block.flags & 0x80000000:
        return None
    if block.flags & 0x10000:
        raise ValueError('Encrypted MPQ members are unsupported')
    if block.flags & 0x100:
        raise ValueError('Imploded MPQ members are unsupported')
    archive.file.seek(archive.header['offset'] + block.offset)
    raw = archive.file.read(block.archived_size)
    if len(raw) != block.archived_size:
        raise ValueError('Truncated MPQ member')

    def decode(data, expected):
        if len(data) == expected:
            return data
        if not data or len(data) > expected:
            raise ValueError('Invalid MPQ sector size')
        if data[0] == 2:
            result = zlib.decompress(data[1:])
        elif data[0] == 16:
            result = bz2.decompress(data[1:])
        else:
            raise ValueError('Unsupported MPQ compression: ' + str(data[0]))
        if len(result) != expected:
            raise ValueError('Decoded MPQ sector size mismatch')
        return result

    if not block.flags & 0x200:
        result = raw
    elif block.flags & 0x1000000:
        result = decode(raw, block.size)
    else:
        sector_size = 512 << archive.header['sector_size_shift']
        sectors = (block.size + sector_size - 1) // sector_size
        table_count = sectors + 1 + bool(block.flags & 0x4000000)
        if len(raw) < 4 * table_count:
            raise ValueError('Truncated MPQ sector table')
        positions = struct.unpack_from('<' + 'I' * table_count, raw)
        if positions[0] < table_count * 4 or any(a > b for a, b in zip(positions, positions[1:])) or positions[-1] > len(raw):
            raise ValueError('Invalid MPQ sector offsets')
        result = b''.join(decode(raw[positions[i]:positions[i+1]], min(sector_size, block.size - i * sector_size)) for i in range(sectors))
    if len(result) != block.size:
        raise ValueError('MPQ member size mismatch')
    return result
