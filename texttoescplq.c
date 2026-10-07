/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 LQ300II driver contributors */
/*
 * texttoescplq - CUPS text filter for the Epson LQ-300+II (ESC/P2)
 *
 * Converts UTF-8 text/plain into ESC/P2 using the printer's built-in fonts.
 *
 * Usage (as CUPS filter): texttoescplq job user title copies options [file]
 *
 * Options (PPD or lp -o):
 *   LQCharset  ISO8859-15 | PC858 | PC850 | ISO8859-1 | PC437 | Roman8
 *   LQTypeface Roman Sans Courier Prestige Script OCR-B Orator Orator-S ...
 *   LQQuality  LQ | Draft
 *   LQDirection Bidi | Uni | Auto   (default Adaptive: graphics decide per band, text sends nothing like Auto)
 *   (| is always printed as a solid bar from PC437; the printer font draws it broken)
 *   LQPitch / cpi   10 12 15 17 20
 *   LQLpi / lpi     3 4 5 6 8 9 10 12
 *   page-left page-right page-top page-bottom   (points)
 *   PageSize   A4 A5 Letter Legal Fanfold_A4 Fanfold_210x12 Fanfold_240x12
 *
 * Build: gcc -O2 -o texttoescplq texttoescplq.c
 */
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include "charsets.h"

#define ESC "\033"

static char *options;

static const char *opt(const char *name, const char *def)
{
    static char val[8][64];
    static int slot;
    size_t nl = strlen(name);
    const char *p = options;
    while (p && *p) {
        while (*p == ' ') p++;
        if (!strncmp(p, name, nl) && p[nl] == '=') {
            const char *v = p + nl + 1;
            size_t n = strcspn(v, " ");
            char *dst = val[slot++ & 7];
            if (n >= 64) n = 63;
            memcpy(dst, v, n);
            dst[n] = 0;
            return dst;
        }
        p += strcspn(p, " ");
    }
    return def;
}

static const struct { const char *name; double w, h; } sizes[] = {
    { "A4", 595.28, 841.89 }, { "A5", 419.53, 595.28 },
    { "Letter", 612, 792 }, { "Legal", 612, 1008 },
    { "Fanfold_A4", 595.28, 841.89 }, { "Fanfold_210x12", 595.28, 864 }, { "Fanfold_240x12", 680.31, 864 },
};

static const struct { const char *name; int n; } faces[] = {
    { "Roman", 0 }, { "Sans", 1 }, { "Courier", 2 }, { "Prestige", 3 },
    { "Script", 4 }, { "OCR-B", 5 }, { "OCR-A", 6 }, { "Orator", 7 },
    { "Orator-S", 8 }, { "ScriptC", 9 }, { "RomanT", 10 }, { "SansH", 11 },
};

/* codepoint -> ASCII fallback for characters missing in the code page */
static const char *translit(uint32_t c)
{
    switch (c) {
    case 0x2010: case 0x2011: case 0x2012: case 0x2013: case 0x2014:
    case 0x2212: return "-";
    case 0x2018: case 0x2019: case 0x201a: case 0x2032: return "'";
    case 0x201c: case 0x201d: case 0x201e: case 0x2033: return "\"";
    case 0x2026: return "...";
    case 0x2022: case 0x25cf: case 0x00b7: return "*";
    case 0x20ac: return "EUR";
    case 0x2122: return "(TM)";
    case 0x00a0: case 0x2002: case 0x2003: case 0x2009: return " ";
    case 0x2192: return "->";
    case 0x2190: return "<-";
    case 0x00a6: return "|"; case 0x00a8: return "\"";
    case 0x00b4: return "'"; case 0x00b8: return ",";
    case 0x00bc: return "1/4"; case 0x00bd: return "1/2"; case 0x00be: return "3/4";
    case 0x0141: return "L"; case 0x0142: return "l";
    case 0x0160: return "S"; case 0x0161: return "s";
    case 0x017d: return "Z"; case 0x017e: return "z";
    }
    return "?";
}

