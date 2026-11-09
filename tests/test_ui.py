"""UI binary bounds, hierarchy, atlas and generated-data regression checks."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from d3_ui import read_ui, atlas_entries
from convert_d3_ui import lua


class UITests(unittest.TestCase):
    def fixture(self):
        data = bytearray(200 + 1856 + 16)
        struct.pack_into('<II', data, 0, 0xDEADBEEF, 471)
        struct.pack_into('<3I', data, 32, 1, 184, 1856)
        data[216:220] = b'Root'
        struct.pack_into('<I', data, 200 + 1048, 2)
        struct.pack_into('<3I', data, 200 + 1600, 1, 2040, 16)
        struct.pack_into('<Qi', data, 2056, 9, 1600)
        return data

    def test_valid_layout_and_property(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Example.ui'
            path.write_bytes(self.fixture())
            result = read_ui(path)
            self.assertEqual(result['controls'][0]['path'], 'Root')
            self.assertEqual(result['controls'][0]['style']['integers']['9'], 1600)

    def test_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Example.ui'
            for offset, value in [(4, 472), (40, 1855), (200 + 1604, 999999)]:
                data = self.fixture(); struct.pack_into('<I', data, offset, value)
                path.write_bytes(data)
                with self.assertRaises(ValueError): read_ui(path)
            data = self.fixture(); data[736:743] = b'Missing'; path.write_bytes(data)
            with self.assertRaises(ValueError): read_ui(path)

    def test_named_atlas_rectangle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'atlas.tex'
            data = bytearray(728)
            struct.pack_into('<II', data, 0, 0xDEADBEEF, 47)
            struct.pack_into('<2I', data, 36, 512, 256)
            struct.pack_into('<3I', data, 536, 1, 632, 80)
            data[648:652] = b'Icon'
            struct.pack_into('<4f', data, 712, .25, .5, .5, 1)
            path.write_bytes(data)
            self.assertEqual(atlas_entries(path)[0]['pixels'], [128, 128, 256, 256])
            struct.pack_into('<f', data, 712, 2); path.write_bytes(data)
            with self.assertRaises(ValueError): atlas_entries(path)

    def test_lua_strings_cannot_inject_code(self):
        self.assertEqual(lua('"\\\n'), '"\\"\\\\\\010"')
        self.assertNotIn('\n', lua('x\ny'))
        self.assertEqual(lua({'x': False}), '{["x"]=false}')


if __name__ == '__main__': unittest.main()
