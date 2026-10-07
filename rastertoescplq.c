/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 LQ300II driver contributors */
/*
 * rastertoescplq - CUPS raster filter for the Epson LQ-300+II (ESC/P2, 24 pin)
 *
 * Reads CUPS raster (8 bit gray/black, no libcups needed), dithers it to
 * 1 bit and prints it with ESC * 24-pin bit images.
 *
 * Resolutions: 180x180, 360x180, 360x360. 360 dpi is produced by interlacing
 * (the printer cannot fire adjacent dots at 360 dpi in one pass).
 *
 * Usage (as CUPS filter): rastertoescplq job user title copies options [file]
 *
 * Build: gcc -O2 -o rastertoescplq rastertoescplq.c -lm
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif
#include <unistd.h>
#include <fcntl.h>

#define HDR_SIZE_V1 420
#define HDR_SIZE_V2 1796
#define PINS 24

static int swapped;
static int compressed;
static FILE *in;

static uint32_t rd32(const unsigned char *h, int off)
{
    const unsigned char *p = h + off;
    return swapped ? ((uint32_t)p[3] << 24 | p[2] << 16 | p[1] << 8 | p[0])
                   : ((uint32_t)p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3]);
}

static float rdf(const unsigned char *h, int off)
{
    uint32_t u = rd32(h, off);
    float f;
    memcpy(&f, &u, 4);
    return f;
}

/* ---- options ---------------------------------------------------------- */

static char *options;

static const char *opt(const char *name, const char *def)
{
    static char val[16][64];   /* ring: callers keep several results at the same time */
    static int slot;
    size_t nl = strlen(name);
    const char *p = options;
    while (p && *p) {
        while (*p == ' ') p++;
        if (!strncmp(p, name, nl) && p[nl] == '=') {
            const char *v = p + nl + 1;
            size_t n = strcspn(v, " ");
            char *dst = val[slot++ & 15];
            if (n >= 64) n = 63;
            memcpy(dst, v, n);
            dst[n] = 0;
            return dst;
        }
        p += strcspn(p, " ");
    }
    return def;
}

/* ---- raster input ----------------------------------------------------- */

/* Returns 1 on success, 0 on EOF */
static int read_header(unsigned char *h, int first)
{
    unsigned char sync[4];
    if (first) {
        if (fread(sync, 1, 4, in) != 4) return 0;
        if (!memcmp(sync, "RaSt", 4))      { swapped = 0; compressed = 0; }
        else if (!memcmp(sync, "tSaR", 4)) { swapped = 1; compressed = 0; }
        else if (!memcmp(sync, "RaS1", 4)) { swapped = 0; compressed = 1; }
        else if (!memcmp(sync, "1SaR", 4)) { swapped = 1; compressed = 1; }
        else if (!memcmp(sync, "RaS2", 4)) { swapped = 0; compressed = 1; }
        else if (!memcmp(sync, "2SaR", 4)) { swapped = 1; compressed = 1; }
        else if (!memcmp(sync, "RaS3", 4)) { swapped = 0; compressed = 0; }
        else if (!memcmp(sync, "3SaR", 4)) { swapped = 1; compressed = 0; }
        else { fprintf(stderr, "ERROR: unknown raster format\n"); exit(1); }
    }
    memset(h, 0, HDR_SIZE_V2);
    size_t want = HDR_SIZE_V2;
    if (fread(h, 1, want, in) != want) return 0;
    return 1;
}

static int read_full(unsigned char *buf, size_t n)
{
    return fread(buf, 1, n, in) == n;
}

/* Read one line of pixels, honouring CUPS RLE when compressed.
 * Repeat counts are handled by the caller via *repeat. */
static int cur_repeat;

static int read_line(unsigned char *dst, size_t bpl, size_t bpp, int white)
{
    if (!compressed) return read_full(dst, bpl);

    if (cur_repeat > 0) { cur_repeat--; return 1; } /* dst still holds line */

    int c = fgetc(in);
    if (c == EOF) return 0;
    cur_repeat = c;

    size_t pos = 0;
    while (pos < bpl) {
        int n = fgetc(in);
        if (n == EOF) return 0;
        if (n == 128) {
            memset(dst + pos, white, bpl - pos);
            pos = bpl;
        } else if (n < 128) {
            size_t cnt = (size_t)(n + 1) * bpp;
            unsigned char pix[8];
            if (fread(pix, 1, bpp, in) != bpp) return 0;
            for (size_t i = 0; i < (size_t)(n + 1) && pos + bpp <= bpl; i++, pos += bpp)
                memcpy(dst + pos, pix, bpp);
            (void)cnt;
        } else {
            size_t cnt = (size_t)(257 - n) * bpp;
            if (pos + cnt > bpl) cnt = bpl - pos;
            if (!read_full(dst + pos, cnt)) return 0;
            pos += cnt;
        }
    }
    return 1;
}

/* ---- dithering -------------------------------------------------------- */

#define RIDGE_MIN 40      /* minimum ink (0..255) of a hairline pixel */
#define RIDGE_STEP 24     /* how much darker than both neighbours */
#define WHITE_POINT 0.10  /* ink amount below which nothing is printed */
#define EDGE_CONTRAST 90   /* gray difference within 3x3 that counts as an edge */
#define EDGE_DARK 250      /* pure black features (text) always count as edge */
#define THIN_MAX 3         /* thin structure: white within this many pixels on both sides */
#define WHITE_INK 30       /* ink amount up to which a pixel counts as white */
#define EDGE_INK 100       /* raw ink amount (0..255) for a dot on an edge */