static int solid_bar = 1;

/* returns byte (0..255), 0x100|byte for table 2 (PC437), or -1 */
static int map_char(const struct charset *cs, uint32_t c)
{
    if (c == '|' && solid_bar) return 0x100 | 0xb3;
    if (c < 0x80) return (int)c;
    for (int i = 0; i < 128; i++)
        if (cs->hi[i] == c) return 0x80 + i;
    for (int i = 0; i < 128; i++)
        if (alt437[i] == c) return 0x100 | (0x80 + i);
    return -1;
}

/* ---- input ------------------------------------------------------------ */

static uint32_t *cp;
static size_t ncp;

static void read_input(FILE *in)
{
    size_t cap = 1 << 16, n = 0;
    unsigned char *buf = malloc(cap);
    size_t r;
    while ((r = fread(buf + n, 1, cap - n, in)) > 0) {
        n += r;
        if (n == cap) buf = realloc(buf, cap *= 2);
    }
    cp = malloc((n + 1) * sizeof *cp);
    for (size_t i = 0; i < n;) {
        unsigned char b = buf[i];
        uint32_t c = b;
        int len = 1;
        if (b >= 0xc2 && b < 0xe0 && i + 1 < n && (buf[i + 1] & 0xc0) == 0x80) {
            c = (b & 0x1f) << 6 | (buf[i + 1] & 0x3f); len = 2;
        } else if (b >= 0xe0 && b < 0xf0 && i + 2 < n && (buf[i + 1] & 0xc0) == 0x80
                   && (buf[i + 2] & 0xc0) == 0x80) {
            c = (b & 0x0f) << 12 | (buf[i + 1] & 0x3f) << 6 | (buf[i + 2] & 0x3f); len = 3;
        } else if (b >= 0xf0 && b < 0xf5 && i + 3 < n && (buf[i + 1] & 0xc0) == 0x80
                   && (buf[i + 2] & 0xc0) == 0x80 && (buf[i + 3] & 0xc0) == 0x80) {
            c = (b & 0x07) << 18 | (buf[i + 1] & 0x3f) << 12
                | (buf[i + 2] & 0x3f) << 6 | (buf[i + 3] & 0x3f); len = 4;
        }
        cp[ncp++] = c;
        i += len;
    }
    free(buf);
}

/* ---- output ----------------------------------------------------------- */

static void put_units(int v) { putchar(v & 255); putchar((v >> 8) & 255); }

/* ---- line layout (word wrap) ------------------------------------------ */

static unsigned short lbuf[1024];   /* byte | 0x100 = from table 2 (PC437) */
static int alt_active;
static int llen, lastsp, wrapped;
static int cols, left_units, lines_per_page, line, dirty;

/* Progress for CUPS and the status monitor. The layout is run once without output to
 * count the pages (dry), so "Page p of n" is known. job-media-progress is the
 * percentage of the current page. */
static int dry, pages_done, total_pages, prog_pct = -1;

static void report(int pct)
{
    if (dry || pct == prog_pct) return;
    prog_pct = pct;
    fprintf(stderr, "ATTR: job-media-progress=%d\nINFO: Page %d of %d, %d %%\n",
            pct, pages_done + 1, total_pages, pct);
}

static void page_done(void)
{
    report(100);
    pages_done++;
    if (!dry) fprintf(stderr, "PAGE: %d 1\n", pages_done);
    prog_pct = -1;
    if (pages_done < total_pages) report(0);
}

static void emit_line(int len)
{
    while (len > 0 && lbuf[len - 1] == ' ') len--;
    if (len > 0) {
        if (left_units) printf(ESC "$%c%c", left_units & 255, left_units >> 8);
        for (int i = 0; i < len; i++) {
            int alt = (lbuf[i] & 0x100) != 0;
            if (alt != alt_active) { printf(ESC "t%c", alt ? 2 : 3); alt_active = alt; }
            putchar(lbuf[i] & 0xff);
        }
        if (alt_active) { fputs(ESC "t\003", stdout); alt_active = 0; }
        dirty = 1;
    }
}

