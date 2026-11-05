#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname -m)" != x86_64 || "$(getconf GNU_LIBC_VERSION)" != 'glibc 2.31' ]]; then
    echo 'Build in packaging/Dockerfile.linux to preserve the glibc 2.31 baseline.' >&2
    exit 1
fi
export PYTHONHASHSEED=0
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-0}"
export PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-cache"
mkdir -p build/linux/lib64 dist
gcc -O2 -fPIC -Wall -Wextra -shared -o build/linux/lib64/libuma_hook.so \
    libuma_hook.c -ldl -lpthread -lrt

# Include rebuild inputs and dependency notices in the executable.
rm -rf build/linux/source build/linux/licenses
mkdir -p build/linux/source/packaging
mkdir -p build/linux/source/tests build/linux/licenses
cp gui.py libuma_hook.c launch.sh launcher.py runtime.py runtime_paths.h setspeed.sh watch.sh umagui Makefile \
    uma-hook.desktop.in LICENSE README.md .dockerignore build/linux/source/
cp packaging/linux_entry.py packaging/launch_environment.py \
    packaging/linux-requirements.txt packaging/Dockerfile.linux \
    packaging/build-linux.sh packaging/THIRD_PARTY.md build/linux/source/packaging/
mkdir -p build/linux/source/packaging/hooks
cp packaging/hooks/*.py build/linux/source/packaging/hooks/
cp tests/*.py tests/*.c build/linux/source/tests/
dpkg-query -W > build/linux/source/debian-packages.txt
for copyright in /usr/share/doc/*/copyright; do
    cp -L "$copyright" "build/linux/licenses/$(basename "$(dirname "$copyright")").copyright"
done
cp /usr/share/common-licenses/{GPL-2,GPL-3,LGPL-2,LGPL-2.1,LGPL-3,Apache-2.0} build/linux/licenses/
cp -R build/linux/licenses build/linux/source/
tar --sort=name --mtime="@${SOURCE_DATE_EPOCH}" --owner=0 --group=0 --numeric-owner \
    -czf dist/UmaSpeedTrainer-linux-source.tar.gz -C build/linux/source .
python3 -m PyInstaller --noconfirm --clean --onefile --noupx \
    --name UmaSpeedTrainer-linux-x86_64 --paths "$PWD" \
    --additional-hooks-dir "$PWD/packaging/hooks" \
    --runtime-hook "$PWD/packaging/launch_environment.py" \
    --distpath dist --workpath build/linux/pyinstaller --specpath build/linux \
    --add-data "$PWD/build/linux/lib64/libuma_hook.so:lib64" \
    --add-data "$PWD/build/linux/source:source" \
    --copy-metadata PyQt6 --copy-metadata PyQt6-Qt6 --copy-metadata PyQt6-sip \
    packaging/linux_entry.py

make test
xvfb-run -a python3 tests/linux_package_probe.py dist/UmaSpeedTrainer-linux-x86_64
xvfb-run -a python3 tests/gui_probe.py
printf '\nBuilt %s/dist/UmaSpeedTrainer-linux-x86_64\n' "$PWD"