static uint8_t lut[256]; /* gray -> ink amount 0..255 after gamma */

/* Tone response measured on the real printer with kalibrierung.pdf (Bayer screen,
 * 360x180, LQDensity=Raw): dot coverage vs. resulting darkness (1.0 = solid black).
 * The printer prints solid black twice, so 100 % is darker than 90 %. The curve is
 * inverted to get evenly spaced tones. */
#define TONE_N 11
static const double tone_cov[TONE_N]  = { 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0 };
static const double tone_dark[TONE_N] = { 0.0, 0.13, 0.22, 0.35, 0.47, 0.62, 0.75, 0.81, 0.86, 0.89, 1.0 };

static double coverage_for(double darkness)
{
    if (darkness <= 0) return 0;
    for (int i = 1; i < TONE_N; i++)
        if (darkness <= tone_dark[i])
            return tone_cov[i - 1] + (tone_cov[i] - tone_cov[i - 1])
                 * (darkness - tone_dark[i - 1]) / (tone_dark[i] - tone_dark[i - 1]);
    return 1.0;
}

/* density: exponent applied to the requested tone (<1 darker, >1 lighter) */
static void build_lut(double density)
{
    if (density <= 0) {                       /* Raw: no tone curve, for calibration */
        for (int g = 0; g < 256; g++) lut[g] = (uint8_t)(255 - g);
        return;
    }
    for (int g = 0; g < 256; g++) {
        double ink = (255 - g) / 255.0;
        /* white point: tones lighter than this cannot be printed cleanly by a dot
         * matrix head, isolated dots in pale halos only look like dirt */
        if (ink < WHITE_POINT) ink = 0;
        lut[g] = (uint8_t)lround(255.0 * coverage_for(pow(ink, density)));
    }
}

/* Colour inks: tone response measured with farbtest_2.pdf (360x180, the ramps were
 * printed with LQDensity=Contrast, i.e. target exponent 1.8 and the black curve above).
 * ramp_dark[ink][k] = darkness of the ramp step k (k/10 of the requested ink, 1.0 = the
 * solid patch), measured with the channel that the ink absorbs. The dot coverage that
 * was printed for each step is recomputed from the curve above, so the pairs
 * (coverage, darkness) describe each ink. The colour LUT inverts them: an ink amount
 * of x prints the coverage that gives darkness x (pale yellow gets many more dots). */
static const double ramp_dark[3][TONE_N] = {
    { 0.0, 0.022, 0.044, 0.099, 0.175, 0.253, 0.387, 0.533, 0.626, 0.814, 1.0 },   /* yellow  */
    { 0.0, 0.029, 0.060, 0.144, 0.266, 0.411, 0.556, 0.633, 0.720, 0.825, 1.0 },   /* magenta */
    { 0.0, 0.030, 0.063, 0.152, 0.286, 0.464, 0.539, 0.618, 0.780, 0.921, 1.0 },   /* cyan    */
};
#define RAMP_DENSITY 1.8          /* LQDensity=Contrast, the setting of the measurement */
#define COLOR_WHITE_POINT 0.04    /* isolated coloured dots on white are hardly visible */

/* ink 0..2 = yellow, magenta, cyan; density as for the black curve (Contrast = 1.8 gives a
 * linear response, other settings scale the exponent around it) */
static void build_ink_lut(int ink, double density)
{
    if (density <= 0) { build_lut(0); return; }
    double cov[TONE_N], dark[TONE_N];
    for (int k = 0; k < TONE_N; k++) {
        cov[k] = k ? coverage_for(pow(k / 10.0, RAMP_DENSITY)) : 0.0;
        dark[k] = ramp_dark[ink][k];
        if (k && dark[k] < dark[k - 1]) dark[k] = dark[k - 1];   /* measurement noise */
    }
    /* the ramp steps below the white point printed nothing in the measurement */
    for (int g = 0; g < 256; g++) {
        double x = (255 - g) / 255.0;
        if (x < COLOR_WHITE_POINT) { lut[g] = 0; continue; }
        double t = pow(x, density / RAMP_DENSITY);
        double c = 1.0;
        for (int k = 1; k < TONE_N; k++)
            if (t <= dark[k]) {
                double span = dark[k] - dark[k - 1];
                c = span > 0 ? cov[k - 1] + (cov[k] - cov[k - 1]) * (t - dark[k - 1]) / span : cov[k];
                break;
            }
        lut[g] = (uint8_t)lround(255.0 * c);
    }
    if (getenv("LQDEBUG")) {
        fprintf(stderr, "ink %d coverage at 10..100 %%:", ink);
        for (int k = 1; k <= 10; k++) fprintf(stderr, " %.0f", lut[255 - (int)lround(k * 25.5)] / 2.55);
        fprintf(stderr, "\n");
    }
}

/* 16x16 Bayer matrix (values 0..255), built by the standard recursion. With an
 * anisotropic dot grid (e.g. 360x180) the matrix cell is stretched over 2 pixels
 * in the finer direction so that a halftone cell is square in physical space. */