static void newline(void)
{
    fputs("\r\n", stdout);
    dirty = 1;
    if (++line >= lines_per_page) { putchar('\f'); line = 0; page_done(); }
    else report(line * 100 / lines_per_page);
}

/* finish the current line; nl != 0: also advance to the next line */
static void end_line(int nl)
{
    emit_line(llen);
    llen = 0; lastsp = -1; wrapped = 0;
    if (nl) newline();
}

static void add_byte(int b)
{
    if (llen >= cols) {
        if (b == ' ') { end_line(1); wrapped = 1; return; }
        if (lastsp > 0) {                       /* break at last space */
            int rest = llen - lastsp - 1;
            emit_line(lastsp);
            newline();
            memmove(lbuf, lbuf + lastsp + 1, rest * sizeof *lbuf);
            llen = rest; lastsp = -1;
            for (int i = 0; i < llen; i++) if (lbuf[i] == ' ') lastsp = i;
        } else {                                /* word longer than line */
            emit_line(llen);
            newline();
            llen = 0; lastsp = -1;
        }
        wrapped = 1;
    }
    if (b == ' ' && llen == 0 && wrapped) return;   /* no leading blank after wrap */
    if (b == ' ') lastsp = llen;
    lbuf[llen++] = (unsigned short)b;
}

static void run_job(const struct charset *cs, int copies)
{
    alt_active = 0;
    for (int c = 0; c < copies; c++) {
        line = 0; dirty = 0; llen = 0; lastsp = -1; wrapped = 0;
        for (size_t i = 0; i < ncp; i++) {
            uint32_t ch = cp[i];

            if (ch == '\r') { if (i + 1 < ncp && cp[i + 1] == '\n') continue; ch = '\n'; }
            if (ch == '\f') {
                end_line(0);
                if (dirty || line > 0) { putchar('\f'); line = 0; dirty = 0; page_done(); }
                continue;
            }
            if (ch == '\n') { end_line(1); continue; }

            int reps = 1, out;
            if (ch == '\t') { reps = 8 - llen % 8; out = ' '; }
            else if (ch < 0x20 || ch == 0x7f || (ch >= 0x80 && ch < 0xa0)) continue;
            else out = map_char(cs, ch);

            for (int r = 0; r < reps; r++) {
                if (out >= 0) add_byte(out);
                else for (const char *t = translit(ch); *t; t++) add_byte((unsigned char)*t);
            }
        }
        end_line(0);
        if (dirty && line > 0) { putchar('\f'); page_done(); }
    }
}

