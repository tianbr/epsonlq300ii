#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 LQ300II driver contributors
"""Status monitor for the Epson LQ-300+II.

Runs in the background (optionally with a tray icon) and shows a window with
progress and remaining time as soon as a job runs on an LQ-300 queue. It reads
what CUPS knows about the job (IPP). The printer itself reports nothing back
over a send-only connection (LPT, print server).

  lq300-monitor                       start the service (or activate the running one)
  lq300-monitor --show                show the window
  lq300-monitor --settings            open the settings
  lq300-monitor --quit                quit the running monitor
  lq300-monitor --demo                window with a simulated job
  lq300-monitor --printers A,B        only these queues (default: all queues with
                                      "LQ-300" or "LQ300" in the model name)
  lq300-monitor --install-autostart / --remove-autostart
"""
import argparse
import json
import math
import os
import re
import shutil
import sys
import time

# ---------- Translations ----------
# The source strings are English. To add a language, add a dictionary to
# TRANSLATIONS (key: language code, value: {English text: translation}).
# The language comes from LANGUAGE, LC_ALL, LC_MESSAGES or LANG.
TRANSLATIONS = {
    "de": {
        "Epson LQ-300+II Print Status": "Epson LQ-300+II Druckstatus",
        "No.": "Nr.",
        "Document": "Dokument",
        "User": "Benutzer",
        "Color mode": "Farbmodus",
        "Resolution": "Auflösung",
        "Paper size": "Papierformat",
        "Paper source": "Papierquelle",
        "Halftoning": "Rasterung",
        "Density": "Dichte",
        "Print direction": "Druckrichtung",
        "Print intensity": "Druckintensität",
        "Fast printing": "Schnelldruck",
        "Character set": "Zeichensatz",
        "Text quality": "Textqualität",
        "waiting": "wartet",
        "on hold": "angehalten",
        "printing": "wird gedruckt",
        "stopped": "gestoppt",
        "canceled": "abgebrochen",
        "error": "Fehler",
        "done": "fertig",
        "in the queue": "in der Warteschlange",
        "receiving data": "Daten werden empfangen",
        "finishing": "wird beendet",
        "completed successfully": "erfolgreich beendet",
        "canceled by user": "vom Benutzer abgebrochen",
        "aborted by system": "vom System abgebrochen",
        "printer stopped": "Drucker gestoppt",
        "printer not ready": "Drucker nicht bereit",
        "connecting to the printer": "verbindet mit dem Drucker",
        "printer unreachable": "Drucker nicht erreichbar",
        "out of paper": "Papier leer",
        "paper jam": "Papierstau",
        "Job %s": "Auftrag %s",
        "Holds waiting and newly arriving jobs. The running job prints to the end: CUPS cannot interrupt it cleanly, holding it would cancel it and restart it from the beginning later.": "Hält wartende und neu eintreffende Aufträge an. Der laufende Auftrag druckt zu Ende: CUPS kann ihn nicht sauber unterbrechen, ein Anhalten würde ihn abbrechen und später von vorn beginnen.",
        "Prints the finished job again (CUPS keeps the data only for a limited time).": "Druckt den beendeten Auftrag noch einmal (CUPS bewahrt die Daten nur begrenzt auf).",
        "Close": "Schließen",
        "Window": "Fenster",
        "Show the window automatically for print jobs": "Fenster bei Druckaufträgen automatisch anzeigen",
        "Off: only the tray icon shows printing; open the window from there.": "Aus: nur das Symbol im Infobereich zeigt den Druck, das Fenster öffnet man von dort.",
        "Bring the window to the front automatically": "Fenster automatisch in den Vordergrund holen",
        "Depends on the window manager; some prevent raising windows.": "Hängt vom Fenstermanager ab; manche verhindern das Holen in den Vordergrund.",
        "Keep the window always on top": "Fenster immer im Vordergrund halten",
        "Takes effect after restarting the monitor. Under Wayland the monitor uses XWayland for this.": "Wirkt nach einem Neustart des Monitors. Unter Wayland läuft der Monitor dafür über XWayland.",
        "Tray": "Infobereich",
        "Show print status as a tray icon": "Druckstatus als Symbol im Infobereich anzeigen",
        "Notifications": "Mitteilungen",
        "Notify when a print is finished": "Mitteilung, wenn ein Druck fertig ist",
        "Notify on print errors": "Mitteilung bei Druckfehlern",
        "Startup and queues": "Start und Warteschlangen",
        "Queue names, comma-separated. Takes effect after a restart.": "Queue-Namen, durch Komma getrennt. Wirkt nach Neustart.",
        "ready": "bereit",
        "Job print options": "Druckoptionen des Auftrags",
        "Queue": "Warteschlange",
        "Cancel selected": "Auswahl abbrechen",
        "Hold / release selected": "Auswahl anhalten / freigeben",
        "History": "Verlauf",
        "Print again": "Erneut drucken",
        "Cancel job": "Auftrag abbrechen",
        "Settings …": "Einstellungen …",
        "Hide": "Ausblenden",
        "Ready": "Bereit",
        "Show window": "Fenster anzeigen",
        "Print last job again": "Letzten Auftrag erneut drucken",
        "Pause (hold waiting jobs)": "Pause (wartende Aufträge anhalten)",
        "Quit monitor": "Monitor beenden",
        "Print error": "Druckfehler",
        "Resume (release held jobs)": "Fortsetzen (angehaltene freigeben)",
        "Not available: install gir1.2-ayatanaappindicator3-0.1.": "Nicht verfügbar: gir1.2-ayatanaappindicator3-0.1 installieren.",
        "Start the monitor at login": "Monitor beim Anmelden starten",
        "Quit the monitor now": "Monitor jetzt beenden",
        "Pause: waiting jobs are being held": "Pause: wartende Aufträge werden angehalten",
        "Job %d: printed again": "Job %d: erneut gedruckt",
        "Job %d: %s, page %d done, %d%% of the page%s": "Job %d: %s, Seite %d fertig, %d%% der Seite%s",
        "%s · %d page(s) · %s": "%s · %d Seite(n) · %s",
        "Print finished": "Druck fertig",
        "Queue (%d)": "Warteschlange (%d)",
        "Resume": "Fortsetzen",
        "No job active": "Kein Auftrag aktiv",
        "Monitored queues: %s": "Überwachte Queues: %s",
        "Queue %s · user %s · job %d": "Queue %s · Benutzer %s · Auftrag %d",
        "%d printed": "%d gedruckt",
        "%s KiB (job)": "%s KiB (Auftrag)",
        "Document format": "Dokumentformat",
        "Copies": "Kopien",
        "Settings – ": "Einstellungen – ",
        "Hide the window after a successful end after": "Fenster nach erfolgreichem Ende ausblenden nach",
        "seconds (0 = never)": "Sekunden (0 = nie)",
        "Not available: install gir1.2-notify-0.7.": "Nicht verfügbar: gir1.2-notify-0.7 installieren.",
        "Monitored queues (empty = all LQ-300):": "Überwachte Queues (leer = alle LQ-300):",
        "Demo: cancel of job %d": "Demo: Abbruch von Job %d",
        "Job %d: cancel requested": "Job %d: Abbruch angefordert",
        "Demo: job %d %s": "Demo: Job %d %s",
        "Pause ended: %d jobs released": "Pause beendet: %d Aufträge freigegeben",
        "Demo: print job %d again": "Demo: Job %d erneut drucken",
        "Only waiting or held jobs can be held or released. A running job would be canceled.": "Nur wartende oder angehaltene Aufträge lassen sich anhalten oder freigeben. Ein laufender Auftrag würde dabei abgebrochen.",
        "Job %d '%s' detected": "Job %d '%s' erkannt",
        "Pause: %d job(s) held, the running print continues.": "Pause: %d Auftrag/Aufträge angehalten, laufender Druck geht weiter.",
        " of %d": " von %d",
        "calculating …": "wird berechnet …",
        " (+%d waiting)": " (+%d wartend)",
        "Cancel failed: %s": "Abbruch fehlgeschlagen: %s",
        "Job %d: %s failed: %s": "Job %d: %s fehlgeschlagen: %s",
        "Print again failed: %s": "Erneut drucken fehlgeschlagen: %s",
        "Job %d cannot be printed again.\n\n%s\n\nCUPS keeps the data of finished jobs only for a limited time (PreserveJobFiles).": "Der Auftrag %d kann nicht erneut gedruckt werden.\n\n%s\n\nCUPS bewahrt die Daten beendeter Aufträge nur begrenzt auf (PreserveJobFiles).",
        "CUPS not reachable: %s": "CUPS nicht erreichbar: %s",
        "Notification failed: %s": "Mitteilung fehlgeschlagen: %s",
        "+ %d more jobs waiting": "+ %d weitere Aufträge wartend",
        "running …": "läuft …",
        "Printing: %s": "Druckt: %s",
        "held": "angehalten",
        "released": "freigegeben",
        " (for this page)": " (für diese Seite)",
        "Holding": "Anhalten",
        "Releasing": "Freigeben",
        " of this page": " dieser Seite",
        "(default)": "(Standard)",
        "Page": "Seite",
        "Runtime": "Laufzeit",
        "Remaining (approx.)": "Restzeit (ca.)",
        "Data size": "Datenmenge",
        "Message": "Meldung",
    },
}


