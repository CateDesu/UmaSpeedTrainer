# Build the speedhack DLL and the GUI EXE that carries it.
#
# Cross compile from Linux:
#   sudo pacman -S mingw-w64-gcc        (Arch / CachyOS)
#   sudo apt install gcc-mingw-w64      (Debian / Ubuntu)
# Or on Windows via MSYS2:
#   pacman -S mingw-w64-x86_64-gcc make
#
# Then just:  make

# Allow the toolchain prefix to be overridden so MSYS2 (where gcc is already
# the mingw gcc) can build with plain `make CC=gcc WINDRES=windres`.
CC      ?= x86_64-w64-mingw32-gcc
WINDRES ?= x86_64-w64-mingw32-windres

CFLAGS      := -O2 -Wall -Wextra
LDFLAGS_DLL := -shared -static-libgcc \
               -Wl,--out-implib,uma_hook.lib -lpsapi
LDFLAGS_EXE := -static-libgcc -mwindows -lpsapi -lcomctl32 -lm

all: uma_speed_trainer.exe uma_hook.dll

uma_hook.dll: uma_hook_win.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS_DLL)

resources.o: resources.rc uma_hook.dll
	$(WINDRES) resources.rc -o resources.o

uma_speed_trainer.exe: uma_speed_trainer.c resources.o
	$(CC) $(CFLAGS) -o $@ uma_speed_trainer.c resources.o $(LDFLAGS_EXE)

clean:
	rm -f *.dll *.lib *.exe *.o

.PHONY: all clean
