# Linux bundle notices

The trainer's own source remains under the MIT license in LICENSE. The Linux
executable combines it with GPLv3 PyQt6 and is distributed under GPLv3, with
Qt under LGPLv3. The original MIT permission remains available for the trainer
source on its own. No dependency source is modified.

The executable contains the trainer source and build inputs in `source/`.
The same inputs and license texts are in `UmaSpeedTrainer-linux-source.tar.gz`
beside the executable in each release.
Use `pyi-archive_viewer` from the pinned PyInstaller version to extract them,
or download the source for the same release tag from GitHub. The build recipe
is `packaging/Dockerfile.linux` and `packaging/build-linux.sh`.

Dependency licenses are included in the Python package metadata. License texts
and the exact upstream source releases are also available here:

* PyQt6 6.9.1, GPLv3:
  https://pypi.org/project/PyQt6/6.9.1/#files
* PyQt6-sip 13.10.2, BSD:
  https://pypi.org/project/PyQt6-sip/13.10.2/#files
* Qt 6.9.2, LGPLv3 and third party notices in the source archive:
  https://download.qt.io/archive/qt/6.9/6.9.2/single/qt-everywhere-src-6.9.2.tar.xz
* Python 3.9, PSF and included third party licenses:
  https://www.python.org/downloads/source/
* PyInstaller 6.22.3, GPLv2 with the bootloader distribution exception:
  https://pypi.org/project/pyinstaller/6.22.3/#files

System support libraries bundled by PyInstaller come from Debian 11.
Their copyright notices are in `source/licenses/`, and matching source
packages can be obtained from https://sources.debian.org/ . Exact package
versions are in `source/debian-packages.txt`. Graphics drivers, glibc and
other excluded system libraries remain supplied by the operating system.