def ppd_translations(path, lang):
    """{(option, choice): text} from the "*<lang>.<option> <choice>/<text>" lines of a PPD."""
    out = {}
    if lang == "en":
        return out
    pat = re.compile(r'\*%s\.(\w+) ([^/\s]+)/(.*?):\s*""' % re.escape(lang))
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = pat.match(line)
                if m:
                    out[(m.group(1), m.group(2))] = m.group(3)
    except OSError:
        pass
    return out


def _detect_lang():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        for part in (os.environ.get(var) or "").split(":"):
            code = part.split(".")[0].split("@")[0].split("_")[0].lower()
            if code and code not in ("c", "posix"):
                return code
    return "en"


_TABLE = TRANSLATIONS.get(_detect_lang(), {})


def _(text):
    return _TABLE.get(text, text)


CONFIG_DIR = os.path.expanduser("~/.config/lq300-monitor")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
LOG_DIR = os.path.expanduser("~/.local/state/lq300-monitor")
USER_AUTOSTART = os.path.expanduser("~/.config/autostart/lq300-monitor.desktop")
SYS_AUTOSTART = "/etc/xdg/autostart/lq300-monitor.desktop"

DEFAULTS = {
    "show_window": True,      # show the window automatically for print jobs
    "raise_window": True,     # ... and bring it to the front
    "keep_above": False,      # keep the window always on top
    "tray": True,             # tray icon
    "hide_after": 8,          # seconds until hiding after the end (0 = never)
    "notify_done": True,      # notification at the end
    "notify_error": True,     # notification on error
    "printers": "",           # queues, empty = automatic
    "expand_queue": False,    # queue expanded
    "expand_options": False,  # print options expanded
}


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE) as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            json.dump(s, f, indent=1)
    except OSError:
        pass


SETTINGS = load_settings()
# Wayland has no "always on top"; it works through XWayland.
if SETTINGS["keep_above"] and os.environ.get("WAYLAND_DISPLAY") \
        and os.environ.get("DISPLAY") and "GDK_BACKEND" not in os.environ:
    os.environ["GDK_BACKEND"] = "x11"


def exe_path():
    return shutil.which("lq300-monitor") or os.path.abspath(sys.argv[0])


def autostart_enabled():
    try:
        with open(USER_AUTOSTART) as f:
            return not re.search(r"^Hidden=true", f.read(), re.M)
    except OSError:
        return os.path.exists(SYS_AUTOSTART)


def set_autostart(on):
    """A per-user autostart file with the same name overrides the system one
    (Hidden=true disables the start)."""
    os.makedirs(os.path.dirname(USER_AUTOSTART), exist_ok=True)
    with open(USER_AUTOSTART, "w") as f:
        f.write("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\n"
                "Icon=printer\nTerminal=false\n%s"
                % ("Epson LQ-300+II Print Status", exe_path(), "" if on else "Hidden=true\n"))


import cairo  # noqa: E402
import gi  # noqa: E402
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gio, GLib, GdkPixbuf, Gtk, Pango  # noqa: E402

try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify
except (ValueError, ImportError):
    Notify = None
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except (ValueError, ImportError):
    AppIndicator = None
try:
    import cups
except ImportError:
    cups = None

APP_NAME = _("Epson LQ-300+II Print Status")
APP_ID = "org.lq300.Monitor"
POLL_S = 1
OPT_KEYS = [("ColorModel", "Color mode"), ("Resolution", "Resolution"),
            ("PageSize", "Paper size"), ("InputSlot", "Paper source"),
            ("LQDither", "Halftoning"), ("LQDensity", "Density"),
            ("LQDirection", "Print direction"), ("LQOnePass", "Print intensity"),
            ("LQMerge", "Fast printing"), ("LQCharset", "Character set"),
            ("LQQuality", "Text quality")]

# Windows 95 wizard style: 80 x 140 pixel graphic on a teal background, 3/4 view
# with light from the upper left, scaled up by two
TEAL = (0, .5, .5)
BLACK, WHITE = (0, 0, 0), (1, 1, 1)
LIGHT, GRAY, MID, DARK = (.92, .92, .92), (.75, .75, .75), (.5, .5, .5), (.3, .3, .3)
NAVY, BLUE = (0, 0, .5), (.1, .1, .9)
CYAN, GREEN, LGREEN = (0, 1, 1), (0, .5, 0), (0, 1, 0)
RED, DRED, YELLOW, MAGENTA = (1, 0, 0), (.5, 0, 0), (1, 1, 0), (.8, 0, .8)
ANIM_W, ANIM_H, ANIM_SC, ANIM_MS = 80, 140, 2, 120
CABLE = [(57, 47), (60, 48), (63, 51), (64, 55), (63, 60), (61, 64),
         (59, 68), (58, 72), (58, 78), (58, 82)]


def _along(path, pos):
    """Point on the polyline at distance pos from its start."""
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        d = math.hypot(x1 - x0, y1 - y0)
        if pos <= d:
            f = pos / d
            return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        pos -= d
    return path[-1]


