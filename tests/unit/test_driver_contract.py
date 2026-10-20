"""Compile and exercise the actual driver's portable boundary predicates."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class DriverContract(unittest.TestCase):
    def test_compiled_datapath_contract(self):
        code = r'''
#include <stdint.h>
#include <limits.h>
#include <assert.h>
#include <string.h>
#include "agnic_contract.h"
int main(void) {
    uint8_t wire[AGNIC_FRAME_LIMIT] = {0};
    uint8_t mac[6], base[6], second[6];
    uint8_t resp[56] = {0x52, 0x4f, 0x57, 0x53, 1, 3, 0, 11};
    unsigned p, i;
    assert(AGNIC_FRAME_LIMIT == 1588);
    /* Every port, including a 1500-byte VLAN payload, preserves Ethernet bytes. */
    for (p = 0; p < AGNIC_PORT_COUNT; p++) {
        wire[0] = 0x81 + p;
        for (i = AGNIC_PORT_PREFIX; i < sizeof(wire); i++) wire[i] = (uint8_t)i;
        assert(agnic_wire_port(wire, sizeof(wire)) == (int)p);
        assert(wire[AGNIC_PORT_PREFIX] == 66);
        assert(agnic_wire_port(wire, 79) == -1);
        wire[1] = 1;
        assert(agnic_wire_port(wire, sizeof(wire)) == -1);
        wire[1] = 0;
    }
    for (p = 0; p < 256; p++) {
        wire[0] = p;
        assert((agnic_wire_port(wire, sizeof(wire)) >= 0) == (p >= 0x81 && p <= 0x89));
    }
    /* Reject poisoned indices, never modulo-mask them into valid queue slots. */
    for (i = 0; i < 512; i++) assert(agnic_ring_index_valid(i, 256) == (i < 256));
    assert(!agnic_ring_index_valid(UINT32_MAX, 256));
    assert(!agnic_ring_index_valid(0, 0));
    assert(!agnic_ring_index_valid(1, 255));
    assert(agnic_rx_extent_valid(0, 0, AGNIC_FRAME_LIMIT, 2048));
    assert(agnic_rx_extent_valid(64, 2, 1982, 2048));
    assert(!agnic_rx_extent_valid(64, 2, 1983, 2048));
    assert(!agnic_rx_extent_valid(UINT32_MAX, 2, 80, 2048));
    assert(!agnic_rx_extent_valid(0, UINT32_MAX, 80, 2048));
    assert(!agnic_rx_extent_valid(0, 0, 0, 2048));
    assert(agnic_swop_cap_valid(AGNIC_SWOP_MAGIC, 1, 0));
    assert(agnic_swop_cap_valid(AGNIC_SWOP_MAGIC, 2, 0x53430001));
    assert(!agnic_swop_cap_valid(AGNIC_SWOP_MAGIC, 2, 0));
    assert(!agnic_swop_cap_valid(AGNIC_SWOP_MAGIC, 3, 0x53430001));
    assert(!agnic_swop_cap_valid(0xffffffff, 1, 0));
    assert(agnic_swop_ports_valid(resp, 56));
    assert(!agnic_swop_ports_valid(resp, 12));
    resp[0] = 0x50; /* verbatim request echo is not a response */
    assert(!agnic_swop_ports_valid(resp, 56));
    resp[0] = 0x52; resp[6] = 1;
    assert(!agnic_swop_ports_valid(resp, 56));
    resp[6] = 0; resp[7] = 10;
    assert(!agnic_swop_ports_valid(resp, 56));
    assert(agnic_uuid_mac("01234567-89ab-cdef-0123-456789abcdef", base));
    assert(agnic_uuid_mac("01234567-89AB-CDEF-0123-456789ABCDEF", second));
    assert(memcmp(base, second, 6) == 0);
    assert(agnic_uuid_mac("11234567-89ab-cdef-0123-456789abcdef", second));
    assert(memcmp(base, second, 5) != 0);
    assert(!agnic_uuid_mac("not-set", second));
    assert(!agnic_uuid_mac("00000000-0000-0000-0000-000000000000", second));
    assert(!agnic_uuid_mac("ffffffff-ffff-ffff-ffff-ffffffffffff", second));
    assert(!agnic_uuid_mac("01234567-89ab-cdef-0123-456789abcdeg", second));
    for (p = 1; p <= AGNIC_PORT_COUNT; p++) {
        agnic_port_mac(base, p, mac);
        assert(agnic_mac_valid(mac));
        assert((mac[0] & 3) == 2 && mac[5] == p);
        assert(memcmp(mac, base, 5) == 0);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp, "contract.c")
            binary = Path(tmp, "contract")
            source.write_text(code)
            subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra",
                            "-Werror", "-fsanitize=undefined", "-I", str(ROOT / "driver/if_agnic"),
                            str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
