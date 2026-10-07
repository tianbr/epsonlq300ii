# CUPS driver "EpsonLQ300+ii" for the Epson LQ-300+II

A driver (PPD, two filters and an optional status monitor) for the 24-pin Epson LQ-300+II
dot matrix printer (ESC/P2), with and without the color ribbon. Tested with CUPS 2.4 on
Ubuntu. Driver version 2.3, status monitor version 1.1. This project is not affiliated with Epson.
Developed with the assistance of an AI coding assistant (Claude) and tested on a single printer.

| File | Purpose |
|---|---|
| `lq300ii.ppd` | printer description (paper sizes, options, filter assignment); German translation included |
| `texttoescplq.c`, `charsets.h` | filter for `text/plain`: uses the printer's built-in fonts |
| `rastertoescplq.c` | filter for graphics (PDF, images): 24-pin bitmap with `ESC *`, black-and-white and color |
| `lq300_monitor.py` | status monitor (window with progress and remaining time), see [MONITOR.md](MONITOR.md) |
| `build_deb.sh`, `build_deb_monitor.sh` | build the installation packages (driver, monitor) |
| `Makefile` | build, install, check the PPD |

## Installation

With the package (guide: [INSTALLATION.md](INSTALLATION.md)):

```bash
sudo apt install ./epsonlq300+ii_2.3_amd64.deb
```

From source: `make`, `sudo make install`, `sudo systemctl restart cups`. The packages are built
with `./build_deb.sh` and `./build_deb_monitor.sh` into the folder `dist/`.

Adding the printer: the device address (`-v`) depends on the connection (print server via LPD or
raw port, USB, parallel); all cases are described in [INSTALLATION.md](INSTALLATION.md).
CUPS queue names must not contain spaces; the display name goes into the description (`-D`):

```bash
sudo lpadmin -p <queue> -D "Epson LQ-300 + II" -E -v <device-address> -m lq300ii.ppd
```

The warning "Printer drivers are deprecated" is harmless: CUPS wants to drop PPD drivers in the
long term. Everything works with CUPS 2.4.

## Usage

```bash
lp -d <queue> letter.txt                    # text with the printer's fonts
lp -d <queue> document.pdf                  # graphics
lp -d <queue> -o cpi=12 -o lpi=8 -o LQTypeface=Sans letter.txt
lp -d <queue> -o Resolution=360x360dpi photo.png
```

Raw data (without CUPS) goes directly to the raw port of the printer or print server:

```bash
nc -q 3 <host> 9100 < file.prn
```

## Options

Always used as `-o Name=Value`. Bold = default.

### Graphics

| Option | Values | Meaning |
|---|---|---|
| `Resolution` | `120x180dpi`, `180x180dpi`, **`360x180dpi`**, `360x360dpi` | Resolution. 360x180 prints each line once (like the Windows driver), 360x360 takes twice as long |
| `LQDensity` | **`Contrast`**, `Normal`, `Light`, `Dark`, `Raw` | Tone curve. `Contrast` separates dark tones better (like Windows), `Raw` = no curve (calibration) |
| `LQDither` | **`Auto`**, `Cluster`, `Bayer`, `FloydSteinberg`, `Threshold` | Halftoning. `Auto` thresholds text and lines hard and halftones areas. Floyd-Steinberg is not recommended because the dots run into each other strongly |
| `LQOnePass` | **`On`**, `Off` | `On`: one pass per line, like Windows. `Off`: two commands per line, a bit darker, takes twice as long (4:08 instead of 2:04 minutes at 360x180). No effect at 360x360, because every band is printed in two interleaved passes there anyway |
| `LQMerge` | **`On`**, `Off` | Print identical dot pairs (halftone areas) once at 180 dpi; reduces the amount of data |

### Text

| Option | Values | Meaning |
|---|---|---|
| `LQCharset` | **`ISO8859-15`**, `PC858`, `PC850`, `ISO8859-1`, `PC437`, `Roman8` | Character set. UTF-8 input is converted, missing characters are replaced (e.g. `–` → `-`, `€` → `EUR`) |
| `InputSlot` | **`Auto`**, `Feeder` | Paper source. `Auto` sends nothing (cut sheet/tractor is chosen by the lever on the printer), `Feeder` sends `ESC EM 1` for the optional cut sheet feeder. Continuous paper via `PageSize` (Fanfold) |
| `LQTypeface` (not in the PPD) | **`Roman`**, `Sans`, `Courier`, `Prestige`, `Script`, `OCR-B`, `OCR-A`, `Orator`, `Orator-S`, `ScriptC`, `RomanT`, `SansH` | Printer typeface |
| `LQQuality` | **`LQ`**, `Draft` | Letter quality or draft (faster) |
| `LQPitch` or `cpi` (not in the PPD) | **`10`**, `12`, `15`, `17`, `20` | Characters per inch (17/20 = condensed) |
| `LQLpi` or `lpi` (not in the PPD) | `4`, **`6`**, `8`, `10` | Lines per inch |
| `page-left`, `page-right`, `page-top`, `page-bottom` | points | additional margins |