class Animation(Gtk.Image):
    """Computer, cable and printer in the style of the Windows 95 wizards.
    While printing, data dots travel along the cable, the printer shakes and
    pushes paper with blue text lines upwards."""

    def __init__(self):
        super().__init__()
        self.state = "print"      # print | wait | done | error
        self.tick = 0
        self.surface = cairo.ImageSurface(
            cairo.FORMAT_RGB24, ANIM_W * ANIM_SC, ANIM_H * ANIM_SC)
        self.render()

    def render(self):
        """Draws into a bitmap and shows it as a pixbuf (needs no draw signal,
        which python3-gi-cairo would require)."""
        self.cr = cr = cairo.Context(self.surface)
        cr.scale(ANIM_SC, ANIM_SC)
        self.paint()
        self.surface.flush()
        w, h = ANIM_W * ANIM_SC, ANIM_H * ANIM_SC
        bgra = bytes(self.surface.get_data())
        rgb = bytearray(w * h * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
        self.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(bytes(rgb)), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3))

    # ---------- Drawing helpers ----------
    def r(self, x, y, w, h, c):
        self.cr.set_source_rgb(*c)
        self.cr.rectangle(x, y, w, h)
        self.cr.fill()

    def poly(self, pts, fill, line=BLACK):
        cr = self.cr
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        cr.close_path()
        cr.set_source_rgb(*fill)
        cr.fill_preserve()
        if line:
            cr.set_source_rgb(*line)
            cr.set_line_width(1)
            cr.stroke()
        else:
            cr.new_path()

    def line(self, p, q, c, w=1):
        cr = self.cr
        cr.set_source_rgb(*c)
        cr.set_line_width(w)
        cr.move_to(*p)
        cr.line_to(*q)
        cr.stroke()

    # ---------- Scene ----------
    def paint(self):
        t, st = self.tick, self.state
        self.cr.set_antialias(cairo.ANTIALIAS_NONE)
        self.r(0, 0, ANIM_W, ANIM_H, TEAL)
        self.draw_computer(t, st)
        self.draw_cable(t, st == "print")
        self.draw_printer(t, st)
        self.draw_docs()
        if st == "wait":
            self.draw_hourglass(t)
        elif st == "done":
            self.draw_check()
        elif st == "error":
            self.draw_cross()

    def draw_computer(self, t, st):
        # case
        self.poly([(46, 46), (56, 40), (56, 50), (46, 56)], MID)
        self.poly([(10, 46), (46, 46), (46, 56), (10, 56)], GRAY)
        self.poly([(10, 46), (46, 46), (56, 40), (20, 40)], LIGHT)
        self.r(14, 50, 14, 1, DARK)
        self.r(14, 52, 14, 1, WHITE)
        self.r(38, 50, 2, 2, RED if st == "error" else LGREEN)
        # screen
        self.poly([(46, 8), (55, 2), (55, 32), (46, 40)], MID)
        self.poly([(12, 8), (46, 8), (46, 40), (12, 40)], GRAY)
        self.poly([(12, 8), (46, 8), (55, 2), (21, 2)], LIGHT)
        self.r(16, 12, 26, 24, DARK)
        self.r(17, 13, 24, 22, CYAN)
        self.r(41, 13, 1, 23, WHITE)
        self.r(17, 35, 25, 1, WHITE)
        self.icon(22, 18)
        self.icon(27 + ((t // 4) % 2 if st == "print" else 0), 22)
        self.r(40, 37, 2, 2, LGREEN)
        self.r(18, 40, 22, 3, MID)
        self.r(16, 43, 26, 1, DARK)

    def icon(self, x, y):
        self.r(x, y, 9, 8, BLACK)
        self.r(x + 1, y + 1, 7, 6, WHITE)
        self.r(x + 2, y + 2, 5, 1, NAVY)
        self.r(x + 2, y + 4, 3, 1, MID)

    def draw_cable(self, t, active):
        cr = self.cr
        cr.set_source_rgb(*NAVY)
        cr.set_line_width(3)
        cr.move_to(*CABLE[0])
        for p in CABLE[1:]:
            cr.line_to(*p)
        cr.stroke()
        cr.set_source_rgb(*BLUE)
        cr.set_line_width(2)
        cr.move_to(CABLE[0][0], CABLE[0][1] - .5)
        for p in CABLE[1:]:
            cr.line_to(p[0] - .5, p[1])
        cr.stroke()
        if active:
            total = sum(math.hypot(b[0] - a[0], b[1] - a[1])
                        for a, b in zip(CABLE, CABLE[1:]))
            for i in range(4):
                x, y = _along(CABLE, (t * 2 + i * total / 4) % total)
                self.r(int(x) - 1, int(y) - 1, 3, 3, YELLOW)

    def draw_printer(self, t, st):
        cr = self.cr
        cr.save()
        if st == "print" and t % 2:
            cr.translate(0, 1)                        # shaking
        self.poly([(52, 88), (64, 80), (64, 96), (52, 106)], MID)
        for i in range(4):
            self.line((55, 95 + 2 * i), (61, 91 + 2 * i), DARK)
        self.poly([(8, 88), (52, 88), (52, 106), (8, 106)], GRAY)
        self.r(9, 89, 42, 1, WHITE)
        self.poly([(8, 88), (52, 88), (64, 80), (20, 80)], LIGHT)
        self.r(18, 84, 30, 1, DARK)
        self.r(12, 93, 3, 2, LGREEN if st != "error" else DARK)
        blink = (t // 3) % 2 == 0
        self.r(17, 93, 3, 2, RED if st == "error" and blink else DRED)
        self.r(22, 93, 3, 2, YELLOW if st == "wait" and blink else DRED)
        self.r(12, 100, 36, 1, DARK)
        self.r(12, 101, 36, 1, WHITE)
        self.draw_paper(t if st == "print" else 0)
        cr.restore()

    def draw_paper(self, t):
        self.poly([(22, 84), (46, 84), (55, 66), (31, 66)], WHITE)
        for k in range(6):
            y = 83 - (t + k * 3) % 18
            if y < 68:
                continue
            left = 22 + (84 - y) * .5
            right = 46 + (84 - y) * .5
            xa, xb = int(left + 3), int(right - 3 - (k * 5) % 8)
            self.r(xa, y, xb - xa, 1, BLUE if k % 3 else MAGENTA)

    def draw_docs(self):
        self.poly([(8, 124), (30, 118), (40, 126), (18, 133)], WHITE)
        for f in (.3, .5, .7):
            x, y = 8 + 10 * f, 124 + 9 * f
            self.line((x + 3, y - .5), (x + 17, y - 4), BLUE if f != .5 else MAGENTA)
        self.poly([(28, 120), (46, 117), (52, 123), (34, 127)], WHITE)
        self.line((33, 121), (45, 119), CYAN)
        self.line((35, 123), (47, 121), MAGENTA)
        self.line((3, 134), (13, 126), (.9, .7, 0), 2)
        self.r(2, 134, 2, 2, BLACK)

    def draw_hourglass(self, t):
        cx, top = 66, 108
        self.r(cx - 5, top, 11, 2, BLACK)
        self.r(cx - 5, top + 18, 11, 2, BLACK)
        s = 7 - (t % 28) // 4
        for i in range(7):
            hw = 3 - i // 2
            y = top + 2 + i
            self.r(cx - hw - 1, y, 2 * hw + 3, 1, LIGHT)
            self.r(cx - hw - 1, y, 1, 1, BLACK)
            self.r(cx + hw + 1, y, 1, 1, BLACK)
            if 7 - i <= s:
                self.r(cx - hw, y, 2 * hw + 1, 1, YELLOW)
            hw2, y2 = i // 2, top + 11 + i
            self.r(cx - hw2 - 1, y2, 2 * hw2 + 3, 1, LIGHT)
            self.r(cx - hw2 - 1, y2, 1, 1, BLACK)
            self.r(cx + hw2 + 1, y2, 1, 1, BLACK)
            if i >= s:
                self.r(cx - hw2, y2, 2 * hw2 + 1, 1, YELLOW)
        if s > 0:
            self.r(cx, top + 9, 1, 2, YELLOW)

    def draw_check(self):
        for px, py in [(0, 5), (1, 6), (2, 7), (3, 6), (4, 5), (5, 4),
                       (6, 3), (7, 2), (8, 1), (9, 0)]:
            self.r(55 + px * 2 + 1, 116 + py * 2 + 1, 3, 3, DARK)
            self.r(55 + px * 2, 116 + py * 2, 3, 3, LGREEN)

    def draw_cross(self):
        for i in range(14):
            for x in (56 + i, 56 + 13 - i):
                self.r(x + 1, 113 + i + 1, 3, 3, DARK)
                self.r(x, 113 + i, 3, 3, RED)


JOB_ATTRS = ["job-id", "job-name", "document-name-supplied", "job-originating-user-name",
             "job-printer-uri", "job-state", "job-state-reasons",
             "job-media-progress", "job-media-sheets-completed",
             "job-impressions", "job-impressions-completed", "job-k-octets",
             "time-at-creation", "time-at-processing", "time-at-completed",
             "job-printer-state-message"]
STATE_NAMES = {3: "waiting", 4: "on hold", 5: "printing",
               6: "stopped", 7: "canceled", 8: "error",
               9: "done"}
ACTIVE = (3, 4, 5, 6)
REASONS = {
    "job-queued": "in the queue",
    "job-incoming": "receiving data",
    "processing-to-stop-point": "finishing",
    "job-printing": "printing",
    "job-completed-successfully": "completed successfully",
    "job-canceled-by-user": "canceled by user",
    "aborted-by-system": "aborted by system",
    "printer-stopped": "printer stopped",
    "resources-are-not-ready": "printer not ready",
    "connecting-to-device": "connecting to the printer",
    "offline-report": "printer unreachable",
    "media-empty": "out of paper",
    "media-jam": "paper jam",
    "none": "",
}


def state_name(state, default=None):
    name = STATE_NAMES.get(state)
    return _(name) if name else default


def jname(a):
    return a.get("job-name") or a.get("document-name-supplied") or _("Job %s") % a.get("job-id", "?")


def fmt_time(sec):
    sec = max(0, int(sec))
    return "%d:%02d" % divmod(sec, 60) if sec < 3600 else \
        "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def reasons_text(val):
    if isinstance(val, str):
        val = [val]
    parts = []
    for r in val or []:
        base = r.rsplit("-", 1)[0] if r.endswith(("-error", "-warning", "-report")) else r
        parts.append(_(REASONS[r]) if r in REASONS else _(REASONS.get(base, r)))
    return ", ".join(p for p in parts if p)


def page_total(job):
    """Page count of the job: from CUPS (job-impressions) or from the text
    filter's message "Page p of n"; 0 = unknown."""
    total = job.get("job-impressions") or 0
    if not total:
        mt = re.search(r"Page \d+ of (\d+)", job.get("job-printer-state-message") or "")
        total = int(mt.group(1)) if mt else 0
    return total


def estimate(job, now, page_start):
    """(fraction 0..1 or None, remaining time in s or None).

    The filters report the progress of the current page (0..100) in
    job-media-progress and count finished pages in job-media-sheets-completed.
    The page time follows from the time spent on this page so far. If the
    page count is unknown (graphics), fraction and remaining time apply to
    the current page only.
    """
    done = job.get("job-media-sheets-completed") or 0
    prog = job.get("job-media-progress") or 0
    total = page_total(job)
    f = prog / 100.0
    frac = min(1.0, (done + f) / total) if total > 0 else (f if prog > 0 else None)
    if prog < 3 or now <= page_start:
        return frac, None
    page_time = (now - page_start) / f
    eta = page_time * (1 - f)
    if total > done + 1:
        eta += page_time * (total - done - 1)
    return frac, eta


class Monitor:
    def __init__(self, app, printers, demo=False):
        self.app = app
        self.demo = demo
        self.wanted = set(printers)
        self.conn = None
        self.queues = set()
        self.queues_checked = 0
        self.known_done = None    # ids of completed jobs already accounted for
        self.jobs = {}            # id -> attributes of active jobs
        self.last_log = {}        # id -> (state, pages, percent/10, message)
        self.page_start = {}      # id -> (pages done, time)
        self.notified = set()
        self.shown_job = None
        self.dismissed = None
        self.manual_open = False
        self.hide_at = None
        self.paused = False
        self.held = set()         # jobs held by the pause
        self.last_finished = None  # (id, attributes) of the last finished job
        self.opt_key = None
        self.ppd_cache = {}
        self.demo_start = time.time()
        os.makedirs(LOG_DIR, exist_ok=True)
        self.logfile = open(os.path.join(LOG_DIR, "demo.log" if demo else "monitor.log"),
                            "a", buffering=1)
        if Notify and not Notify.is_initted():
            Notify.init(APP_NAME)
        self.settings_dialog = None
        self.build_window()
        self.build_tray()
        self.apply_window_settings()
        GLib.timeout_add_seconds(POLL_S, self.poll)
        GLib.timeout_add(ANIM_MS, self.animate)

    # ---------- Window ----------
    def build_window(self):
        w = self.win = Gtk.Window(title=APP_NAME)
        w.set_default_size(700, -1)
        w.set_border_width(14)
        w.connect("delete-event", lambda *_: (self.dismiss(), True)[1])
        outer = Gtk.Box(spacing=14)
        w.add(outer)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.title = Gtk.Label(xalign=0)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub = Gtk.Label(xalign=0)
        self.sub.get_style_context().add_class("dim-label")
        self.anim = Animation()
        frame = Gtk.Frame(shadow_type=Gtk.ShadowType.IN)
        frame.add(self.anim)
        frame.set_valign(Gtk.Align.START)
        self.bar = Gtk.ProgressBar(show_text=True)
        grid = Gtk.Grid(column_spacing=14, row_spacing=4)
        self.vals = {}
        for i, (key, label) in enumerate([
                ("status", "Status"), ("page", "Page"), ("runtime", "Runtime"),
                ("eta", "Remaining (approx.)"), ("size", "Data size"), ("message", "Message")]):
            k = Gtk.Label(label=_(label), xalign=0)
            k.get_style_context().add_class("dim-label")
            v = Gtk.Label(label="–", xalign=0, selectable=True)
            v.set_line_wrap(True)
            grid.attach(k, 0, i, 1, 1)
            grid.attach(v, 1, i, 1, 1)
            self.vals[key] = v
        self.info = Gtk.Label(xalign=0)
        self.info.set_line_wrap(True)

        self.exp_opts = Gtk.Expander(label=_("Job print options"))
        self.opts_grid = Gtk.Grid(column_spacing=14, row_spacing=2)
        self.exp_opts.add(self.opts_grid)
        self.exp_opts.set_expanded(SETTINGS["expand_options"])
        self.exp_opts.connect("notify::expanded", self.on_expander, "expand_options")

        self.exp_queue = Gtk.Expander(label=_("Queue"))
        qbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.qstore = Gtk.ListStore(int, str, str, str, str)
        self.qview = Gtk.TreeView(model=self.qstore)
        for i, title in enumerate(["No.", "Document", "User", "Status", "Page"]):
            col = Gtk.TreeViewColumn(_(title), Gtk.CellRendererText(), text=i)
            col.set_resizable(True)
            self.qview.append_column(col)
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(90)
        sw.add(self.qview)
        qbtn = Gtk.Box(spacing=6)
        b_qc = Gtk.Button(label=_("Cancel selected"))
        b_qc.connect("clicked", self.on_queue_cancel)
        self.b_qh = Gtk.Button(label=_("Hold / release selected"))
        self.b_qh.connect("clicked", self.on_queue_hold)
        qbtn.pack_start(b_qc, False, False, 0)
        qbtn.pack_start(self.b_qh, False, False, 0)
        qbox.pack_start(sw, True, True, 0)
        qbox.pack_start(qbtn, False, False, 0)
        self.exp_queue.add(qbox)
        self.exp_queue.set_expanded(SETTINGS["expand_queue"])
        self.exp_queue.connect("notify::expanded", self.on_expander, "expand_queue")

        exp_log = Gtk.Expander(label=_("History"))
        sw2 = Gtk.ScrolledWindow()
        sw2.set_min_content_height(110)
        self.log = Gtk.TextView(editable=False, monospace=True)
        self.log.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw2.add(self.log)
        exp_log.add(sw2)

        btns = Gtk.Box(spacing=6)
        self.b_pause = Gtk.Button(label="Pause")
        self.b_pause.set_tooltip_text(
            _("Holds waiting and newly arriving jobs. The running job prints to the end: "
              "CUPS cannot interrupt it cleanly, holding it would cancel it and restart "
              "it from the beginning later."))
        self.b_pause.connect("clicked", lambda *_: self.toggle_pause())
        self.b_again = Gtk.Button(label=_("Print again"))
        self.b_again.set_tooltip_text(_("Prints the finished job again "
                                        "(CUPS keeps the data only for a limited time)."))
        self.b_again.connect("clicked", lambda *_: self.reprint())
        self.cancel = Gtk.Button(label=_("Cancel job"))
        self.cancel.connect("clicked", self.on_cancel)
        b_set = Gtk.Button(label=_("Settings …"))
        b_set.connect("clicked", lambda *_: self.open_settings())
        b_hide = Gtk.Button(label=_("Hide"))
        b_hide.connect("clicked", lambda *_: self.dismiss())
        for b in (self.b_pause, self.b_again, self.cancel):
            btns.pack_start(b, False, False, 0)
        btns.pack_end(b_hide, False, False, 0)
        btns.pack_end(b_set, False, False, 0)

        for x in (self.title, self.sub, self.bar, grid, self.info, self.exp_opts,
                  self.exp_queue, exp_log, btns):
            box.pack_start(x, False, False, 0)
        outer.pack_start(frame, False, False, 0)
        outer.pack_start(box, True, True, 0)

    def on_expander(self, exp, _pspec, key):
        SETTINGS[key] = exp.get_expanded()
        save_settings(SETTINGS)
        if key == "expand_options":
            self.opt_key = None
        GLib.idle_add(lambda: self.win.resize(self.win.get_size()[0], 1) or False)

    def apply_window_settings(self):
        self.win.set_keep_above(bool(SETTINGS["keep_above"]))

    def animate(self):
        if self.win.get_visible():
            self.anim.tick += 1
            self.anim.render()
        return True

    def dismiss(self):
        """Hide the window for the current job; a new job opens it again."""
        self.dismissed = self.shown_job
        self.manual_open = False
        self.win.hide()

    def wlog(self, text):
        line = "%s  %s\n" % (time.strftime("%H:%M:%S"), text)
        buf = self.log.get_buffer()
        buf.insert(buf.get_end_iter(), line)
        self.log.scroll_to_iter(buf.get_end_iter(), 0, False, 0, 0)
        self.logfile.write(time.strftime("%Y-%m-%d ") + line)

    def message(self, text, kind=Gtk.MessageType.INFO):
        d = Gtk.MessageDialog(transient_for=self.win if self.win.get_visible() else None,
                              message_type=kind, buttons=Gtk.ButtonsType.OK, text=text)
        d.run()
        d.destroy()

    # ---------- Tray icon ----------
    def build_tray(self):
        self.ind = None
        if not AppIndicator:
            return
        self.ind = AppIndicator.Indicator.new(
            "lq300-monitor", "printer", AppIndicator.IndicatorCategory.HARDWARE)
        self.ind.set_title(APP_NAME)
        menu = Gtk.Menu()
        self.t_status = Gtk.MenuItem(label=_("Ready"))
        self.t_status.set_sensitive(False)
        self.t_show = Gtk.MenuItem(label=_("Show window"))
        self.t_show.connect("activate", lambda *_: self.show_now())
        self.t_again = Gtk.MenuItem(label=_("Print last job again"))
        self.t_again.connect("activate", lambda *_: self.reprint(self.last_finished[0]
                                                               if self.last_finished else None))
        self.t_pause = Gtk.MenuItem(label=_("Pause (hold waiting jobs)"))
        self.t_pause.connect("activate", lambda *_: self.toggle_pause())
        t_set = Gtk.MenuItem(label=_("Settings …"))
        t_set.connect("activate", lambda *_: self.open_settings())
        t_quit = Gtk.MenuItem(label=_("Quit monitor"))
        t_quit.connect("activate", lambda *_: self.app.quit())
        for it in (self.t_status, Gtk.SeparatorMenuItem(), self.t_show, self.t_again,
                   self.t_pause, Gtk.SeparatorMenuItem(), t_set, t_quit):
            menu.append(it)
        menu.show_all()
        self.ind.set_menu(menu)
        self.apply_tray_settings()

    def apply_tray_settings(self):
        if self.ind:
            self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE if SETTINGS["tray"]
                                else AppIndicator.IndicatorStatus.PASSIVE)

    def update_tray(self, job, waiting):
        if not self.ind or not SETTINGS["tray"]:
            return
        state = job.get("job-state") if job else None
        if state in (8, 6):
            icon, text, label = "printer-error", _("Print error"), ""
        elif self.paused:
            icon, text, label = "printer-warning", "Pause", "Pause"
        elif job and state in ACTIVE:
            frac, _eta = estimate(job, time.time(), 0)
            pct = job.get("job-media-progress") or 0
            icon, text, label = "printer", _("Printing: %s") % jname(job), \
                ("%d %%" % pct if pct else "")
        else:
            icon, text, label = "printer", _("Ready"), ""
        if self.ind.get_icon() != icon:
            self.ind.set_icon_full(icon, text)
        self.ind.set_label(label, "100 %")
        self.t_status.set_label(text + (_(" (+%d waiting)") % waiting if waiting else ""))
        self.t_again.set_sensitive(self.last_finished is not None)
        self.t_pause.set_label(_("Resume (release held jobs)") if self.paused
                               else _("Pause (hold waiting jobs)"))

    # ---------- Settings ----------
    def open_settings(self):
        if self.settings_dialog:
            self.settings_dialog.present()
            return
        d = self.settings_dialog = Gtk.Dialog(title=_("Settings – ") + APP_NAME)
        d.set_border_width(12)
        d.add_button(_("Close"), Gtk.ResponseType.CLOSE)
        area = d.get_content_area()
        area.set_spacing(6)

        def check(label, key, tip=None, cb=None):
            c = Gtk.CheckButton(label=label)
            c.set_active(bool(SETTINGS[key]))
            if tip:
                c.set_tooltip_text(tip)

            def toggled(w):
                SETTINGS[key] = w.get_active()
                save_settings(SETTINGS)
                if cb:
                    cb()
            c.connect("toggled", toggled)
            area.pack_start(c, False, False, 0)
            return c

        def head(text):
            lab = Gtk.Label(xalign=0)
            lab.set_markup("<b>%s</b>" % text)
            area.pack_start(lab, False, False, 6)

        head(_("Window"))
        check(_("Show the window automatically for print jobs"), "show_window",
              _("Off: only the tray icon shows printing; open the window from there."))
        check(_("Bring the window to the front automatically"), "raise_window",
              _("Depends on the window manager; some prevent raising windows."))
        check(_("Keep the window always on top"), "keep_above",
              _("Takes effect after restarting the monitor. Under Wayland the monitor "
                "uses XWayland for this."), self.apply_window_settings)
        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label=_("Hide the window after a successful end after")),
                       False, False, 0)
        spin = Gtk.SpinButton.new_with_range(0, 600, 1)
        spin.set_value(SETTINGS["hide_after"])
        spin.connect("value-changed", lambda w: (SETTINGS.__setitem__(
            "hide_after", int(w.get_value())), save_settings(SETTINGS)))
        row.pack_start(spin, False, False, 0)
        row.pack_start(Gtk.Label(label=_("seconds (0 = never)")), False, False, 0)
        area.pack_start(row, False, False, 0)

        head(_("Tray"))
        c = check(_("Show print status as a tray icon"), "tray",
                  None, self.apply_tray_settings)
        if not AppIndicator:
            c.set_sensitive(False)
            c.set_tooltip_text(_("Not available: install gir1.2-ayatanaappindicator3-0.1."))

        head(_("Notifications"))
        n1 = check(_("Notify when a print is finished"), "notify_done")
        n2 = check(_("Notify on print errors"), "notify_error")
        if not Notify:
            for n in (n1, n2):
                n.set_sensitive(False)
                n.set_tooltip_text(_("Not available: install gir1.2-notify-0.7."))

        head(_("Startup and queues"))
        auto = Gtk.CheckButton(label=_("Start the monitor at login"))
        auto.set_active(autostart_enabled())
        auto.connect("toggled", lambda w: set_autostart(w.get_active()))
        area.pack_start(auto, False, False, 0)
        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label=_("Monitored queues (empty = all LQ-300):")),
                       False, False, 0)
        ent = Gtk.Entry(text=SETTINGS["printers"])
        ent.set_tooltip_text(_("Queue names, comma-separated. Takes effect after a restart."))
        ent.connect("changed", lambda w: (SETTINGS.__setitem__("printers", w.get_text()),
                                          save_settings(SETTINGS)))
        row.pack_start(ent, True, True, 0)
        area.pack_start(row, False, False, 0)

        quit_btn = Gtk.Button(label=_("Quit the monitor now"))
        quit_btn.connect("clicked", lambda *_: self.app.quit())
        area.pack_start(quit_btn, False, False, 6)
        d.connect("response", self.close_settings)
        d.connect("delete-event", lambda *_: self.close_settings())
        d.show_all()

    def close_settings(self, *_args):
        if self.settings_dialog:
            self.settings_dialog.destroy()
            self.settings_dialog = None
        return True

    # ---------- CUPS ----------
    def connect(self):
        if self.conn is None:
            self.conn = cups.Connection()
        return self.conn

    def refresh_queues(self):
        if time.time() - self.queues_checked < 15 and self.queues:
            return
        self.queues_checked = time.time()
        found = set()
        for name, a in self.connect().getPrinters().items():
            if self.wanted:
                if name in self.wanted:
                    found.add(name)
            elif re.search(r"LQ-?300", a.get("printer-make-and-model") or "", re.I):
                found.add(name)
        self.queues = found

    def fetch_jobs(self):
        """Active jobs of our queues; jobs seen last time that have finished
        are fetched once more with their final state."""
        c = self.connect()
        self.refresh_queues()
        now = {}
        for jid, a in c.getJobs(which_jobs="not-completed",
                                requested_attributes=JOB_ATTRS).items():
            if a.get("job-printer-uri", "").rsplit("/", 1)[-1] in self.queues:
                a["job-id"] = jid
                now[jid] = a
        finished = {}
        for jid in set(self.jobs) - set(now):
            try:
                finished[jid] = c.getJobAttributes(jid, requested_attributes=JOB_ATTRS)
                finished[jid]["job-id"] = jid
            except cups.IPPError:
                finished[jid] = dict(self.jobs[jid], **{"job-state": 9})
        # jobs that started and finished between two polls (short jobs) were never active
        done = {}
        for jid, a in c.getJobs(which_jobs="completed", requested_attributes=JOB_ATTRS).items():
            if a.get("job-printer-uri", "").rsplit("/", 1)[-1] in self.queues:
                done[jid] = a
        if self.known_done is None:
            self.known_done = set(done)          # first poll: do not replay the history
        for jid in sorted(set(done) - self.known_done - set(finished) - set(now)):
            try:
                a = c.getJobAttributes(jid, requested_attributes=JOB_ATTRS)
            except cups.IPPError:
                a = done[jid]
            a["job-id"] = jid
            finished[jid] = a
        self.known_done |= set(done)
        return now, finished

    # ---------- Actions ----------
    def on_cancel(self, *_args):
        jid = self.shown_job
        if jid:
            self.cancel_job(jid)

    def cancel_job(self, jid):
        if self.demo:
            self.wlog(_("Demo: cancel of job %d") % jid)
            return
        try:
            self.connect().cancelJob(jid)
            self.wlog(_("Job %d: cancel requested") % jid)
        except Exception as e:                     # noqa: BLE001
            self.wlog(_("Cancel failed: %s") % e)

    def set_hold(self, jid, hold):
        if self.demo:
            self.wlog(_("Demo: job %d %s") % (jid, _("held") if hold else _("released")))
            return True
        try:
            self.connect().setJobHoldUntil(jid, "indefinite" if hold else "no-hold")
            return True
        except Exception as e:                     # noqa: BLE001
            self.wlog(_("Job %d: %s failed: %s") % (jid, _("Holding") if hold else _("Releasing"), e))
            return False

    def toggle_pause(self):
        """Pause: hold waiting and newly arriving jobs. The running job is left
        alone (holding it would cancel it and restart it from the beginning later)."""
        self.paused = not self.paused
        if self.paused:
            self.wlog(_("Pause: waiting jobs are being held"))
            self.hold_pending(self.jobs)
        else:
            self.wlog(_("Pause ended: %d jobs released") % len(self.held))
            for jid in list(self.held):
                self.set_hold(jid, False)
            self.held.clear()
        self.update_buttons()

    def hold_pending(self, jobs):
        for jid, a in jobs.items():
            if a.get("job-state") == 3 and jid not in self.held and self.set_hold(jid, True):
                self.held.add(jid)

    def reprint(self, jid=None):
        jid = jid or (self.shown_job if self.shown_job and
                      self.jobs.get(self.shown_job, {}).get("job-state") not in ACTIVE else None)
        if jid is None and self.last_finished:
            jid = self.last_finished[0]
        if jid is None:
            return
        if self.demo:
            self.wlog(_("Demo: print job %d again") % jid)
            return
        try:
            self.connect().restartJob(jid)
        except Exception as e:                     # noqa: BLE001
            self.wlog(_("Print again failed: %s") % e)
            self.message(_("Job %d cannot be printed again.\n\n%s\n\n"
                           "CUPS keeps the data of finished jobs only for a limited time "
                           "(PreserveJobFiles).") % (jid, e), Gtk.MessageType.WARNING)
            return
        self.wlog(_("Job %d: printed again") % jid)
        for d in (self.last_log, self.page_start):
            d.pop(jid, None)
        self.notified.discard(jid)
        self.dismissed = None
        self.hide_at = None

    def selected_job(self):
        model, it = self.qview.get_selection().get_selected()
        return model[it][0] if it else None

    def on_queue_cancel(self, *_args):
        jid = self.selected_job()
        if jid:
            self.cancel_job(jid)

    def on_queue_hold(self, *_args):
        jid = self.selected_job()
        if not jid:
            return
        state = self.jobs.get(jid, {}).get("job-state")
        if state == 4:
            self.set_hold(jid, False)
            self.held.discard(jid)
        elif state == 3:
            self.set_hold(jid, True)
        else:
            self.message(_("Only waiting or held jobs can be held or released. "
                           "A running job would be canceled."))

    # ---------- Flow ----------
    def demo_jobs(self):
        """Simulates in turn: waiting, printing 4 pages, done/error."""
        t = time.time() - self.demo_start
        n, cycle = divmod(t, 60)
        if cycle < 8:
            state, done, prog = 3, 0, 0
        elif cycle < 46:
            state = 5
            p = (cycle - 8) / 38 * 4
            done, prog = int(p), int(p % 1 * 100)
        else:
            state, done, prog = (9 if int(n) % 2 == 0 else 8), 4, 0
        jid = 99 + int(n)
        job = {"job-id": jid, "job-name": "Demo: test page.pdf",
               "job-originating-user-name": "demo",
               "job-printer-uri": "ipp://localhost/printers/LQ-300_Demo",
               "job-state": state, "job-state-reasons": "job-printing",
               "job-media-progress": prog, "job-media-sheets-completed": done,
               "job-impressions": 4, "job-k-octets": 812,
               "time-at-processing": int(self.demo_start + n * 60 + 8),
               "job-printer-state-message": "Page %d of 4, %d %%" % (done + 1, prog)}
        jobs = {}
        if state in (3, 5):
            jobs[jid] = job
            jobs[jid + 1000] = dict(job, **{"job-id": jid + 1000, "job-state": 3,
                                            "job-name": "Demo: letter.txt",
                                            "job-media-progress": 0,
                                            "job-media-sheets-completed": 0})
        if state in (8, 9):
            return {}, {jid: job}
        return jobs, {}

    def poll(self):
        try:
            now, finished = self.demo_jobs() if self.demo else self.fetch_jobs()
        except Exception as e:                      # noqa: BLE001
            self.conn = None
            self.vals["message"].set_text(_("CUPS not reachable: %s") % e)
            return True
        for jid, a in list(finished.items()) + list(now.items()):
            self.log_changes(jid, a)
        for jid, a in finished.items():
            self.last_finished = (jid, a)
            self.held.discard(jid)
            self.notify_end(jid, a)
        self.jobs = now
        if self.paused:
            self.hold_pending(now)
        self.fill_queue(now)
        job = waiting = None
        if now:
            jid = self.shown_job if self.shown_job in now else \
                sorted(now, key=lambda j: (now[j].get("job-state") != 5, j))[0]
            job, waiting = now[jid], len(now) - 1
            self.hide_at = None
        elif finished:
            job, waiting = finished[max(finished)], 0
            ok = job.get("job-state") == 9
            self.hide_at = time.time() + SETTINGS["hide_after"] \
                if ok and SETTINGS["hide_after"] and not self.manual_open else None
        elif self.manual_open and self.last_finished:
            job, waiting = self.last_finished[1], 0
        if job:
            self.show(job, waiting)
        elif self.manual_open:
            self.show_idle()
        elif self.hide_at and time.time() > self.hide_at:
            self.win.hide()
            self.hide_at = None
            self.shown_job = None
        self.update_tray(job if now or finished else None, waiting or 0)
        self.update_buttons()
        return True

    def log_changes(self, jid, a):
        key = (a.get("job-state"), a.get("job-media-sheets-completed") or 0,
               (a.get("job-media-progress") or 0) // 10,
               a.get("job-printer-state-message") or "")
        old = self.last_log.get(jid)
        if old == key:
            return
        self.last_log[jid] = key
        if old is None:
            self.wlog(_("Job %d '%s' detected") % (jid, jname(a)))
        self.wlog(_("Job %d: %s, page %d done, %d%% of the page%s") % (
            jid, state_name(key[0], key[0]), key[1],
            a.get("job-media-progress") or 0, (", " + key[3]) if key[3] else ""))

    def notify_end(self, jid, a):
        if jid in self.notified or not Notify:
            return
        state = a.get("job-state")
        name = jname(a)
        start = a.get("time-at-processing") or a.get("time-at-creation") or time.time()
        if state == 9 and SETTINGS["notify_done"]:
            body = _("%s · %d page(s) · %s") % (name, a.get("job-media-sheets-completed") or 0,
                                               fmt_time((a.get("time-at-completed") or time.time()) - start))
            title, icon = _("Print finished"), "printer"
        elif state in (6, 8) and SETTINGS["notify_error"]:
            body = "%s · %s" % (name, reasons_text(a.get("job-state-reasons")) or _("canceled"))
            title, icon = _("Print error"), "printer-error"
        else:
            return
        self.notified.add(jid)
        try:
            Notify.Notification.new(title, body, icon).show()
        except Exception as e:                      # noqa: BLE001
            self.wlog(_("Notification failed: %s") % e)

    def fill_queue(self, jobs):
        sel = self.selected_job()
        self.qstore.clear()
        for jid in sorted(jobs):
            a = jobs[jid]
            total = page_total(a)
            self.qstore.append([jid, jname(a),
                                a.get("job-originating-user-name", "?"),
                                state_name(a.get("job-state"), "?"),
                                "%d%s" % (a.get("job-media-sheets-completed") or 0,
                                          " / %d" % total if total else "")])
            if jid == sel:
                self.qview.get_selection().select_path(Gtk.TreePath(len(self.qstore) - 1))
        self.exp_queue.set_label(_("Queue (%d)") % len(jobs))

    def update_buttons(self):
        job = self.jobs.get(self.shown_job)
        running = bool(job and job.get("job-state") in ACTIVE)
        self.b_pause.set_label(_("Resume") if self.paused else "Pause")
        self.cancel.set_sensitive(running)
        self.b_again.set_sensitive(not running and (self.shown_job is not None
                                                     or self.last_finished is not None))
        parts = []
        if self.paused:
            parts.append(_("Pause: %d job(s) held, the running print continues.")
                         % len(self.held))
        elif len(self.jobs) > 1:
            parts.append(_("+ %d more jobs waiting") % (len(self.jobs) - 1))
        self.info.set_text(" ".join(parts))

    def show_now(self):
        self.manual_open = True
        self.dismissed = None
        self.win.show_all()
        self.win.present()
        self.poll()

    def show_idle(self):
        self.title.set_markup("<b>%s</b>" % _("No job active"))
        self.sub.set_text(_("Monitored queues: %s") % (", ".join(sorted(self.queues)) or "–"))
        self.anim.state = "idle"
        self.bar.set_fraction(0)
        self.bar.set_text(_("ready"))
        for v in self.vals.values():
            v.set_text("–")
        self.reveal()

    def reveal(self):
        if not self.win.get_visible() and (self.manual_open or
                                           (SETTINGS["show_window"] and
                                            self.shown_job != self.dismissed)):
            self.win.show_all()
            if SETTINGS["raise_window"] or self.manual_open:
                self.win.present()

    def show(self, job, waiting):
        jid = job["job-id"]
        self.shown_job = jid
        state = job.get("job-state")
        now = time.time()
        queue = job.get("job-printer-uri", "").rsplit("/", 1)[-1]
        self.title.set_markup("<b>%s</b>" % GLib.markup_escape_text(jname(job)))
        self.sub.set_text(_("Queue %s · user %s · job %d") % (
            queue, job.get("job-originating-user-name", "?"), jid))
        sheets = job.get("job-media-sheets-completed") or 0
        ps = self.page_start.get(jid)
        if ps is None or ps[0] != sheets:
            ps = (sheets, job.get("time-at-processing") or now if sheets == 0 else now)
            self.page_start[jid] = ps
        frac, eta = estimate(job, now, ps[1])
        if state in ACTIVE:
            if frac is None:
                self.bar.pulse()
                self.bar.set_text(_("waiting") if state in (3, 4) else _("running …"))
            else:
                self.bar.set_fraction(frac)
                self.bar.set_text("%d %%%s" % (round(frac * 100),
                                  "" if page_total(job) else _(" of this page")))
        else:
            self.bar.set_fraction(1.0 if state == 9 else self.bar.get_fraction())
            self.bar.set_text(_("done") if state == 9 else state_name(state, ""))
        status = state_name(state, str(state))
        r = reasons_text(job.get("job-state-reasons"))
        self.vals["status"].set_text(status + (" (%s)" % r if r and state != 9 and r != status else ""))
        total = page_total(job)
        page = _("%d printed") % sheets + (_(" of %d") % total if total else "")
        self.vals["page"].set_text(page)
        start = job.get("time-at-processing") or job.get("time-at-creation") or now
        end = job.get("time-at-completed") if state in (7, 8, 9) else 0
        self.vals["runtime"].set_text(fmt_time((end or now) - start))
        if state in ACTIVE:
            self.vals["eta"].set_text(
                (fmt_time(eta) + ("" if total else _(" (for this page)"))) if eta is not None
                else _("calculating …"))
        else:
            self.vals["eta"].set_text("–")
        self.vals["size"].set_text(_("%s KiB (job)") % (job.get("job-k-octets") or 0))
        self.vals["message"].set_text(job.get("job-printer-state-message") or "–")
        self.anim.state = {5: "print", 3: "wait", 4: "wait", 9: "done"}.get(state, "error")
        if self.exp_opts.get_expanded():
            self.refresh_options(job, queue)
        self.reveal()

    # ---------- Print options ----------
    def ppd_options(self, queue):
        """Keyword -> (default value, {value: text}) from the queue's PPD."""
        if queue in self.ppd_cache:
            return self.ppd_cache[queue]
        res = {}
        if not self.demo:
            path = None
            try:
                path = self.connect().getPPD(queue)
                ppd = cups.PPD(path)
                tr = ppd_translations(path, _detect_lang())
                for key, _label in OPT_KEYS:
                    opt = ppd.findOption(key)
                    if opt:
                        res[key] = (opt.defchoice, {c["choice"]: tr.get((key, c["choice"]), c["text"])
                                                    for c in opt.choices})
            except Exception:                       # noqa: BLE001
                pass
            finally:
                if path:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
        self.ppd_cache[queue] = res
        return res

    def refresh_options(self, job, queue):
        key = (job["job-id"], queue)
        if key == self.opt_key:
            return
        self.opt_key = key
        rows = []
        attrs = {}
        if self.demo:
            attrs = {"Resolution": "360x180dpi", "ColorModel": "Gray", "copies": 1}
        else:
            try:
                attrs = self.connect().getJobAttributes(job["job-id"])
            except Exception:                       # noqa: BLE001
                pass
        defaults = self.ppd_options(queue)
        rows.append((_("Document format"), str(attrs.get("document-format-detected")
                                           or attrs.get("document-format") or "–")))
        rows.append((_("Copies"), str(attrs.get("copies", 1))))
        for k, label in OPT_KEYS:
            dflt, texts = defaults.get(k, (None, {}))
            val, given = attrs.get(k), True
            if val is None and k == "ColorModel":
                pcm = attrs.get("print-color-mode")
                val = {"color": "RGB", "monochrome": "Gray"}.get(pcm)
            if val is None and k == "PageSize":
                val = attrs.get("media")
            if val is None:
                val, given = dflt, False
            if val is None:
                continue
            text = texts.get(val, val)
            rows.append((_(label), "%s%s" % (text, "" if given else "  " + _("(default)"))))
        for ch in self.opts_grid.get_children():
            self.opts_grid.remove(ch)
        for i, (k, v) in enumerate(rows):
            a = Gtk.Label(label=k, xalign=0)
            a.get_style_context().add_class("dim-label")
            b = Gtk.Label(label=v, xalign=0, selectable=True)
            self.opts_grid.attach(a, 0, i, 1, 1)
            self.opts_grid.attach(b, 1, i, 1, 1)
        self.opts_grid.show_all()


