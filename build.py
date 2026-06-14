#!/usr/bin/env python3
"""
Normaliserar parse.py:s rådata till ett kompakt dataset för dashboarden.
Skriver data/skolenkaten_data.js  (window.SKOLDATA = {...}).
"""
import json, os, re, statistics, datetime
from collections import defaultdict, OrderedDict

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, 'data')

rows    = json.load(open(os.path.join(DATA, 'rows_raw.json')))
trends  = json.load(open(os.path.join(DATA, 'trends_raw.json')))
oindex  = json.load(open(os.path.join(DATA, 'oindex_raw.json')))

# ---------------------------------------------------------------------------
# Kanonisering av områdesnamn. Fixar trunkeringar och samlar stabila teman.
# ---------------------------------------------------------------------------
CANON = {
    # stabila teman (finns i flera eror)
    'Trygghet': 'Trygghet',
    'Trygghet och studiero': 'Trygghet',
    'Studiero': 'Studiero',
    'Arbetsro': 'Studiero',
    'Ordningsregler': 'Ordningsregler',
    'Förhindra kränkningar': 'Förhindra kränkningar',
    'Elevhälsa': 'Elevhälsa',
    'Stimulans': 'Stimulans',
    'Stimulans och utmaningar': 'Stimulans',
    'Utmaningar': 'Utmaningar',
    # äldre namn
    'Veta vad som krävs': 'Veta vad som krävs',
    'Veta vad som krävs/Tillit till elevens förmåga': 'Veta vad som krävs',
    'Tillit till elevens förmåga': 'Tillit till elevens förmåga',
    'Anpassning efter elevens behov': 'Anpassning efter elevens behov',
    'Argumentation och kritiskt': 'Kritiskt tänkande',
    'Argumentation och kritiskt tänkande': 'Kritiskt tänkande',
    'Argumentation och kritiskt tänkande/Delaktighet och': 'Kritiskt tänkande',
    'Argumentation och kritiskt tänkande/Delaktighet': 'Kritiskt tänkande',
    'Kritiskt tänkande': 'Kritiskt tänkande',
    'Grundläggande värden i': 'Grundläggande värden (undervisning)',
    'Grundläggande värden i undervisningen': 'Grundläggande värden (undervisning)',
    'Grundläggande värden i undervisningen/lärandet': 'Grundläggande värden (undervisning)',
    'Grundläggande värden på skolan': 'Grundläggande värden (skolan)',
    'Grundläggande värden på skolan/Elevhälsa': 'Grundläggande värden (skolan)',
    'Delaktighet och inflytande': 'Inflytande',
    'Elevinflytande': 'Inflytande',
    'Inflytande': 'Inflytande',
    'Vårdnadshavares delaktighet och': 'Vårdnadshavares delaktighet',
    # nyare namn (2022+)
    'Information om utbildningen': 'Information om utbildningen',
    'Information om utbildningens mål': 'Information om utbildningen',
    'Information från skolan': 'Information från skolan',
    'Stöd': 'Stöd',
    'Särskilt stöd': 'Särskilt stöd',
    'Bemötande - elever': 'Bemötande – elever',
    'Bemötande - lärare': 'Bemötande – lärare',
    'Pedagogiskt ledarskap': 'Pedagogiskt ledarskap',
    'Bedömning och betygsättning': 'Bedömning och betygsättning',
    'Utveckling av utbildningen': 'Utveckling av utbildningen',
    'Uppföljning': 'Uppföljning',
    'Samverkan': 'Samverkan',
    'Samverkan av undervisning': 'Samverkan',
    'Modersmålsundervisning': 'Modersmålsundervisning',
    'Jämställdhet': 'Jämställdhet',
    'Rutiner': 'Rutiner',
    'Fritidshem': 'Fritidshem',
}
JUNK = {'Elevens utveckling helt och ganska ganska', 'Medel', ''}

def canon_omrade(name):
    if not name:
        return None
    n = name.strip()
    n = re.sub(r'\s*\(bildar.*$', '', n).strip()
    if n in JUNK:
        return None
    if n in CANON:
        return CANON[n]
    # prefixmatchning för trunkerade namn
    for k, v in CANON.items():
        if k.startswith(n) and len(n) >= 6:
            return v
    return n

# teman som kan följas kontinuerligt över alla eror
STABLE = ['Trygghet', 'Studiero', 'Förhindra kränkningar', 'Elevhälsa', 'Stimulans']

# ---------------------------------------------------------------------------
# Perioder (tidsaxel)
# ---------------------------------------------------------------------------
periods = {}
for r in rows:
    periods[r['period']] = dict(key=r['period'], label=r['label'],
                                year=r['year'], term=r['term'],
                                sortkey=r['sortkey'])
period_order = sorted(periods.values(), key=lambda p: p['sortkey'])
label_by_period = {p['key']: p['label'] for p in period_order}
sortkey_by_label = {p['label']: p['sortkey'] for p in period_order}

