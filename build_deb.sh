#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 LQ300II driver contributors
# Builds epsonlq300+ii_<version>_<arch>.deb (driver: filters + PPD) from the sources.
# The status monitor is a separate package (build_deb_monitor.sh).
set -e
cd "$(dirname "$0")"
PKG="epsonlq300+ii"
VER="${1:-2.3}"
# Maintainer field of the package; override with MAINTAINER="Name <address>"
MAINTAINER="${MAINTAINER:-LQ300II driver contributors <noreply@invalid>}"
ARCH="$(dpkg --print-architecture)"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

make -s clean all
install -d "$ROOT/usr/lib/cups/filter" "$ROOT/usr/share/cups/model" \
           "$ROOT/usr/share/doc/$PKG" "$ROOT/DEBIAN"
install -m 755 rastertoescplq texttoescplq "$ROOT/usr/lib/cups/filter/"
strip --strip-unneeded "$ROOT/usr/lib/cups/filter/rastertoescplq" "$ROOT/usr/lib/cups/filter/texttoescplq"
install -m 644 lq300ii.ppd "$ROOT/usr/share/cups/model/"
install -m 644 README.md INSTALLATION.md "$ROOT/usr/share/doc/$PKG/"
install -m 644 LICENSE "$ROOT/usr/share/doc/$PKG/copyright"
chmod 755 "$ROOT"; chmod 644 "$ROOT/usr/share/doc/$PKG/copyright"
cat > "$ROOT/DEBIAN/postinst" <<'C'
#!/bin/sh
set -e
systemctl try-restart cups >/dev/null 2>&1 || true
exit 0
C
chmod 755 "$ROOT/DEBIAN/postinst"
SIZE=$(du -sk "$ROOT/usr" | cut -f1)
cat > "$ROOT/DEBIAN/control" <<C
Package: $PKG
Version: $VER
Section: utils
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Depends: cups, libc6 (>= 2.34)
Suggests: epsonlq300+ii-monitor
Conflicts: epson-lq300+ii-mono, epson-lq300+ii-color
Replaces: epson-lq300+ii-mono, epson-lq300+ii-color
Maintainer: $MAINTAINER
Description: CUPS driver for the Epson LQ-300+II dot matrix printer
 One driver (PPD "EpsonLQ300+ii") for the 24-pin ESC/P2 printer, with and
 without the optional colour ribbon: a graphics filter (120 to 360 dpi,
 dithering, bidirectional printing, bar codes and QR codes, colour via the
 ColorModel option) and a native text filter with the printer's own fonts and
 character sets. Cut sheets and tractor paper (A4, 210 mm x 12").
 The filters report progress (page, percent) to CUPS. The optional package
 epsonlq300+ii-monitor shows it in a window while a job is printing.
 After installing, add the printer with lpadmin or the CUPS web interface and
 pick "EpsonLQ300+ii".
C
mkdir -p dist
fakeroot dpkg-deb --build "$ROOT" "dist/${PKG}_${VER}_${ARCH}.deb" >/dev/null
echo "dist/${PKG}_${VER}_${ARCH}.deb"