Box-drawing characters (`┌ ─ ┬ ┐ │ ├ ┼ ┤ └ ┴ ┘`), blocks (`░ ▒ ▓ █`) and some Greek and
mathematical characters come from a second printer table (PC 437).

### Both filters

| Option | Values | Meaning |
|---|---|---|
| `LQDirection` | **`Adaptive`**, `Bidi`, `Uni`, `Auto` | Print direction. `Adaptive` (default) decides per 24-pin band (see below; for text the driver sends nothing and the firmware setting applies). `Auto` sends nothing, the firmware setting applies. `Bidi` prints bidirectionally, about 17 to 20 % faster; no quality difference was measurable on the test printer. With color, bands containing yellow, magenta or cyan are printed unidirectionally anyway so that the colors line up. `Uni` prints everything unidirectionally (precise). `Adaptive`: unidirectional if a vertical edge (line, barcode, letter stem, edge of an area) runs at least about 1.4 mm through the band, otherwise bidirectional (see `LQDirTol`, `LQDirHalo`). Only works if the firmware is set to **"Bidirectional"**; with "Automatic" the printer ignores `ESC U` and always prints graphics unidirectionally. The printer usually prints the first 5 to 10 bands of a page unidirectionally. `LQDEBUG=1` in the filter's environment lists the direction per band |
| `LQDirTol` (not in the PPD) | mm, **`1.41`** | Only for `Adaptive`: shortest vertical edge that makes a band unidirectional. Larger values (e.g. 2.5 or 4) let small text print bidirectionally, while lines, barcodes and areas stay unidirectional |
| `LQDirHalo` (not in the PPD) | **`1`**, `0` | Only for `Adaptive`: `1` also takes along the neighboring bands of a unidirectional band, `0` only bands that themselves touch a long edge |
| `PageSize` | **`A4`**, `A5`, `Letter`, `Legal`, `Fanfold_A4`, `Fanfold_210x12`, `Fanfold_240x12` | Paper size, Fanfold = tractor paper |

## Color

Color is part of the same driver: the option **Color mode** (`ColorModel`) switches between
*Black and white* (default) and *Color*. It requires the color upgrade kit with the color ribbon.

- **Separation:** RGB is split into the four ribbon colors yellow, magenta, cyan, black. The
  neutral part of each color comes from the black band (option `LQGcr`, percent, default 100) so
  that text and grays have no color fringe.
- **Printing:** one pass per color for each 24-pin band (`ESC r n`), in the order yellow,
  magenta, cyan, black. The driver prints bands with color unidirectionally so that the colors
  lie on top of each other.
- **Tone curve:** each ink has its own curve; `LQDensity=Raw` switches it off. The values come
  from a single printer with one ribbon and are only a starting point.
- **Calibrating the ribbon:** if color areas show horizontal stripes 3.4 mm apart (one 24-pin
  band), the ribbon is not seated correctly. A remedy that worked: switch the printer off, hold
  **Load/Eject** and **Pause**, switch the printer on. Repeat after every ribbon change.

## Progress and status monitor

Both filters report progress to CUPS (`job-media-progress`, `INFO: Page p [of n], x %`), which
the CUPS web interface and `lpstat -l` display. The optional status monitor `lq300-monitor`
(separate package) shows a window with bar, page and remaining time while printing, plus pause,
print again, queue, print options, tray icon and notifications, see [MONITOR.md](MONITOR.md).

## Known limitations

- Over a send-only connection (LPT, print server) the printer reports nothing back (no
  paper-out, no errors). The monitor only sees what the filter has sent.
- Text output has no bold, italic, underline or proportional fonts.
- Barcodes and QR codes print readably, but need room: a dot matrix dot is coarser than a pixel
  at 360 dpi, so a QR module should be at least about 0.6 mm.
- If "Auto line feed" is set to **On** in the printer menu, the text filter prints double line
  spacing. Set it to **Off**.
- Margins, tone curves and color values were determined on a single printer.

## Languages

The PPD is in English with a German translation (shown automatically by CUPS front ends in a
German locale). The monitor is in English with a built-in German table; further languages can be
added in `lq300_monitor.py` (`TRANSLATIONS`).

## License

MIT License, see [LICENSE](LICENSE).
