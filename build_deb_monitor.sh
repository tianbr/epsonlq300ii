#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 LQ300II driver contributors
# Builds epsonlq300+ii-monitor_<version>_all.deb (status monitor) from the sources.
set -e
cd "$(dirname "$0")"
PKG="epsonlq300+ii-monitor"
VER="${1:-1.2}"
# Maintainer field of the package; override with MAINTAINER="Name <address>"
MAINTAINER="${MAINTAINER:-LQ300II driver contributors <noreply@invalid>}"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT

python3 -m py_compile lq300_monitor.py
install -d "$ROOT/usr/bin" "$ROOT/etc/xdg/autostart" "$ROOT/usr/share/applications" \
           "$ROOT/usr/share/doc/$PKG" "$ROOT/DEBIAN"
install -m 755 lq300_monitor.py "$ROOT/usr/bin/lq300-monitor"
cat > "$ROOT/etc/xdg/autostart/lq300-monitor.desktop" <<C
[Desktop Entry]
Type=Application
Name=Epson LQ-300+II Print Status
Name[de]=Epson LQ-300+II Druckstatus
Comment=Shows progress and remaining time while printing
Comment[de]=Zeigt Fortschritt und Restzeit beim Drucken
Exec=/usr/bin/lq300-monitor
Icon=printer
Terminal=false
C
cat > "$ROOT/usr/share/applications/lq300-monitor.desktop" <<C
[Desktop Entry]
Type=Application
Name=Epson LQ-300+II Print Status
Name[de]=Epson LQ-300+II Druckstatus
Comment=Print progress, remaining time and queue
Comment[de]=Druckfortschritt, Restzeit und Warteschlange
Exec=/usr/bin/lq300-monitor --show
Icon=printer
Terminal=false
Categories=Utility;System;
Actions=Settings;

[Desktop Action Settings]
Name=Settings
Name[de]=Einstellungen
Exec=/usr/bin/lq300-monitor --settings
C
chmod 644 "$ROOT/etc/xdg/autostart/lq300-monitor.desktop" "$ROOT/usr/share/applications/lq300-monitor.desktop"
install -m 644 MONITOR.md "$ROOT/usr/share/doc/$PKG/"
install -m 644 LICENSE "$ROOT/usr/share/doc/$PKG/copyright"
chmod 755 "$ROOT"; chmod 644 "$ROOT/usr/share/doc/$PKG/copyright"
SIZE=$(du -sk "$ROOT/usr" "$ROOT/etc" | awk '{s+=$1} END {print s}')
cat > "$ROOT/DEBIAN/control" <<C
Package: $PKG
Version: $VER
Section: utils
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-gdkpixbuf-2.0, python3-cairo, python3-cups
Recommends: gir1.2-ayatanaappindicator3-0.1, gir1.2-notify-0.7
Suggests: epsonlq300+ii
Breaks: epsonlq300+ii (<< 2.1)
Replaces: epsonlq300+ii (<< 2.1)
Maintainer: $MAINTAINER
Description: Status monitor for the Epson LQ-300+II print jobs
 Small desktop program that shows a window with progress, pages and remaining
 time while a job prints on a CUPS queue of the Epson LQ-300+II. Pause for
 waiting jobs, reprint, queue view, job options, tray icon and notifications.
 Everything is configurable in a settings dialog; the autostart can be switched
 off there or by removing the package.
C
mkdir -p dist
fakeroot dpkg-deb --build "$ROOT" "dist/${PKG}_${VER}_all.deb" >/dev/null
echo "dist/${PKG}_${VER}_all.deb"