static uint8_t bayer16[16][16];
static int cur_hres = 360, cur_vres = 360;
static int cell_x = 1, cell_y = 1;

static void build_bayer(int hres, int vres)
{
    int m[16][16] = { { 0 } };
    for (int n = 1; n < 16; n *= 2)
        for (int j = 0; j < n; j++)
            for (int i = 0; i < n; i++) {
                int v = m[j][i] * 4;
                m[j][i] = v;
                m[j][i + n] = v + 2;
                m[j + n][i] = v + 3;
                m[j + n][i + n] = v + 1;
            }
    for (int j = 0; j < 16; j++)
        for (int i = 0; i < 16; i++) bayer16[j][i] = (uint8_t)m[j][i];
    cur_hres = hres; cur_vres = vres;
    cell_x = hres > vres ? hres / vres : 1;
    cell_y = vres > hres ? vres / hres : 1;
}

/* 45 degree clustered-dot screen, period CLUSTER_PERIOD in 1/360 inch. Ink merges
 * into round dots, which suits the large, overlapping dots of a needle head. */
#define CLUSTER_PERIOD 8.0
static int use_cluster;

static int cluster_thr(int x, int y)
{
    double X = x * (360.0 / cur_hres), Y = y * (360.0 / cur_vres);
    double u = (X + Y) * 0.70710678, v = (X - Y) * 0.70710678;
    double spot = 0.5 + 0.25 * (cos(2 * M_PI * u / CLUSTER_PERIOD) + cos(2 * M_PI * v / CLUSTER_PERIOD));
    int t = (int)lround((1.0 - spot) * 255.0);
    return t < 0 ? 0 : t > 255 ? 255 : t;
}

/* Colour planes use the same screen shifted in threshold, so that dots of different
 * inks avoid each other (a shift of a third of the range keeps them disjoint up to
 * a combined coverage of 100 %). 0 for black / monochrome. */
static int thr_shift;

static int bayer_thr(int x, int y)
{
    int t = use_cluster ? cluster_thr(x, y) : bayer16[(y / cell_y) & 15][(x / cell_x) & 15];
    return thr_shift ? (t + thr_shift) & 255 : t;
}