class App(Gtk.Application):
    """One instance: further calls (--show, --settings, --quit) are passed
    on to the running monitor."""

    def __init__(self, demo, printers):
        super().__init__(application_id=APP_ID + (".Demo" if demo else ""),
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.demo, self.printers, self.mon = demo, printers, None

    def do_command_line(self, cl):
        args = cl.get_arguments()[1:]
        if self.mon is None:
            if "--quit" in args:
                return 0
            self.hold()
            self.mon = Monitor(self, self.printers, self.demo)
            if self.demo:
                self.mon.show_now()
        if "--quit" in args:
            self.quit()
        if "--settings" in args:
            self.mon.open_settings()
        if "--show" in args:
            self.mon.show_now()
        return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--printers", help="queue names, comma-separated")
    ap.add_argument("--demo", action="store_true", help="simulated job")
    ap.add_argument("--show", action="store_true", help="show the window")
    ap.add_argument("--settings", action="store_true", help="open the settings")
    ap.add_argument("--quit", action="store_true", help="quit the running monitor")
    ap.add_argument("--install-autostart", action="store_true")
    ap.add_argument("--remove-autostart", action="store_true")
    a = ap.parse_args()
    if a.install_autostart or a.remove_autostart:
        set_autostart(a.install_autostart)
        print("Autostart %s." % ("enabled" if a.install_autostart else "disabled"))
        return
    if cups is None and not a.demo:
        sys.exit("python3-cups is missing: sudo apt install python3-cups")
    printers = set((a.printers or SETTINGS["printers"]).replace(" ", "").split(",")) - {""}
    app = App(a.demo, printers)
    sys.exit(app.run([sys.argv[0]] + [x for x in sys.argv[1:] if x != "--printers"
                                      and not (x.startswith("--printers="))]))


if __name__ == "__main__":
    main()
