/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef AGNIC_CONTRACT_H
#define AGNIC_CONTRACT_H
/* Included after the platform's integer types. No platform-specific ABI. */
#define AGNIC_PORT_COUNT 9
#define AGNIC_PORT_PREFIX 66u
#define AGNIC_ETH_HEADER 14u
#define AGNIC_VLAN_HEADER 4u
#define AGNIC_HOST_MTU 1500u
/* One 802.1Q tag and conservative FCS allowance in PF_INIT. */
#define AGNIC_FRAME_LIMIT (AGNIC_PORT_PREFIX + AGNIC_ETH_HEADER + \
    AGNIC_VLAN_HEADER + AGNIC_HOST_MTU + 4u)
#define AGNIC_SWOP_SLOT 0xf000u
#define AGNIC_SWOP_MAGIC 0x53574f50u
#define AGNIC_SWOP_RESP_MAGIC 0x53574f52u
static inline int
agnic_wire_port(const uint8_t *p, unsigned len)
{
    if (len < AGNIC_PORT_PREFIX + AGNIC_ETH_HEADER || p[1] != 0 ||
        p[0] < 0x81 || p[0] > 0x89)
        return -1;
    return p[0] - 0x81;
}
static inline int
agnic_ring_index_valid(uint32_t index, uint32_t count)
{
    return count >= 2 && (count & (count - 1)) == 0 && index < count;
}
static inline int
agnic_rx_extent_valid(uint32_t headroom, uint32_t offset,
    uint32_t len, uint32_t capacity)
{
    return len != 0 && headroom <= capacity && offset <= capacity - headroom &&
        len <= capacity - headroom - offset;
}
static inline int
agnic_swop_cap_valid(uint32_t magic, uint32_t version, uint32_t features)
{
    return magic == AGNIC_SWOP_MAGIC &&
        (version == 1 || (version == 2 && (features >> 16) == 0x5343));
}
static inline int
agnic_swop_ports_valid(const uint8_t *p, unsigned len)
{
    return len == 56 && p[0] == 0x52 && p[1] == 0x4f && p[2] == 0x57 &&
        p[3] == 0x53 && p[4] == 1 && p[5] == 3 && p[6] == 0 && p[7] == 11;
}
/* Canonical SMBIOS UUID only; reject null/all-ones placeholders. */
static inline int
agnic_uuid_mac(const char *uuid, uint8_t *base)
{
    uint64_t hash = 14695981039346656037ULL;
    unsigned i, nonzero = 0, nonf = 0;
    for (i = 0; i < 36; i++) {
        unsigned char c = uuid[i];
        if (c == 0) return 0;
        if (c >= 'A' && c <= 'F') c += 'a' - 'A';
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (c != '-') return 0;
        } else {
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return 0;
            nonzero |= c != '0';
            nonf |= c != 'f';
        }
        hash = (hash ^ c) * 1099511628211ULL;
    }
    if (uuid[36] != 0 || !nonzero || !nonf) return 0;
    for (i = 0; i < 5; i++) base[i] = (uint8_t)(hash >> (i * 8));
    base[0] = (base[0] | 2) & 0xfe;
    base[5] = 0;
    return 1;
}
static inline int
agnic_mac_valid(const uint8_t *mac)
{
    return !(mac[0] & 1) && (mac[0] | mac[1] | mac[2] | mac[3] | mac[4] | mac[5]);
}
/* Allocate the last byte to physical port numbers; base is a /40 local prefix. */
static inline void
agnic_port_mac(const uint8_t *base, unsigned port, uint8_t *mac)
{
    unsigned i;
    for (i = 0; i < 5; i++) mac[i] = base[i];
    mac[0] = (mac[0] | 2) & 0xfe;
    mac[5] = (uint8_t)port;
}
#endif