/* gray: w*h bytes (255 = white) -> bits: w*h bytes 0/1 (1 = dot) */
static void dither(const unsigned char *gray, unsigned char *bits, int w, int h,
                   const char *method)
{
    if (!strcmp(method, "FloydSteinberg")) {
        int *err = calloc((size_t)(w + 2) * 2, sizeof(int));
        int *cur = err, *nxt = err + (w + 2);
        for (int y = 0; y < h; y++) {
            int ltr = !(y & 1);
            for (int i = 0; i < w + 2; i++) nxt[i] = 0;
            for (int i = 0; i < w; i++) {
                int x = ltr ? i : w - 1 - i;
                int v = lut[gray[(size_t)y * w + x]] + cur[x + 1] / 16;
                int on = v >= 128;
                int e = v - (on ? 255 : 0);
                bits[(size_t)y * w + x] = on;
                int d = ltr ? 1 : -1;
                cur[x + 1 + d] += e * 7;
                nxt[x + 1 - d] += e * 3;
                nxt[x + 1]     += e * 5;
                nxt[x + 1 + d] += e * 1;
            }
            int *t = cur; cur = nxt; nxt = t;
        }
        free(err);
    } else if (!strcmp(method, "Threshold")) {
        for (size_t i = 0; i < (size_t)w * h; i++)
            bits[i] = lut[gray[i]] >= 128;
    } else if (!strcmp(method, "Auto") || !strcmp(method, "Cluster")) {
        use_cluster = !strcmp(method, "Cluster");
        /* edge aware: hard threshold at strong contrast (text, lines),
         * ordered dither in smooth areas (gradients, gray fills) */
        unsigned char *mn = malloc((size_t)w * h), *mx = malloc((size_t)w * h);
        unsigned char *tmn = malloc((size_t)w * h), *tmx = malloc((size_t)w * h);
        for (int y = 0; y < h; y++)                      /* horizontal 3 */
            for (int x = 0; x < w; x++) {
                int a = gray[(size_t)y * w + (x > 0 ? x - 1 : x)];
                int b = gray[(size_t)y * w + x];
                int c = gray[(size_t)y * w + (x < w - 1 ? x + 1 : x)];
                tmn[(size_t)y * w + x] = a < b ? (a < c ? a : c) : (b < c ? b : c);
                tmx[(size_t)y * w + x] = a > b ? (a > c ? a : c) : (b > c ? b : c);
            }
        for (int y = 0; y < h; y++)                      /* vertical 3 */
            for (int x = 0; x < w; x++) {
                int y0 = y > 0 ? y - 1 : y, y1 = y < h - 1 ? y + 1 : y;
                int a = tmn[(size_t)y0 * w + x], b = tmn[(size_t)y * w + x], c = tmn[(size_t)y1 * w + x];
                mn[(size_t)y * w + x] = a < b ? (a < c ? a : c) : (b < c ? b : c);
                a = tmx[(size_t)y0 * w + x]; b = tmx[(size_t)y * w + x]; c = tmx[(size_t)y1 * w + x];
                mx[(size_t)y * w + x] = a > b ? (a > c ? a : c) : (b > c ? b : c);
            }
        /* edge map: strong contrast AND (pure black OR thin structure). Borders of broad
         * gray fills are not edges, otherwise they get a solid rim around a halftone. */
        unsigned char *edge = calloc((size_t)w * h, 1);
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                size_t i = (size_t)y * w + x;
                if (mx[i] - mn[i] <= EDGE_CONTRAST) continue;
                if (255 - mn[i] >= EDGE_DARK) { edge[i] = 1; continue; }
                int lw = 0, rw = 0, uw = 0, dw = 0;
                for (int k = 1; k <= THIN_MAX; k++) {
                    if (x - k >= 0 && 255 - gray[i - k] <= WHITE_INK) lw = 1;
                    if (x + k < w  && 255 - gray[i + k] <= WHITE_INK) rw = 1;
                    if (y - k >= 0 && 255 - gray[i - (size_t)k * w] <= WHITE_INK) uw = 1;
                    if (y + k < h  && 255 - gray[i + (size_t)k * w] <= WHITE_INK) dw = 1;
                }
                if ((lw && rw) || (uw && dw)) edge[i] = 1;
            }
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                size_t i = (size_t)y * w + x;
                if (edge[i])
                    bits[i] = (255 - gray[i]) >= EDGE_INK;   /* raw ink: independent of the tone curve */
                else /* flat area: both pixels of a halftone cell get the same value so
                      * that they can be printed as one 180 dpi dot */
                    bits[i] = lut[gray[i - (cell_x > 1 ? x % cell_x : 0)]] > bayer_thr(x, y);
                /* hairlines: a pixel darker than both neighbours across a line is part
                 * of a line thinner than the device pixel; print it as a full dot */
                if (!bits[i] && x > 0 && x < w - 1 && y > 0 && y < h - 1) {
                    int ink = 255 - gray[i];
                    int up = 255 - gray[i - w], dn = 255 - gray[i + w];
                    int lf = 255 - gray[i - 1], rt = 255 - gray[i + 1];
                    if (ink >= RIDGE_MIN && ((ink - up >= RIDGE_STEP && ink - dn >= RIDGE_STEP) ||
                                             (ink - lf >= RIDGE_STEP && ink - rt >= RIDGE_STEP)))
                        bits[i] = 1;
                }
            }
        /* despeckle: drop dots on edges that have no neighbour at all (ink bleed
         * makes such isolated dots look like dirt), keep them in gradients */
        unsigned char *keep = malloc((size_t)w * h);
        memcpy(keep, bits, (size_t)w * h);
        for (int y = 1; y < h - 1; y++)
            for (int x = 1; x < w - 1; x++) {
                size_t i = (size_t)y * w + x;
                if (!keep[i] || !edge[i]) continue;
                int n = keep[i - 1] + keep[i + 1] + keep[i - w] + keep[i + w]
                      + keep[i - w - 1] + keep[i - w + 1] + keep[i + w - 1] + keep[i + w + 1];
                if (n == 0) bits[i] = 0;
            }
        free(keep);
        free(mn); free(mx); free(tmn); free(tmx); free(edge);
    } else { /* Bayer */
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                int t = bayer_thr(x, y);
                bits[(size_t)y * w + x] = lut[gray[(size_t)y * w + x]] > t;
            }
    }
}

/* ---- printer output --------------------------------------------------- */

#define ESC "\033"

static void feed(int units360)
{
    while (units360 > 0) {
        int n = units360 > 255 ? 255 : units360;
        printf(ESC "+%c\n", n);
        units360 -= n;
    }
}

/*
 * bits: w*h, 1 byte per pixel. hres,vres in {180,360}.
 * left_units: raster column 0 sits at this printer position in 1/hres inch.
 */
/* Print one 24-pin pass of columns [xa, xb) of the given band row set.
 * Modes: 39 = 180 dpi (one pixel pair per column), 40 = 360 dpi (only columns with
 * (x % 2) == par are printed, the printer cannot fire adjacent dots at 360 dpi). */
#define TOF_UNITS   60    /* first printable row of a sheet: 12 pt (4.2 mm), measured (ausdruck22) */
#define TOF_TRACTOR 127   /* tractor paper as loaded: first row 9 mm below the perforation */
#define ORIGIN_UNITS 85  /* head x = 0 lies about 6 mm right of the sheet edge (1/360") */
#define ORIGIN_TRACTOR 33 /* same for 210 mm tractor paper as loaded (about 2.3 mm), measured */
static int left_off60 = 0;    /* shift of the whole image, 1/60" */
static double skip_inch = 0.25;  /* empty stretches longer than this are jumped over */