# ---------------------------------------------------------------------------
# Indextidsserier: (group, subgroup, omrade) -> {label: index}
# Källa 1: oindex (per rapport, inkl vt/ht). Källa 2: trend-tabeller (2025/26).
# ---------------------------------------------------------------------------
series = defaultdict(dict)         # key -> {label: (index, source)}

PRIO = {'rapport': 3, 'trend': 2, 'beräknad': 1}

def add_point(group, subgroup, omrade, label, idx, source):
    if idx is None:
        return
    key = (group, subgroup, omrade)
    cur = series[key].get(label)
    if cur is None or PRIO[source] > PRIO[cur[1]]:
        series[key][label] = (idx, source)

# samla flera oindex-värden per (period,grupp,delgrupp,område) -> median
agg = defaultdict(list)
for o in oindex:
    om = canon_omrade(o['omrade'])
    if not om or not o.get('subgroup'):
        continue
    agg[(o['group'], o['subgroup'], om, o['label'])].append(o['index'])
for (g, s, om, lab), vals in agg.items():
    add_point(g, s, om, lab, round(statistics.median(vals), 1), 'rapport')

# trend-tabeller: år -> index. Etikett = årets helårsetikett (== str(year))
for t in trends:
    om = canon_omrade(t['omrade'])
    if not om or not t.get('subgroup'):
        continue
    for year, idx in t['values'].items():
        lab = label_by_period.get(year, year)
        add_point(t['group'], t['subgroup'], om, lab, idx, 'trend')

# backfill: där officiellt index saknas men frågor finns -> medel av frågemedel
# (median |diff| mot officiellt index ≈ 0,03; markeras som källa 'beräknad').
qagg = defaultdict(list)
for r in rows:
    om = canon_omrade(r['omrade'])
    if om and r.get('subgroup'):
        # printade medel för (-)-frågor är redan omvända (högt = bra)
        qagg[(r['group'], r['subgroup'], om, r['label'])].append(r['medel'])
for (g, s, om, lab), vals in qagg.items():
    add_point(g, s, om, lab, round(statistics.mean(vals), 1), 'beräknad')

index_series = []
for (g, s, om), pts in series.items():
    points = [dict(label=lab, sortkey=sortkey_by_label.get(lab, 0),
                   index=v[0], source=v[1]) for lab, v in pts.items()]
    points.sort(key=lambda p: p['sortkey'])
    if len(points) >= 1:
        index_series.append(dict(group=g, subgroup=s, omrade=om,
                                 stable=(om in STABLE), points=points))

# ---------------------------------------------------------------------------
# Frågedata för drill-down
# ---------------------------------------------------------------------------
SCALE5 = ['Stämmer helt och hållet', 'Stämmer ganska bra',
          'Stämmer ganska dåligt', 'Stämmer inte alls', 'Vet ej']
SCALE6 = ['Mest positivt', 'Ganska positivt', 'Mitten',
          'Ganska negativt', 'Mest negativt', 'Vet ej']

questions = []
for r in rows:
    om = canon_omrade(r['omrade'])
    questions.append(dict(
        period=r['period'], label=r['label'], year=r['year'], term=r['term'],
        sortkey=r['sortkey'], group=r['group'], subgroup=r['subgroup'],
        omrade=om, fraga=r['fraga'], medel=r['medel'],
        andelar=[round(a, 1) for a in r['andelar']],
        n_alt=r['n_alt'], reverse=r['reverse']))

# ---------------------------------------------------------------------------
# Navigationshjälp: vilka grupper/delgrupper/områden/perioder finns
# ---------------------------------------------------------------------------
groups = sorted({r['group'] for r in rows if r['group']})
subgroups = defaultdict(set)
for r in rows:
    if r['group'] and r['subgroup']:
        subgroups[r['group']].add(r['subgroup'])
subgroups = {g: sorted(v) for g, v in subgroups.items()}

out = dict(
    meta=dict(
        generated=datetime.date.today().isoformat(),
        source='Skolinspektionen – Skolenkäten, totalrapporter',
        periods=period_order,
        groups=groups,
        subgroups=subgroups,
        stable_themes=STABLE,
        scale5=SCALE5, scale6=SCALE6,
        n_questions=len(questions), n_series=len(index_series),
    ),
    index_series=index_series,
    questions=questions,
)

os.makedirs(DATA, exist_ok=True)
js = 'window.SKOLDATA = ' + json.dumps(out, ensure_ascii=False) + ';\n'
open(os.path.join(HERE, 'skolenkaten_data.js'), 'w').write(js)
json.dump(out, open(os.path.join(DATA, 'skolenkaten_data.json'), 'w'),
          ensure_ascii=False)

print(f"Perioder:      {len(period_order)}  ({period_order[0]['label']} … {period_order[-1]['label']})")
print(f"Grupper:       {groups}")
print(f"Indexserier:   {len(index_series)}")
print(f"Frågerader:    {len(questions)}")
print(f"Stabila teman: {STABLE}")
sz = os.path.getsize(os.path.join(HERE, 'skolenkaten_data.js'))
print(f"Datafil:       skolenkaten_data.js  ({sz/1024:.0f} kB)")
