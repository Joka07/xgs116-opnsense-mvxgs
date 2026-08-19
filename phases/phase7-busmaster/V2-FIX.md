# Phase 7 v2 build fix

Two source-generation mistakes in v1 prevented compilation:

1. The attach `device_printf()` still used the Phase 6 format string while
   passing the additional PCI command argument.
2. A newline was accidentally embedded inside the detach `device_printf()`
   string literal.

v2 fixes only those compiler issues. The Phase 7 hardware logic is unchanged.
