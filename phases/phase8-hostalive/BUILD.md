# Build notes

The module must be compiled against a kernel/source tree matching the OPNsense system that will load it.

The simple module Makefile is:

```make
KMOD=   mvxgs
SRCS=   mvxgs.c device_if.h bus_if.h pci_if.h
.include <bsd.kmod.mk>
```

On a suitable FreeBSD/OPNsense build host with the matching source tree available, enter this directory and run:

```sh
make clean
make
```

Do not copy a `.ko` built for a different FreeBSD kernel ABI onto the firewall merely because the version looks close.
