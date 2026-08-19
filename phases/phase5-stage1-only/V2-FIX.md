# V2 compile fix

The first offline build reached the compiler successfully but failed on:

`fatal error: 'sys/atomic.h' file not found`

FreeBSD's atomic(9) interface is included through:

`#include <machine/atomic.h>`

V2 changes only that include. No NPU protocol/MMIO write path was added.