static void emit_columns(const unsigned char *bits, int w, int h, int base, int vi, int vj,
                         int mode, int sx, int xa, int xb, int par, unsigned char *data)
{
    /* sx: pixels per printed column (2 = merged pixel pair at 180 dpi) */
    int per60 = mode == 39 ? 3 : mode == 33 ? 2 : 6;  /* columns per 1/60 inch */
    int c0 = xa / sx, c1 = (xb + sx - 1) / sx;   /* column range */
    int first = -1, last = -1;
    for (int c = c0; c < c1; c++) {
        if (mode == 40 && par >= 0 && (c % 2) != par) continue;
        for (int p = 0; p < PINS; p++) {
            int r = base + vi * p + vj;
            if (r < h && c * sx < w && bits[(size_t)r * w + (size_t)c * sx]) {
                if (first < 0) first = c;
                last = c;
                break;
            }
        }
    }
    if (first < 0) return;

    /* split at long empty stretches: the head then jumps (ESC $) instead of
     * sweeping through blank columns at printing speed */
    int cols_per_inch = mode == 39 ? 180 : mode == 33 ? 120 : 360;
    int gap = (int)(skip_inch * cols_per_inch);
    if (gap < 1) gap = 1;
    int c = first;
    while (c <= last) {
        /* find segment [seg_a, seg_b] */
        int seg_a = -1, seg_b = -1;
        for (; c <= last; c++) {
            if (mode == 40 && par >= 0 && (c % 2) != par) continue;
            int on = 0;
            for (int p = 0; p < PINS && !on; p++) {
                int r = base + vi * p + vj;
                on = r < h && c * sx < w && bits[(size_t)r * w + (size_t)c * sx];
            }
            if (!on) continue;
            if (seg_a < 0) seg_a = c;
            else if (c - seg_b > gap) break;
            seg_b = c;
        }
        if (seg_a < 0) break;
        int u = seg_a / per60;
        int start = u * per60;
        int n = seg_b - start + 1;
        for (int i = 0; i < n; i++) {
            int cc = start + i;
            unsigned char b0 = 0, b1 = 0, b2 = 0;
            if (cc >= c0 && cc < c1 && cc * sx < w && !(mode == 40 && par >= 0 && (cc % 2) != par)) {
                for (int p = 0; p < PINS; p++) {
                    int r = base + vi * p + vj;
                    if (r < h && bits[(size_t)r * w + (size_t)cc * sx]) {
                        if (p < 8)       b0 |= 0x80 >> p;
                        else if (p < 16) b1 |= 0x80 >> (p - 8);
                        else             b2 |= 0x80 >> (p - 16);
                    }
                }
            }
            data[i * 3] = b0; data[i * 3 + 1] = b1; data[i * 3 + 2] = b2;
        }
        { int uu = u + left_off60; printf(ESC "$%c%c", uu & 255, uu >> 8); }
        printf(ESC "*%c%c%c", mode, n & 255, n >> 8);
        fwrite(data, 3, n, stdout);
    }
}

#define MERGE_MIN_PAIRS 180   /* only merge runs of at least 1 inch (360 dpi: 2 px per pair) */

static int one_pass = 1;      /* Windows-like: one ESC * 40 with all columns per band */
static int allow_merge = 0;   /* no gain: the printer merges both passes in its line buffer */

static int adaptive_dir = 0;  /* LQDirection=Adaptive: uni for bands with fine vertical structure */
static int bidi_mode = 0;     /* LQDirection=Bidi: colour bands still print unidirectional (registration) */
static double dir_tol_mm = 25.4 / 18;   /* LQDirTol: shortest vertical edge that forces a band unidirectional */
static int dir_halo = 1;                /* LQDirHalo: 1 = neighbour bands of an aligned band are aligned too */
static int cur_uni = -1;
static long n_uni_bands = 0, n_bidi_bands = 0;

/* A band needs exact dot alignment (unidirectional) when a vertical edge (a set pixel
 * with an empty pixel to its left or right) runs for at least ~1.4 mm through it:
 * vertical lines, bar codes, stems of letters, borders of solid areas. The window
 * reaches beyond the band, so a stem that only ends in this band stays aligned. */
static int band_needs_uni(const unsigned char *bits, int w, int h, int base, int band, int vres)
{
    int run_min = (int)lround(dir_tol_mm * vres / 25.4);   /* default 10 rows at 180 dpi, 20 at 360 dpi */
    if (run_min < 1) run_min = 1;
    int r0 = base - run_min, r1 = base + band + run_min;
    if (r0 < 0) r0 = 0;
    if (r1 > h) r1 = h;
    for (int x = 0; x < w; x++) {
        int run = 0, hit = 0;
        for (int r = r0; r < r1; r++) {
            const unsigned char *row = bits + (size_t)r * w;
            int on = row[x] && ((x == 0 || !row[x - 1]) || (x == w - 1 || !row[x + 1]));
            if (on) {
                run++;
                if (r >= base && r < base + band) hit = 1;
                if (run >= run_min && hit) return 1;
            } else { run = 0; hit = 0; }
        }
    }
    return 0;
}

