# Installing the "EpsonLQ300+ii" driver

This guide installs the finished driver from the package without compiling anything.
There are two independent packages:

| Package | Contents |
|---|---|
| `epsonlq300+ii_2.2_amd64.deb` | the driver: both filters and the PPD (color and black-and-white) |
| `epsonlq300+ii-monitor_1.0_all.deb` | the status monitor (optional) |

## Requirements

- Ubuntu or Debian on a 64-bit PC (x86-64) with CUPS (tested with 2.4)
- administrator rights (`sudo`)
- the file `epsonlq300+ii_2.2_amd64.deb` (and `epsonlq300+ii-monitor_1.0_all.deb` for the monitor),
  downloadable from the Releases page of the repository

## 1. Install the package

In the folder containing the file:

```bash
sudo apt install ./epsonlq300+ii_2.2_amd64.deb
```

The installation restarts CUPS.

## 2. Add the printer

The package does **not** create a printer and knows no address. The PPD only contains the
printer description. How the printer is connected is decided when you create the queue, by
the device address (`-v`). All examples here are examples: replace queue name, host name and
path with your own values.

CUPS queue names must not contain spaces. The display name (for example "Epson LQ-300 + II")
is therefore set as the description (`-D`).

The template for every connection:

```bash
sudo lpadmin -p <queue> -D "<display name>" -E -v <device-address> -m lq300ii.ppd
```

| Connection | Device address (`-v`) |
|---|---|
| Print server via LPD | `lpd://<host>/<queue-on-the-print-server>` |
| Print server, raw port | `socket://<host>:9100` |
| Print server or computer via IPP | `ipp://<host>/printers/<name>` (only if CUPS already runs there; the filters then run on that CUPS server) |
| USB | `usb://...`, the exact address is shown by `lpinfo -v` |
| Parallel (LPT) | `parallel:/dev/lp0` or the address from `lpinfo -v` |
| Serial (RS-232) | `serial:/dev/ttyS0?baud=9600` (parameters must match the printer's menu) |

**Finding the address:** switch the printer on, connect it and run

```bash
lpinfo -v
```

For USB and parallel the printer appears there with its address (for example
`direct usb://EPSON/LQ-300%2BII?serial=...`). Put that line after `-v`. The same works in the
CUPS web interface (`http://localhost:631`, "Add Printer"): choose the detected device, then the
driver "EpsonLQ300+ii".

Examples:

```bash
sudo lpadmin -p <queue> -D "Epson LQ-300 + II" -E -v lpd://<host>/<queue-on-the-print-server> -m lq300ii.ppd
```

```bash
sudo lpadmin -p <queue> -D "Epson LQ-300 + II" -E -v socket://<host>:9100 -m lq300ii.ppd
```

```bash
sudo lpadmin -p <queue> -D "Epson LQ-300 + II" -E -v "usb://EPSON/LQ-300%2BII?serial=XXXX" -m lq300ii.ppd
```

Change the connection later without recreating the queue:

```bash
sudo lpadmin -p <queue> -v <new-device-address>
```

**The same for every connection:** the filters always produce the same printer commands
(ESC/P2). Resolution, character sets and margins do not depend on the connection. Which
connections the printer itself has depends on the unit (parallel and RS-232 are common, USB
not on every unit). If the printer has no USB port, a USB-to-parallel adapter usually shows
up in `lpinfo -v` as `usb://...`. With a print server there is no feedback from the printer
(send only); directly over USB or parallel CUPS can often read messages such as "out of
paper" from the printer (untested; the monitor does not evaluate this yet).

The message "Printer drivers are deprecated" is only a warning.

## 3. Check

```bash
lpstat -p <queue> -l
```

Set as default printer (optional):

```bash
sudo lpadmin -d <queue>
```

Test print (text):

```bash
printf 'Test print: Ää Öö Üü ß € |\n' | lp -d <queue>
```

Umlauts, the euro sign and the vertical bar should print correctly.

## 4. Status monitor (optional)

```bash
sudo apt install ./epsonlq300+ii-monitor_1.0_all.deb
```

`apt` fetches the required packages (`python3-gi`, `python3-cups`, `gir1.2-gtk-3.0`) and
recommends `gir1.2-ayatanaappindicator3-0.1` (tray icon) and `gir1.2-notify-0.7`
(notifications). The monitor starts by itself at the next login. Open it right away:

```bash
lq300-monitor --show
```

It runs invisibly and shows a window as soon as a job prints. Everything can be adjusted in the
settings (`lq300-monitor --settings`), including switching off the start at login.
Description in [MONITOR.md](MONITOR.md). The monitor speaks English; with a German locale
(`LANG=de_…`) it shows German.

Just try it without printing: `lq300-monitor --demo`.
Remove completely: `sudo apt remove epsonlq300+ii-monitor`.

## Updating

Install the new package as in step 1 (driver) or step 4 (monitor). The queue stays. The queue
only gets the new PPD if you recreate it as in step 2 (`lpadmin` overwrites the existing one).
This is only necessary if options have changed.

## Uninstalling

```bash
sudo lpadmin -x <queue>
sudo apt remove 'epsonlq300+ii'
```

## Without a package (just copy files)

Without `apt`, the files `rastertoescplq`, `texttoescplq` (build them with `make`) and
`lq300ii.ppd` are enough:

```bash
sudo install -m 755 -o root -g root rastertoescplq texttoescplq /usr/lib/cups/filter/
sudo install -m 644 -o root -g root lq300ii.ppd /usr/share/cups/model/
sudo systemctl restart cups
```

The monitor also runs without a package: `python3 lq300_monitor.py` (needs `python3-gi`,
`python3-cups`, `gir1.2-gtk-3.0`).

On Fedora and Arch the filter directory is `/usr/libexec/cups/filter/`. The prebuilt binaries
in the package are for x86-64 only; elsewhere build with `make`.

## Troubleshooting

| Problem | Cause and remedy |
|---|---|
| `lpadmin` does not find `lq300ii.ppd` | CUPS not restarted: `sudo systemctl restart cups` |
| Job hangs or "Filter failed" | `sudo tail -n 30 /var/log/cups/error_log`. Usually the execute permission is missing (`ls -l /usr/lib/cups/filter/*escplq`, expected `-rwxr-xr-x root root`) |
| `Exec format error` in the log | Different processor (ARM, Raspberry Pi). Build there with `make` |
| Nothing printed, job "completed" | Check the queue name on the print server (`lpd://…/<queue>`) or use the raw port 9100 |
| Double line spacing in text | Set "Auto line feed" in the printer menu to **Off** |
| Monitor shows no window | Is it running? `lq300-monitor --show` opens it. Starting it in a terminal shows error messages. If "Show the window automatically" is off in the settings, only the tray icon shows printing |
| AppArmor blocks (Ubuntu, `DENIED` in the log) | The filters are not in `/usr/lib/cups/filter/`. Copy them there |

All print options are listed in the [README.md](README.md).
