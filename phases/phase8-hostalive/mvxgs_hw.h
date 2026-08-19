/*-
 * SPDX-License-Identifier: BSD-2-Clause
 *
 * Behavioural definitions recovered by black-box observation and static
 * analysis of a Sophos XGS 116 running SFOS 19.5.4 MR-4.
 * No vendor binary code is included.
 */
#ifndef _MVXGS_HW_H_
#define _MVXGS_HW_H_

#include <sys/types.h>

#define MVXGS_VENDOR_ID                  0x11ab
#define MVXGS_DEVICE_ID_PF               0x7080
#define MVXGS_DEVICE_ID_VF               0x7081

#define MVXGS_BAR0                       0
#define MVXGS_BAR2                       2
#define MVXGS_BAR4                       4
#define MVXGS_NBARS                      3

#define MVXGS_BAR0_WINDOW_SIZE           0x00014000u
#define MVXGS_BAR2_WINDOW_SIZE           0x00103000u
#define MVXGS_BAR2_WINDOW_BASE_FROM_END  0x00104000u
#define MVXGS_BARMAP_FROM_WINDOW         0x00102000u
#define MVXGS_BARMAP_FROM_BAR_END        0x00002000u

#define MVXGS_BARMAP_VERSION             5u
#define MVXGS_TARGET_COOKIE              0xd0fac10du
#define MVXGS_CTRL_COOKIE                0xafacafacu
#define MVXGS_PCINET_TARGET_PATTERN      0xaa55aa55u
#define MVXGS_PCINET_HOST_PATTERN        0xbb66bb66u
#define MVXGS_NWA_HOST_MAGIC             0xcafebabeu

#define MVXGS_FACILITY_COUNT             5
#define MVXGS_FAC_CTRL                   0
#define MVXGS_FAC_MVMGMT                 1
#define MVXGS_FAC_NWA                    2
#define MVXGS_FAC_RPC                    3
#define MVXGS_FAC_GIU                    4

/* CTRL flags recovered from mv_armada_drv behaviour. */
#define MVXGS_CTRL_F_TARGET_READY        0x00000001u
#define MVXGS_CTRL_F_HOST_READY          0x00000002u
/* Vendor name unknown: the H2T worker gates on this target-set bit. */
#define MVXGS_CTRL_F_TARGET_H2T_READY    0x00000004u
#define MVXGS_CTRL_F_HOST_ALIVE          0x00000008u
#define MVXGS_CTRL_KNOWN_MASK            0x0000000fu

#define MVXGS_T2H_MSIX_COUNT             5
#define MVXGS_H2T_DBELL_COUNT            5
#define MVXGS_CTRL_H2T_DESC_BASE         0x10u
#define MVXGS_CTRL_H2T_DESC_STRIDE       0x10u

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
