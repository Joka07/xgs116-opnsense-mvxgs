/*-
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Behavioural definitions recovered from a Sophos XGS 116 running
 * SFOS 19.5.4 MR-4.  No vendor binary code is included in this file.
 */
#ifndef _MVXGS_HW_H_
#define _MVXGS_HW_H_

#include <sys/types.h>

#define MVXGS_VENDOR_ID                  0x11ab
#define MVXGS_DEVICE_ID_PF               0x7080
#define MVXGS_DEVICE_ID_VF               0x7081

/* PF BARs used by Sophos' armada_pci driver. */
#define MVXGS_BAR0                       0
#define MVXGS_BAR2                       2
#define MVXGS_BAR4                       4
#define MVXGS_NBARS                      3

/*
 * The Linux driver maps these logical windows, not necessarily each full BAR.
 * On the XGS 116 sample BAR2 is 16 MiB, so the BAR2 window starts at 0xEFC000.
 */
#define MVXGS_BAR0_WINDOW_SIZE           0x00014000u
#define MVXGS_BAR2_WINDOW_SIZE           0x00103000u
/* The SFOS driver maps BAR2 starting 0x104000 bytes before the full BAR end. */
#define MVXGS_BAR2_WINDOW_BASE_FROM_END  0x00104000u
#define MVXGS_BARMAP_FROM_WINDOW         0x00102000u
#define MVXGS_BARMAP_FROM_BAR_END        0x00002000u

#define MVXGS_BARMAP_VERSION             5u
#define MVXGS_TARGET_COOKIE               0xd0fac10du
#define MVXGS_CTRL_COOKIE                 0xafacafacu
#define MVXGS_PCINET_TARGET_PATTERN       0xaa55aa55u
#define MVXGS_PCINET_HOST_PATTERN         0xbb66bb66u

#define MVXGS_FACILITY_COUNT             5

#define MVXGS_FAC_CTRL                   0
#define MVXGS_FAC_MVMGMT                 1
#define MVXGS_FAC_NWA                    2
#define MVXGS_FAC_RPC                    3
#define MVXGS_FAC_GIU                    4

/* ctrl flags observed in mv_armada_drv. */
#define MVXGS_CTRL_F_TARGET_READY         0x00000001u
#define MVXGS_CTRL_F_HOST_READY           0x00000002u
#define MVXGS_CTRL_F_HOST_ALIVE           0x00000008u

/*
 * Target BAR map layout recovered from mv_armada_drv::mv_facility_conf_init().
 * The header is 8 bytes followed by five 16-byte records.
 */
/*
 * bar is a target logical window index: 0 -> PF BAR0, 1 -> PF BAR2,
 * 2 -> PF BAR4.  It is not the raw PCI BAR number.
 */
struct mvxgs_barmap_entry {
        uint32_t bar;
        uint32_t facility_id;
        uint32_t offset;
        uint32_t size;
};

struct mvxgs_barmap {
        uint32_t version;
        uint32_t target_cookie;
        struct mvxgs_barmap_entry facility[MVXGS_FACILITY_COUNT];
};

#endif /* _MVXGS_HW_H_ */
