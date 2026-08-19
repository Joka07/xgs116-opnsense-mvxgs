#!/usr/bin/env python3
"""Tiny host-side unit test for the recovered 8+5*16 byte BAR-map layout."""
import struct

VERSION = 5
TARGET_COOKIE = 0xD0FAC10D
FAC = [
    (0, 0, 0x1000, 0x100),
    (2, 1, 0x2000, 0x200),
    (2, 2, 0x3000, 0x300),
    (2, 3, 0x4000, 0x400),
    (4, 4, 0x5000, 0x500),
]
blob = struct.pack('<II', VERSION, TARGET_COOKIE)
for ent in FAC:
    blob += struct.pack('<IIII', *ent)
assert len(blob) == 88
v, cookie = struct.unpack_from('<II', blob, 0)
assert v == VERSION and cookie == TARGET_COOKIE
for i, expected in enumerate(FAC):
    got = struct.unpack_from('<IIII', blob, 8 + i * 16)
    assert got == expected
print('PASS: recovered BAR-map layout is internally consistent (88 bytes).')
