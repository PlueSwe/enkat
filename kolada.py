#!/usr/bin/env python3
"""
Hämtar Skolenkäten-resultat per kommun från Koladas öppna API (api.kolada.se/v3)
och skriver kolada_data.js (window.KOLADA) för kartfliken.

Frågor (KPI:er): trygghet och nöjdhet för åk 5, åk 8 och gymnasiets år 2.
Värdet är "Andel som svarat Helt och hållet" (%). År 2022–2026.
"""
import json, os, urllib.request, time

HERE = os.path.dirname(os.path.abspath(__file__))

# Tema -> fråga -> KPI per årskurs (Kolada-koder). Värde = andel "Helt och hållet" (%).
THEMES = [
    dict(tema='Trygghet', fraga='Känner du dig trygg i skolan?',
         kpi=dict(ak5='N15613', ak8='N15643', gy2='N17673')),
    dict(tema='Studiero', fraga='Hur ofta är det arbetsro på lektionerna?',
         kpi=dict(ak5='N15603', ak8='N15633', gy2='N17663')),
    dict(tema='Förhindra kränkningar',
         fraga='Litar du på att de vuxna gör tillräckligt om någon elev blir kränkt?',
         kpi=dict(ak5='N15614', ak8='N15644', gy2='N17674')),
    dict(tema='Elevhälsa', fraga='Hur lätt är det att få hjälp av elevhälsan?',
         kpi=dict(ak5='N15608', ak8='N15638', gy2='N17668')),
    dict(tema='Stimulans', fraga='Hur ofta får lärarna dig att bli intresserad av skolarbetet?',
         kpi=dict(ak5='N15602', ak8='N15632', gy2='N17662')),
    dict(tema='Nöjdhet', fraga='Hur nöjd är du med din skola?',
         kpi=dict(ak5='N15629', ak8='N15659', gy2='N17689')),
]
GRADE_LABEL = {'ak5': 'Åk 5', 'ak8': 'Åk 8', 'gy2': 'Gymnasiet år 2'}
YEARS = [2022, 2023, 2024, 2025, 2026]

# platt lista av alla KPI:er att hämta
KPIS = []
for th in THEMES:
    for g, kid in th['kpi'].items():
        KPIS.append(dict(id=kid, tema=th['tema'], grade=g,
                         grupp='Elever ' + GRADE_LABEL[g], fraga=th['fraga']))

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
        themes=THEMES,
        grade_label=GRADE_LABEL,
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
