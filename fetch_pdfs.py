#!/usr/bin/env python3
"""
Hämtar Skolenkätens totalrapporter (PDF) till raw/ enligt sources.txt.
Kör: python3 fetch_pdfs.py
Format per rad i sources.txt:  <period> <grupp> <url>
"""
import os, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw')
os.makedirs(RAW, exist_ok=True)

with open(os.path.join(HERE, 'sources.txt')) as f:
    rows = [ln.split(None, 2) for ln in f if ln.strip()]

for period, grp, url in rows:
    out = os.path.join(RAW, f'{period}_{grp}.pdf')
    if os.path.exists(out) and os.path.getsize(out) > 0:
        print(f'  finns redan: {os.path.basename(out)}')
        continue
    req = urllib.request.Request(url.strip(), headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        open(out, 'wb').write(data)
        print(f'  hämtad: {os.path.basename(out)}  ({len(data)//1024} kB)')
    except Exception as e:
        print(f'  FEL {os.path.basename(out)}: {e}')

print('Klart. Kör sedan: python3 parse.py && python3 build.py')
