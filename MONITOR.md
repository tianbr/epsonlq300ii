# Status monitor for the LQ-300+II

Separate package `epsonlq300+ii-monitor` (program [lq300_monitor.py](lq300_monitor.py),
installed as `lq300-monitor`). It runs in the background and shows a window with a pixel
animation, progress and remaining time as soon as a job runs on an LQ-300 queue. The package
is independent of the driver: if you do not want it, do not install it or remove it
(`sudo apt remove epsonlq300+ii-monitor`).

The monitor is in English; with a German locale it shows German. More languages can be added
to the `TRANSLATIONS` table at the top of `lq300_monitor.py`.

## Install, start, switch off

```bash
sudo apt install ./epsonlq300+ii-monitor_1.2_all.deb
```

The monitor starts by itself at the next login. Start and open it right away:

```bash
lq300-monitor --show
```

It is also in the application menu as "Epson LQ-300+II Print Status".

| Command | Effect |
|---|---|
| `lq300-monitor` | start the service (if one is already running, nothing happens) |
| `lq300-monitor --show` | show the window |
| `lq300-monitor --settings` | open the settings |
| `lq300-monitor --quit` | quit the running monitor |
| `lq300-monitor --demo` | simulated job, to look at it without printing |
| `lq300-monitor --printers A,B` | only these queues (default: all with "LQ-300" or "LQ300" in the model name) |

**Switching off:**
- permanently without uninstalling: settings, untick "Start the monitor at login"
- only quit the service: tray icon, "Quit monitor", or `lq300-monitor --quit`
- remove completely: uninstall the package

The monitor runs only once per user. Further calls talk to the running one.

## Window

Animation on the left (computer, cable, dot matrix printer), on the right job, bar, status,
page, runtime, remaining time, data size and filter message.

| State | Animation |
|---|---|
| printing | yellow data dots travel along the cable, the printer shakes and pushes paper with text lines upwards |
| waiting, on hold | hourglass, yellow LED blinks |
| done | green check mark |
| canceled, error, stopped | red cross, red LED blinks |

**Buttons:**

| Button | Effect |
|---|---|
| **Pause** / **Resume** | Holds waiting and newly arriving jobs until you resume. The *running* job prints to the end: CUPS cannot interrupt it cleanly. If it were held, CUPS would cancel it and print it again from the beginning later (checked on a test queue). To pause in the middle of a job, cancel it |
| **Print again** | Prints the finished job once more (CUPS `Restart-Job`). Works only as long as CUPS still has the data; otherwise a message appears |
| **Cancel job** | cancels the displayed job. The printer still prints the data already sent |
| **Settings …** | opens the settings dialog |
| **Hide** | hides the window for this job; the monitor keeps running |

**Expandable on request** (state is remembered, closed by default):
- **Job print options:** document format, copies, color mode, resolution, paper size, paper
  source, halftoning, density, print direction and more. Options that are not set show the PPD
  default marked "(default)".
- **Queue:** all jobs of the monitored queues with number, document, user, status and page.
  With a selection you can cancel individual jobs or hold and release them (not running ones).
- **History:** timestamp for every change.

## Tray icon

Icon with a menu: status, show window, print last job again, pause, settings, quit monitor.
While printing, the percentage is shown next to the icon (if the desktop shows labels). The icon
changes on pause and on error. Needs `gir1.2-ayatanaappindicator3-0.1` (recommended by the
package).

## Notifications

Desktop notification "Print finished" (document, pages, duration) and "Print error" (document,
reason). Each can be switched off separately. Needs `gir1.2-notify-0.7` (recommended by the
package). Cancellations by the user do not trigger a notification.

## Settings

Dialog via the window ("Settings …"), the tray menu or `lq300-monitor --settings`. Every change
applies immediately and is stored in `~/.config/lq300-monitor/settings.json`.

| Setting | Default | Meaning |
|---|---|---|
| Show the window automatically for print jobs | on | off: only the icon shows printing, you open the window by hand |
| Bring the window to the front automatically | on | depends on the window manager |
| Keep the window always on top | off | takes effect after restarting the monitor. Under Wayland the monitor uses XWayland for this, because Wayland does not allow it otherwise |
| Hide the window after a successful end after … s | 8 | 0 = never. On error or cancel the window stays |
| Show print status as a tray icon | on | |
| Notify when a print is finished / on errors | on / on | |
| Start the monitor at login | on | writes `~/.config/autostart/lq300-monitor.desktop` (overrides the system file) |
| Monitored queues | empty | empty = all LQ-300; otherwise names separated by commas, takes effect after a restart |
| Quit the monitor now | | stops the service |

## Where progress and remaining time come from

The filters report `job-media-progress` (percent of the current page) and `PAGE:` after every
finished page. The text filter counts the pages beforehand and writes "Page p of n" into the
message; the monitor reads n from there. For graphics n is unknown: percent and remaining time
then apply to the current page (the display says "of this page").

Remaining time: extrapolated from the time spent on the current page and its progress, from 3 %
of the page on (before that "calculating …"). With a known page count, the remaining pages are
added with the same page duration. The graphics filter weights the bands by head passes (empty
bands are only a paper feed), so that the percentage follows the printing time.

## History file

Every change (state, page counter, progress in 10 % steps, filter message, pause, cancel) is
written with a timestamp to `~/.local/state/lq300-monitor/monitor.log`. This makes it possible
to follow when a job stalled or how long a page really took. Demo mode writes to `demo.log`.

## Limits

- **The monitor sees what the filter has sent, not what has been printed.** The printer reports
  nothing back over LPT (no paper-out, no errors). Between filter and paper there are the pipe,
  the network, the print server and the printer buffer. A print server that accepts LPD jobs
  spools the whole job, so a page that takes minutes to print can be "finished" for CUPS (and
  the monitor) after about a second. In that case the monitor works as a "job accepted"
  display; pause, print again and the queue view are still useful. Using the raw port
  (`socket://<host>:9100`) instead of LPD made no difference on the test setup. Very large jobs
  (for example color pages) can exceed the print server's buffer, then the progress follows the
  printing more closely. The history file shows what the monitor saw.
- If CUPS runs on another computer, the monitor has to connect there
  (`CUPS_SERVER=host lq300-monitor`).
- Very short jobs that start and finish between two polls are reported as finished afterwards.
- Pause does not affect the running job, see the button table.

## Ideas for later

- Total page count for graphics too (buffer the raster beforehand).
- Print duration per page as statistics, a test-print button.
