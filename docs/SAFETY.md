# Safety rules for hardware testing

1. Keep the serial console open during active experiments.
2. Never write raw `/dev/mem` values by hand unless a later documented phase explicitly requires it.
3. Collectors are read-only unless clearly marked otherwise.
4. Only use the gated sysctl transitions in the current phase source.
5. Do not repeat HOST_READY or HOST_ALIVE writes after an error/timeout.
6. After an active protocol write, use reboot as the reset path; do not `kldunload` the experimental module.
7. Never write to the internal Sophos SSD just to collect diagnostics.
8. Keep proprietary Sophos/Marvell binary modules out of the public repository.
9. Do not assume a driver phase creates usable Ethernet; current work is still control-plane reverse engineering.
