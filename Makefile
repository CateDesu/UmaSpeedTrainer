CFLAGS  := -O2 -fPIC -Wall -Wextra
LDFLAGS := -shared -ldl -lpthread -lrt

# Resolve the repo's own absolute location (works from `cd repo && make`
# or `make -C repo`). Used to generate the .desktop and print the Steam line.
REPO_DIR    := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
DESKTOP_DIR := $(HOME)/.local/share/applications

# The game runs 64-bit under Proton, so the 64-bit hook is what matters and
# is built by default into lib64/ (where launch.sh preloads it from). The
# 32-bit companion in lib/ is optional, for 32-bit Wine helper processes;
# build both with `make all32`. launch.sh preloads whichever exist and ld.so
# silently skips the wrong-class one.

all: lib64/libuma_hook.so

lib64/libuma_hook.so: libuma_hook.c
	@mkdir -p lib64
	gcc $(CFLAGS) -o $@ $< $(LDFLAGS)

lib/libuma_hook.so: libuma_hook.c
	@mkdir -p lib
	gcc -m32 $(CFLAGS) -o $@ $< $(LDFLAGS)

all32: lib64/libuma_hook.so lib/libuma_hook.so

# Build the hook and install the app-menu launcher with this repo's real
# path baked in, then print the one line the user must paste into Steam.
install: all
	@mkdir -p "$(DESKTOP_DIR)"
	@sed "s|@EXEC@|$(REPO_DIR)/umagui|" uma-hook.desktop.in > "$(DESKTOP_DIR)/uma-hook.desktop"
	@echo ""
	@echo "Built the 64-bit hook and installed the app-menu launcher:"
	@echo "  $(DESKTOP_DIR)/uma-hook.desktop"
	@echo ""
	@echo "Final step -- paste this into Steam (right click Umamusume:"
	@echo "Pretty Derby -> Properties -> Launch Options):"
	@echo ""
	@echo "    $(REPO_DIR)/launch.sh %command%"
	@echo ""

clean:
	rm -f lib64/libuma_hook.so lib/libuma_hook.so

.PHONY: all all32 install clean
