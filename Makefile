# SPDX-License-Identifier: MIT
# Copyright (c) 2026 LQ300II driver contributors
CUPS_FILTERDIR ?= $(shell for d in /usr/lib/cups/filter /usr/libexec/cups/filter; do [ -d $$d ] && echo $$d && break; done)
PPDDIR ?= /usr/share/cups/model

all: rastertoescplq texttoescplq

rastertoescplq: rastertoescplq.c
	$(CC) -O2 -Wall -o $@ $< -lm

texttoescplq: texttoescplq.c charsets.h
	$(CC) -O2 -Wall -o $@ $< -lm

install: all
	install -m 755 -o root -g root rastertoescplq texttoescplq $(CUPS_FILTERDIR)/
	install -m 644 -o root -g root lq300ii.ppd $(PPDDIR)/

check:
	cupstestppd -I filters -W translations lq300ii.ppd

clean:
	rm -f rastertoescplq texttoescplq

install-monitor:
	install -m 755 -o root -g root lq300_monitor.py /usr/bin/lq300-monitor