/* One printing pass of a band (interlace row vj): all columns of one ink plane. */
static void print_pass(const unsigned char *bits, int w, int h, int hres, int vres,
                       int base, int vj, unsigned char *data, unsigned char *eq)
{
    int vi = vres / 180;
    int npairs = (w + 1) / 2;
    if (hres < 360) {                         /* 120/180 dpi: a single pass */
        emit_columns(bits, w, h, base, vi, vj, hres == 120 ? 33 : 39, 1, 0, w, 0, data);
        return;
    }
    /* 360 dpi: pixel pairs that are identical can be printed at 180 dpi in
     * one pass (same result), the rest needs the even/odd double pass */
    for (int k = 0; k < npairs; k++) {
        int e = 1;
        for (int p = 0; p < PINS && e; p++) {
            int r = base + vi * p + vj;
            if (r < h && 2 * k + 1 < w &&
                bits[(size_t)r * w + 2 * k] != bits[(size_t)r * w + 2 * k + 1]) e = 0;
        }
        eq[k] = e;
    }
    /* short equal runs are not worth an extra head movement */
    for (int k = 0; k < npairs;) {
        int e = k;
        while (e < npairs && eq[e] == eq[k]) e++;
        if (eq[k] && (e - k < MERGE_MIN_PAIRS || !allow_merge))
            for (int j = k; j < e; j++) eq[j] = 0;
        k = e;
    }
    for (int k = 0; k < npairs;) {
        int e = k;
        while (e < npairs && eq[e] == eq[k]) e++;
        int xa = 2 * k, xb = 2 * e < w ? 2 * e : w;
        if (eq[k]) {
            emit_columns(bits, w, h, base, vi, vj, 39, 2, xa, xb, 0, data);
        } else {
            if (one_pass) {
                emit_columns(bits, w, h, base, vi, vj, 40, 1, xa, xb, -1, data);
            } else {
                emit_columns(bits, w, h, base, vi, vj, 40, 1, xa, xb, 0, data);
                emit_columns(bits, w, h, base, vi, vj, 40, 1, xa, xb, 1, data);
            }
        }
        k = e;
    }
}

static int band_has_dots(const unsigned char *bits, int w, int h, int base, int band)
{
    for (int r = base; r < base + band && r < h; r++) {
        const unsigned char *row = bits + (size_t)r * w;
        for (int x = 0; x < w; x++) if (row[x]) return 1;
    }
    return 0;
}

/* Ink planes. Plane 0 is the only one for monochrome jobs (no colour commands at
 * all). For colour the planes are printed in this order, lightest ink first so that
 * the ribbon stripes stay clean: yellow, magenta, cyan, black. */
#define MAXPLANES 4
static const char plane_esc_r[MAXPLANES] = { 4, 1, 2, 0 };      /* ESC r n: yellow, magenta, cyan, black */
static long n_color_passes;

/* Progress for CUPS (and the status monitor): job-media-progress is the percentage of the
 * current page; a page counts as completed (PAGE:) only after its last band was written.
 * Reported in steps of 2 %. */
static int cur_page, prog_pct = -1;

static void progress(double done, double total)
{
    int pct = total > 0 ? (int)(100.0 * done / total) : 100;
    if (pct > 100) pct = 100;
    pct -= pct % 2 && pct < 100;
    if (pct == prog_pct) return;
    prog_pct = pct;
    fprintf(stderr, "ATTR: job-media-progress=%d\nINFO: Page %d, %d %%\n", pct, cur_page, pct);
}

static void print_page(unsigned char **planes, int nplanes, int w, int h, int hres, int vres,
                       int top_units360)
{
    int vi = vres / 180;  /* vertical interlace passes   */
    int band = PINS * vi; /* raster rows per band        */
    int band_units = 2 * PINS;                      /* 48/360 inch */
    int pending = top_units360;
    int npairs = (w + 1) / 2;
    unsigned char *data = malloc((size_t)w * 3 + 8);
    unsigned char *eq = malloc((size_t)npairs);
    int nbands = (h + band - 1) / band;
    unsigned char *uni_flag = NULL;
    int color = nplanes > 1;
    unsigned char *black = planes[nplanes - 1];    /* the last plane is always black */
    int dyn_dir = adaptive_dir || (bidi_mode && color);   /* direction chosen per band */
    /* print time per band is roughly the number of head passes; blank bands only feed */
    double wtot = 0, wdone = 0;
    float *bw = malloc(sizeof(float) * ((size_t)nbands + 1));
    for (int b = 0; b < nbands; b++) {
        int np = 0;
        for (int p = 0; p < nplanes; p++) np += band_has_dots(planes[p], w, h, b * band, band);
        bw[b] = 0.1f + (np ? vi * (color ? np : 1) : 0);
        wtot += bw[b];
    }
    prog_pct = -1;
    progress(0, wtot);
    if (dyn_dir) {     /* a band next to an aligned one stays aligned: stems end cleanly */
        uni_flag = calloc((size_t)nbands + 2, 1);
        for (int b = 0; b < nbands; b++) {
            int u = adaptive_dir && band_needs_uni(black, w, h, b * band, band, vres);
            /* colour passes are separate head passes: only unidirectional printing
             * keeps the inks on top of each other */
            for (int p = 0; p < nplanes - 1 && !u; p++)
                u = band_has_dots(planes[p], w, h, b * band, band);
            uni_flag[b + 1] = u;
        }
    }

    for (int base = 0; base < h; base += band) {
        /* empty band? */
        int empty = 1;
        for (int p = 0; p < nplanes && empty; p++)
            empty = !band_has_dots(planes[p], w, h, base, band);
        if (empty) {
            pending += band_units;
            wdone += bw[base / band];
            progress(wdone, wtot);
            continue;
        }
        feed(pending);
        pending = 0;
        if (dyn_dir) {
            int b = base / band + 1;
            int u = uni_flag[b] || (adaptive_dir && dir_halo && (uni_flag[b - 1] || uni_flag[b + 1]));
            if (u != cur_uni) { printf(ESC "U%c", u); cur_uni = u; }
            if (u) n_uni_bands++; else n_bidi_bands++;
            if (getenv("LQDEBUG")) fprintf(stderr, "band %d y=%.1fmm %s\n", base / band, base * 25.4 / vres, u ? "uni" : "bidi");
        }

        for (int vj = 0; vj < vi; vj++) {
            for (int p = 0; p < nplanes; p++) {
                if (color && !band_has_dots(planes[p], w, h, base, band)) continue;
                if (color) printf(ESC "r%c", plane_esc_r[MAXPLANES - nplanes + p]);
                print_pass(planes[p], w, h, hres, vres, base, vj, data, eq);
                if (color) n_color_passes++;
            }
            /* like the Windows driver: colours follow each other without CR, the printer
             * collects them in its line buffer; one CR after the last colour of the row */
            if (color) fputc('\r', stdout);
            if (vj + 1 < vi) feed(1);
        }
        pending = band_units - (vi - 1);
        if (pending) { feed(pending); pending = 0; }
        wdone += bw[base / band];
        progress(wdone, wtot);
    }
    progress(1, 1);
    free(bw);
    if (color) printf(ESC "r%c", 0);
    free(data); free(eq); free(uni_flag);
    fputc('\r', stdout);
}

