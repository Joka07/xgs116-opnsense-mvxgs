/* SPDX-License-Identifier: GPL-2.0-or-later
 * Derived from Mamoru's MIT tag_dsa.h (Copyright 2026 The Mamoru Project).
 * Tagged/CFI wire conversion follows Linux v6.12 net/dsa/tag_dsa.c,
 * Copyright (c) 2008-2009 Marvell Semiconductor (GPL-2.0+).
 * XGS116 integration: preserve VLANs, validate source attribution and lengths.
 */
#ifndef DP_TAG_DSA_H
#define DP_TAG_DSA_H
#include <string.h>
#include <stdint.h>
#include "pport_hdr.h"
#include "portmap.h"
#include "dp_config.h"
#ifndef DP_DSA_DEV
#error "DP_DSA_DEV must be selected from the appliance switch observation (0..31)"
#endif
#if DP_DSA_DEV < 0 || DP_DSA_DEV > 31
#error "DP_DSA_DEV outside DSA device field"
#endif
#define DSA_LEN 4
#define ETH_MAC_LEN 12
#define ETH_HEADER_LEN 14
#define DSA_CMD_TO_CPU 0
#define DSA_CMD_FROM_CPU 1
#define DSA_CMD_TO_SNIFFER 2
#define DSA_CMD_FORWARD 3
static inline uint8_t dsa_src_port(const uint8_t *t) { return (t[1] >> 3) & 31; }
static inline uint8_t dsa_cmd(const uint8_t *t) { return t[0] >> 6; }
static inline void dsa_build_from_cpu(uint8_t *t, uint8_t port)
{
	t[0] = (DSA_CMD_FROM_CPU << 6) | DP_DSA_DEV;
	t[1] = port << 3;
	t[2] = t[3] = 0;
}
/* No allocation: caller owns len bytes and the declared headroom. FCS is absent.
 * VLAN tagged DSA uses the existing 802.1Q tag; untagged DSA inserts four bytes.
 * 802.1ad stays inside an untagged DSA envelope; no offload is claimed for it. */
static inline int dp_h2t_transform(uint8_t *frame, uint16_t len,
    uint8_t **out, uint16_t *out_len)
{
	uint8_t *eth, *tag;
	int idx;
	if (len < PPORT_PREFIX + ETH_HEADER_LEN || len > DP_GIU_FRAME) return -1;
	if (frame[1] != 0) return -2;
	idx = dp_phys_to_index(PPORT_TAG_TO_PHYS(frame[0]));
	if (idx < 0) return -2;
	eth = frame + PPORT_PREFIX;
	if (eth[12] == 0x81 && eth[13] == 0x00) {
		if (len < PPORT_PREFIX + ETH_HEADER_LEN + DSA_LEN) return -1;
		tag = eth + ETH_MAC_LEN;
		tag[0] = (DSA_CMD_FROM_CPU << 6) | 0x20 | DP_DSA_DEV;
		tag[1] = dp_ports[idx].dsa_port << 3;
		if (tag[2] & 0x10) { tag[1] |= 1; tag[2] &= ~0x10; }
		*out = eth;
		*out_len = len - PPORT_PREFIX;
	} else {
		memmove(eth - DSA_LEN, eth, ETH_MAC_LEN);
		dsa_build_from_cpu(eth - DSA_LEN + ETH_MAC_LEN, dp_ports[idx].dsa_port);
		*out = eth - DSA_LEN;
		*out_len = len - PPORT_PREFIX + DSA_LEN;
	}
	return 0;
}
static inline int dp_t2h_transform(uint8_t *frame, uint16_t len,
    uint16_t headroom, const struct agnic_pport_md *md_src,
    uint8_t **out, uint16_t *out_len)
{
	uint8_t *tag, *eth, *pfx, cmd, tagged;
	uint16_t eth_len, need;
	int idx;
	struct agnic_pport_md *md;
	(void)md_src;
	if (len < ETH_HEADER_LEN + DSA_LEN) return -1;
	tag = frame + ETH_MAC_LEN;
	cmd = dsa_cmd(tag);
	/* Only a single switch, no aggregation/remote-register replies/mirrors.
	 * A malformed device or direction must never inject into another port. */
	if ((tag[0] & 31) != DP_DSA_DEV) return -5;
	if (cmd != DSA_CMD_FORWARD && cmd != DSA_CMD_TO_CPU) return -5;
	if (cmd == DSA_CMD_FORWARD && (tag[1] & 4)) return -5;
	if (cmd == DSA_CMD_TO_CPU) {
		uint8_t reason = (tag[1] & 6) | ((tag[2] >> 4) & 1);
		if (reason != 0 && reason != 2 && reason != 3) return -5;
	}
	idx = dp_dsa_to_index(dsa_src_port(tag));
	if (idx < 0) return -4;
	tagged = tag[0] & 0x20;
	need = tagged ? PPORT_PREFIX : PPORT_PREFIX - DSA_LEN;
	if (headroom < need) return -3;
	eth_len = tagged ? len : len - DSA_LEN;
	if (eth_len > DP_GIU_FRAME - PPORT_PREFIX) return -1;
	if (tagged) {
		uint8_t tci_high = (tag[2] & ~0x10) | ((tag[1] & 1) ? 0x10 : 0);
		tag[0] = 0x81; tag[1] = 0x00; tag[2] = tci_high;
		eth = frame;
	} else {
		memmove(frame + DSA_LEN, frame, ETH_MAC_LEN);
		eth = frame + DSA_LEN;
	}
	pfx = eth - PPORT_PREFIX;
	pfx[0] = dp_ports[idx].tag0; pfx[1] = 0;
	md = (struct agnic_pport_md *)(pfx + PPORT_TAG_LEN);
	memset(md, 0, sizeof(*md));
	md->md_magic = AGNIC_MD_MAGIC; md->md_version = AGNIC_MD_VERSION;
	md->md_dir_flags = MD_DIR_T2H; md->src_port = dp_ports[idx].physport;
	md->orig_l2_len = eth_len;
	*out = pfx; *out_len = PPORT_PREFIX + eth_len;
	return 0;
}
#endif
