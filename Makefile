CFLAGS  := -O2 -fPIC -Wall -Wextra
LDFLAGS := -shared -ldl -lpthread -lrt

# Default builds 64-bit only. Add `make all32` for the 32-bit companion
# in case some 32-bit Wine helper process needs hooking too.

all: libuma_hook.so

libuma_hook.so: libuma_hook.c
	gcc $(CFLAGS) -o $@ $< $(LDFLAGS)

libuma_hook32.so: libuma_hook.c
	gcc -m32 $(CFLAGS) -o $@ $< $(LDFLAGS)

all32: libuma_hook.so libuma_hook32.so

clean:
	rm -f libuma_hook.so libuma_hook32.so

.PHONY: all all32 clean