/* Colour separation to the four inks of the colour ribbon (0 = no ink, 255 = full).
 * out[0..3] = yellow, magenta, cyan, black. The black ribbon stripe is much stronger
 * than any CMY mix, so the neutral share of a colour (gcr = 1: all of it) is printed
 * with black only. That keeps gray tones and black text free of colour fringes and
 * saves head passes. Input: RGB (ncomp 3) or CMYK (ncomp 4). */
static void separate(const unsigned char *raw, int ncomp, int w, int h,
                     unsigned char **out, double gcr)
{
    for (size_t i = 0; i < (size_t)w * h; i++) {
        int c, m, y, k = 0;
        if (ncomp == 3) {
            c = 255 - raw[i * 3]; m = 255 - raw[i * 3 + 1]; y = 255 - raw[i * 3 + 2];
            int mn = c < m ? (c < y ? c : y) : (m < y ? m : y);
            k = (int)lround(mn * gcr);
            c -= k; m -= k; y -= k;
        } else {
            c = raw[i * 4]; m = raw[i * 4 + 1]; y = raw[i * 4 + 2]; k = raw[i * 4 + 3];
        }
        out[0][i] = (unsigned char)y;
        out[1][i] = (unsigned char)m;
        out[2][i] = (unsigned char)c;
        out[3][i] = (unsigned char)k;
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

    if (argc == 7) {
        in = fopen(argv[6], "rb");
        if (!in) { perror("ERROR: open"); return 1; }
    } else in = stdin;

    const char *dm = opt("LQDither", "Auto");
    const char *dens = opt("LQDensity", "Contrast");
    double density = !strcmp(dens, "Raw") ? 0 : !strcmp(dens, "Contrast") ? 1.8 : !strcmp(dens, "Light") ? 1.3 : !strcmp(dens, "Dark") ? 0.8 : 1.0;
    build_lut(density);
    const char *dir = opt("LQDirection", "Adaptive");
    allow_merge = !strcmp(opt("LQMerge", "On"), "On");
    skip_inch = atof(opt("LQSkip", "0.25"));   /* 100 = never split */
    int one_pass_opt = strcmp(opt("LQOnePass", "On"), "Off") != 0;
    one_pass = one_pass_opt;
    double gcr = atof(opt("LQGcr", "100")) / 100.0;   /* share of neutral colour printed as black */
    if (gcr < 0) gcr = 0;
    if (gcr > 1) gcr = 1;

    static unsigned char hdr[HDR_SIZE_V2];
    int first = 1, page = 0;
    int printer_init = 0;

    while (read_header(hdr, first)) {
        first = 0;
        int w = rd32(hdr, 372), h = rd32(hdr, 376);
        int hres = rd32(hdr, 276), vres = rd32(hdr, 280);
        int bpc = rd32(hdr, 384), bpp_bits = rd32(hdr, 388);
        size_t bpl = rd32(hdr, 392);
        int cs = rd32(hdr, 400);
        float pageW = rdf(hdr, 428), pageH = rdf(hdr, 432);
        float bboxL = rdf(hdr, 436), bboxT = rdf(hdr, 448);
        (void)pageW;

        /* 0 = W, 3 = K (gray), 1/19 = RGB/sRGB, 6 = CMYK */
        int ncomp = (cs == 0 || cs == 3) ? 1 : (cs == 1 || cs == 19) ? 3 : cs == 6 ? 4 : 0;
        if (bpc != 8 || !ncomp || bpp_bits != 8 * ncomp) {
            fprintf(stderr, "ERROR: need 8 bit gray, RGB or CMYK raster (bpc=%d bpp=%d cs=%d)\n",
                    bpc, bpp_bits, cs);
            return 1;
        }
        if (hres != 120 && hres != 180 && hres != 360) hres = 180;
        if (vres != 180 && vres != 360) vres = 180;
        /* 360 dpi vertical already prints every band in two interlaced passes, a
         * further even/odd split ("Intensiv") only slows the job down */
        one_pass = one_pass_opt || vres == 360;
        if (!one_pass_opt && vres == 360)
            fprintf(stderr, "INFO: LQOnePass=Off (Intensiv) ignored at 360x360 dpi\n");

        if (!printer_init) {
            printf(ESC "@");
            if (!strcmp(opt("InputSlot", "Auto"), "Feeder")) printf(ESC "\031" "1");   /* ESC EM 1: cut sheet feeder bin 1 */
            if (!strcmp(dir, "Bidi")) { printf(ESC "U%c", 0); bidi_mode = 1; }     /* bidirectional: faster */
            else if (!strcmp(dir, "Uni")) printf(ESC "U%c", 1); /* exact dot alignment */
            else if (!strcmp(dir, "Adaptive")) adaptive_dir = 1;   /* chosen per band */
            dir_tol_mm = atof(opt("LQDirTol", "1.41"));
            if (dir_tol_mm < 0.1) dir_tol_mm = 25.4 / 18;
            dir_halo = strcmp(opt("LQDirHalo", "1"), "0") != 0;
            /* Auto: leave to the printer setting */
            printf(ESC "O");                 /* cancel skip over perforation */
            printf(ESC "2");                 /* 1/6" line spacing */
            int lines = (int)lround(pageH / 72.0 * 6.0);
            if (lines > 127) lines = 127;
            if (lines > 0) printf(ESC "C%c", lines);
            printer_init = 1;
        }

        unsigned char *raw = malloc((size_t)w * h * ncomp);
        unsigned char *line = malloc(bpl);
        if (!raw || !line) { fprintf(stderr, "ERROR: out of memory\n"); return 1; }
        int white = cs == 0 || cs == 1 || cs == 19 ? 0xff : 0x00;
        memset(line, white, bpl);
        cur_repeat = 0;
        int ok = 1;
        for (int y = 0; y < h && ok; y++) {
            ok = read_line(line, bpl, ncomp, white);
            if (!ok) break;
            memcpy(raw + (size_t)y * w * ncomp, line, (size_t)w * ncomp);
        }
        if (!ok) { fprintf(stderr, "ERROR: truncated raster data\n"); return 1; }

        if (ncomp > 1 && vres == 360)
            fprintf(stderr, "WARNING: colour at 360x360 dpi prints every colour twice per band "
                            "and wears the colour ribbon; 360x180 dpi is recommended\n");

        /* ink planes: 1 (black) for gray input, 4 (Y M C K) for colour input */
        int nplanes = ncomp == 1 ? 1 : MAXPLANES;
        unsigned char *planes[MAXPLANES] = { 0 };
        build_bayer(hres, vres);
        if (nplanes == 1) {
            unsigned char *gray = malloc((size_t)w * h);
            for (size_t i = 0; i < (size_t)w * h; i++)
                gray[i] = cs == 0 ? raw[i] : 255 - raw[i];
            planes[MAXPLANES - 1] = malloc((size_t)w * h);
            dither(gray, planes[MAXPLANES - 1], w, h, dm);
            free(gray);
        } else {
            unsigned char *ink[MAXPLANES];
            for (int p = 0; p < MAXPLANES; p++) ink[p] = malloc((size_t)w * h);
            separate(raw, ncomp, w, h, ink, gcr);
            /* dither each ink as a gray plane (255 = white); the plane order is Y M C K */
            static const int shifts[MAXPLANES] = { 170, 85, 0, 0 };
            for (int p = 0; p < MAXPLANES; p++) {
                for (size_t i = 0; i < (size_t)w * h; i++) ink[p][i] = 255 - ink[p][i];
                planes[p] = malloc((size_t)w * h);
                thr_shift = shifts[p];
                if (p < 3) build_ink_lut(p, density); else build_lut(density);
                dither(ink[p], planes[p], w, h, dm);
                free(ink[p]);
            }
            thr_shift = 0;
        }
        free(raw); free(line);

        /* PPD margins are measured from the paper edge, the printer starts at its
         * top of form and at its x origin: subtract both */
        int tof = bboxL > 20 ? TOF_TRACTOR : TOF_UNITS;   /* tractor formats have bboxL >= 13 mm */
        int top_units = (int)lround((pageH - bboxT) * 5.0 + atof(opt("LQShiftY", "0")) * 360 / 25.4) - tof;
        if (top_units < 0) top_units = 0;
        int origin = bboxL > 20 ? ORIGIN_TRACTOR : ORIGIN_UNITS;   /* tractor formats have bboxL >= 13 mm */
        left_off60 = (int)lround(((bboxL * 5.0 - origin) + atof(opt("LQShiftX", "0")) * 360 / 25.4) / 6.0);
        if (left_off60 < 0) left_off60 = 0;
        page++;
        cur_page = page;
        for (int c = 0; c < copies; c++) {
            print_page(planes + (MAXPLANES - nplanes), nplanes, w, h, hres, vres, top_units);
            fputc('\f', stdout);
        }
        fflush(stdout);
        fprintf(stderr, "PAGE: %d %d\n", page, copies);
        for (int p = 0; p < MAXPLANES; p++) free(planes[p]);
    }
    if (n_color_passes)
        fprintf(stderr, "INFO: %ld colour passes\n", n_color_passes);
    if (n_uni_bands + n_bidi_bands)
        fprintf(stderr, "INFO: Direction per band: %ld bands unidirectional, %ld bidirectional\n", n_uni_bands, n_bidi_bands);
    if (printer_init) printf(ESC "@");
    fflush(stdout);
    return 0;
}
