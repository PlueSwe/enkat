#!/usr/bin/env python3
"""
Hämtar Skolenkäten-resultat per kommun från Koladas öppna API (api.kolada.se/v3)
och skriver kolada_data.js (window.KOLADA) för kartfliken.

Frågor (KPI:er): trygghet och nöjdhet för åk 5, åk 8 och gymnasiets år 2.
Värdet är "Andel som svarat Helt och hållet" (%). År 2022–2026.
"""
import json, os, urllib.request, time

HERE = os.path.dirname(os.path.abspath(__file__))

KPIS = [
    dict(id='N15613', tema='Trygghet', grupp='Elever åk 5',  fraga='Känner du dig trygg i skolan?'),
    dict(id='N15643', tema='Trygghet', grupp='Elever åk 8',  fraga='Känner du dig trygg i skolan?'),
    dict(id='N17673', tema='Trygghet', grupp='Gymnasiet år 2', fraga='Känner du dig trygg i skolan?'),
    dict(id='N15629', tema='Nöjdhet',  grupp='Elever åk 5',  fraga='Hur nöjd är du med din skola?'),
    dict(id='N15659', tema='Nöjdhet',  grupp='Elever åk 8',  fraga='Hur nöjd är du med din skola?'),
    dict(id='N17689', tema='Nöjdhet',  grupp='Gymnasiet år 2', fraga='Hur nöjd är du med din skola?'),
]
YEARS = [2022, 2023, 2024, 2025, 2026]

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'skolinsyn/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def is_kommun(code):
    return isinstance(code, str) and len(code) == 4 and code.isdigit() and code != '0000'

def main():
    data = {}          # kpi -> year -> kommunkod -> value(T)
    national = {}       # kpi -> year -> value(T) (kod 0000)
    kommuner = set()
    for kpi in KPIS:
        kid = kpi['id']
        data[kid] = {}
        national[kid] = {}
        for y in YEARS:
            url = f'https://api.kolada.se/v3/data/kpi/{kid}/year/{y}'
            try:
                resp = fetch(url)
            except Exception as e:
                print(f'  FEL {kid}/{y}: {e}'); continue
            ymap = {}
            for row in resp.get('values', []):
                code = row.get('municipality')
                tval = next((v.get('value') for v in row.get('values', [])
                             if v.get('gender') == 'T'), None)
                if tval is None:
                    continue
                if code == '0000':
                    national[kid][str(y)] = round(tval, 1)
                elif is_kommun(code):
                    ymap[code] = round(tval, 1)
                    kommuner.add(code)
            data[kid][str(y)] = ymap
            print(f'  {kid} {y}: {len(ymap)} kommuner  (riket {national[kid].get(str(y))})')
            time.sleep(0.15)

    out = dict(
        generated=time.strftime('%Y-%m-%d'),
        source='Kolada (kolada.se) – Skolinspektionens Skolenkäten per kommun',
        years=YEARS,
        kpis=KPIS,
        national=national,
        data=data,
    )
    js = 'window.KOLADA = ' + json.dumps(out, ensure_ascii=False) + ';\n'
    open(os.path.join(HERE, 'kolada_data.js'), 'w').write(js)
    sz = os.path.getsize(os.path.join(HERE, 'kolada_data.js'))
    print(f'\nKommuner med data: {len(kommuner)}')
    print(f'kolada_data.js: {sz/1024:.0f} kB')

if __name__ == '__main__':
    main()
