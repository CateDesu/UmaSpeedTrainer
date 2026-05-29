# Cross compile from Linux. Install mingw-w64 first:
#   sudo pacman -S mingw-w64-gcc        (Arch / CachyOS)
#   sudo apt install gcc-mingw-w64      (Debian / Ubuntu)
#
# Or build on Windows with MSYS2 / MinGW.

CC      := x86_64-w64-mingw32-gcc
CFLAGS  := -O2 -Wall -Wextra
LDFLAGS := -shared -static-libgcc -Wl,--out-implib,uma_hook.lib -lpsapi

all: uma_hook.dll

uma_hook.dll: uma_hook_win.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f uma_hook.dll uma_hook.lib

.PHONY: all clean