int main(int argc, char **argv)
{
    if (argc < 6 || argc > 7) {
        fprintf(stderr, "Usage: %s job user title copies options [file]\n", argv[0]);
        return 1;
    }
    int copies = atoi(argv[4]);
    if (copies < 1) copies = 1;
    options = argv[5];

    FILE *in = stdin;
    if (argc == 7 && !(in = fopen(argv[6], "rb"))) { perror("ERROR: open"); return 1; }
    read_input(in);

    /* options */
    const struct charset *cs = &charsets[0];
    const char *csn = opt("LQCharset", "ISO8859-15");
    for (size_t i = 0; i < sizeof charsets / sizeof *charsets; i++)
        if (!strcmp(charsets[i].name, csn)) cs = &charsets[i];

    int face = 0;
    const char *fn = opt("LQTypeface", "Roman");
    for (size_t i = 0; i < sizeof faces / sizeof *faces; i++)
        if (!strcmp(faces[i].name, fn)) face = faces[i].n;
    int draft = !strcmp(opt("LQQuality", "LQ"), "Draft");

    int cpi = atoi(opt("cpi", opt("LQPitch", "10")));
    if (cpi != 10 && cpi != 12 && cpi != 15 && cpi != 17 && cpi != 20) cpi = 10;
    int lpi = atoi(opt("lpi", opt("LQLpi", "6")));
    if (lpi < 3 || lpi > 12) lpi = 6;
    int line_units = 360 / lpi;

    double pw = 595.28, ph = 841.89;
    const char *psz = opt("PageSize", "A4");
    for (size_t i = 0; i < sizeof sizes / sizeof *sizes; i++)
        if (!strcmp(sizes[i].name, psz)) { pw = sizes[i].w; ph = sizes[i].h; }

    double pl = atof(opt("page-left", "0")), pr = atof(opt("page-right", "0"));
    double pt = atof(opt("page-top", "12")), pb = atof(opt("page-bottom", "18.4"));
    if (pt < 12) pt = 12;
    if (pb < 12) pb = 12;
    double printable = pw - 17.0;
    if (printable > 576.0) printable = 576.0;
    double textw = printable - pl - pr;
    cols = (int)floor(textw / 72.0 * cpi + 1e-6);
    if (cols > (int)sizeof lbuf) cols = sizeof lbuf;
    if (cols < 10) cols = 10;
    left_units = (int)lround(pl * 5.0);

    int page_units = (int)lround(ph * 5.0);
    int top_units = (int)lround(pt * 5.0);
    int bottom_units = page_units - (int)lround(pb * 5.0);
    lines_per_page = (bottom_units - top_units) / line_units;
    if (lines_per_page < 1) lines_per_page = 1;

    /* printer setup */
    fputs(ESC "@\r", stdout);
    if (!strcmp(opt("InputSlot", "Auto"), "Feeder")) fputs(ESC "\031" "1", stdout);   /* ESC EM 1: cut sheet feeder bin 1 */
    { const char *dir = opt("LQDirection", "Adaptive");
      if (!strcmp(dir, "Bidi")) printf(ESC "U%c", 0);
      else if (!strcmp(dir, "Uni")) printf(ESC "U%c", 1); }
    fputs(ESC "(U\001", stdout); putchar(0); putchar(10);       /* unit 1/360" */
    printf(ESC "(t\003%c%c%c%c", 0, 3, cs->d2, cs->d3);         /* table 3 := charset */
    printf(ESC "(t\003%c%c%c%c", 0, 2, 1, 0);              /* table 2 := PC437 (box drawing, bars) */
    fputs(ESC "t\003", stdout);
    fputs(ESC "6", stdout);                                     /* 0x80-0x9f printable */
    fputs(ESC "R", stdout); putchar(0);                          /* country USA */
    fputs(ESC "O", stdout);
    fputs(ESC "(C\002", stdout); putchar(0); put_units(page_units);
    fputs(ESC "(c\004", stdout); putchar(0); put_units(top_units); put_units(bottom_units);
    printf(ESC "x%c", draft ? 0 : 1);
    if (!draft) printf(ESC "k%c", face);
    fputc(0x12, stdout);                                        /* cancel condensed */
    switch (cpi) {
    case 10: case 17: fputs(ESC "P", stdout); break;
    case 12: case 20: fputs(ESC "M", stdout); break;
    case 15: fputs(ESC "g", stdout); break;
    }
    if (cpi == 17 || cpi == 20) fputc(0x0f, stdout);            /* condensed */
    printf(ESC "+%c", line_units);

    /* dry run: count the pages */
    fflush(stdout);
    int saved = dup(1);
    if (saved >= 0 && freopen("/dev/null", "w", stdout)) {
        dry = 1;
        run_job(cs, copies);
        dry = 0;
        total_pages = pages_done;
        pages_done = 0; prog_pct = -1;
        fflush(stdout);
        dup2(saved, 1);
        close(saved);
        clearerr(stdout);
    }
    report(0);
    run_job(cs, copies);
    fputs(ESC "@", stdout);
    fflush(stdout);
    return 0;
}
