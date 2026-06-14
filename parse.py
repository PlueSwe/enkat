#!/usr/bin/env python3
"""
Parsar Skolenkätens totalrapporter (PDF) till ett enhetligt JSON-schema.

Strategi:
- Läs ord med koordinater, filtrera bort roterad text (upright=False) som
  förekommer i de nyaste rapporternas sammanfattningsblock.
- Rekonstruera rader utifrån y-position, sortera ord vänster->höger.
- Spåra grupp (Elever/Vårdnadshavare/Pedagogisk personal/Undervisande lärare)
  och delgrupp (åk 5 Grundskola, år 2 Gymnasieskola, Förskoleklass ...).
- Frågeområde-rubriker: "N. Namn" (+ ev. "Index X,Y").
- Frågerader: medelvärde (X,Y) följt av 5 eller 6 andelar (%).
  Tidiga rapporter har även antal mellan medelvärde och andel; de ignoreras,
  andelarna behålls.

Utdata: data/skolenkaten.json
"""
import pdfplumber, glob, os, re, json, sys
from collections import defaultdict

RAW = os.path.join(os.path.dirname(__file__), 'raw')
OUT = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(OUT, exist_ok=True)

# ---- Period-metadata ur filnamn ----
def period_from_name(base):
    # ex: vt-2015_elever, ht-2018_total, 2021_total
    m = re.match(r'(vt|ht)-(\d{4})_(\w+)', base)
    if m:
        term, year, grp = m.group(1), int(m.group(2)), m.group(3)
        label = f"{'VT' if term=='vt' else 'HT'} {year}"
        # sorteringsnyckel: år*10 + (vt=0,ht=5)
        sortkey = year*10 + (0 if term=='vt' else 5)
        return dict(period=f"{term}-{year}", label=label, year=year,
                    term=term, sortkey=sortkey, filegroup=grp)
    m = re.match(r'(\d{4})_(\w+)', base)
    if m:
        year, grp = int(m.group(1)), m.group(2)
        return dict(period=str(year), label=str(year), year=year,
                    term='helar', sortkey=year*10+2, filegroup=grp)
    return None

# ---- Grupp- och delgruppsdetektering ----
GROUP_PATTERNS = [
    ('Undervisande lärare', re.compile(r'^Undervisande lärare\b')),
    ('Pedagogisk personal',  re.compile(r'^Pedagogisk personal\b')),
    ('Vårdnadshavare',       re.compile(r'^Vårdnadshavare\b')),
    ('Elever',               re.compile(r'^Elever\b')),
]
# Delgrupp ur totalrapport-sektionsrubrik, ex "Elever åk 5 Grundskola ..."
# Matchas som PREFIX – i nyare rapporter följer en sidtitel på samma rad.
SUBGROUP_TAIL = (r'(åk \d+ Grundskola|år 2 Gymnasieskola|Förskoleklass|'
                 r'Anpassad grundskola|Anpassad gymnasieskola|Grundsärskola|'
                 r'Grundskola|Gymnasieskola)')
SECTION_RE = re.compile(
    r'^(Elever|Vårdnadshavare|Pedagogisk personal|Undervisande lärare)\s+'
    + SUBGROUP_TAIL + r'\b')
# Indextrend-tabell (2025/2026): "Samtliga deltagande skolor åk 5"
TREND_SUB_RE = re.compile(r'Samtliga deltagande skolor\s+(.+?)\s*$', re.I)
YEARROW_RE = re.compile(r'^((?:20\d{2}\s+){2,}20\d{2})\s*$')
TRENDROW_RE = re.compile(r'^(\d{1,2})\.\s+(.+?)\s+((?:(?:\d{1,2},\d|[-–])\s*){2,})$')
# Delgrupp ur tidig per-grupp-rapport, ex "Resultat för elever i årskurs 5 ..."
# (raden radbryts ofta före "i samtliga", så vi tar hela svansen och städar.)
# Begränsas till persongrupper – annars matchar "Resultat för frågeområden ...".
RESULT_FOR_RE = re.compile(
    r'^Resultat för\s+((?:elever|vårdnadshavare|pedagogisk personal|'
    r'undervisande lärare)\b.+?)\s*$', re.I)

def clean_subgroup(s):
    s = s.strip()
    s = re.sub(r'\s+', ' ', s)
    return s

def canon_subgroup(group, raw):
    """Mappa råa delgruppstexter (båda eror) till en kanonisk etikett."""
    s = raw.lower()
    # Elever
    if 'årskurs 5' in s or 'åk 5' in s:        return 'Åk 5 Grundskola'
    if 'årskurs 8' in s or 'åk 8' in s:        return 'Åk 8 Grundskola'
    if 'årskurs 9' in s or 'åk 9' in s:        return 'Åk 9 Grundskola'
    if 'gymnasieskolans år 2' in s or 'år 2 gymnas' in s:  return 'År 2 Gymnasieskola'
    # Vårdnadshavare
    if 'förskoleklass' in s:                   return 'Förskoleklass'
    if 'anpassad grundskola' in s or 'grundsärskola' in s: return 'Anpassad grundskola'
    if 'anpassad gymnas' in s:                 return 'Anpassad gymnasieskola'
    # Generella skolformer (vh, personal, lärare)
    if 'gymnasie' in s:                        return 'Gymnasieskola'
    if 'grundskola' in s or 'grundskolan' in s: return 'Grundskola'
    return clean_subgroup(raw)

# En giltig delgruppsrubrik i totalrapport (undvik falska träffar på frågetext)
VALID_SUBGROUP_TAIL = re.compile(
    r'^(åk \d+ Grundskola|år 2 Gymnasieskola|Grundskola|Gymnasieskola|'
    r'Förskoleklass|Anpassad grundskola|Grundsärskola|Anpassad gymnasieskola|'
    r'Förskola|Totalt.*)$')

OMRADE_RE = re.compile(r'^(\d{1,2})\.\s+([^\d].*?)\s*$')
INDEX_RE  = re.compile(r'^Index\s+(\d{1,2},\d)\b')
PCT = r'\d{1,3}(?:,\d)?%'
# Datarad: medelvärde + 5..6 andelar (ev antal-tokens mellan; vi plockar bara %)
DATAROW_RE = re.compile(r'(?<!\d)(\d{1,2},\d)\b')

MEDEL_TOK = re.compile(r'^\d{1,2},\d$')
PCT_TOK   = re.compile(r'^\d{1,3}(?:,\d)?%$')

def _bands(words, tol=3.5):
    """Klustra ord till visuella rader efter y (top)."""
    words = sorted(words, key=lambda w: w['top'])
    bands, cur, top = [], [], None
    for w in words:
        if top is None or abs(w['top']-top) <= tol:
            cur.append(w); top = w['top'] if top is None else top
        else:
            bands.append(cur); cur=[w]; top=w['top']
    if cur: bands.append(cur)
    return bands

def extract_items(page):
    """
    Returnerar en y-ordnad lista av poster:
      ('line', text, ytop)               – rubrik/områdes-/index-/trendrad
      ('data', label, medel, andelar, ytop)
    Sifferrader paras ihop med närliggande textrader via koordinater så att
    tvåradiga frågor (med siffrorna centrerade mellan raderna) blir korrekta.
    """
    words = [w for w in page.extract_words(extra_attrs=['upright'])
             if w.get('upright', True)]
    if not words:
        return []
    heights = [w['bottom']-w['top'] for w in words]
    lh = sorted(heights)[len(heights)//2] or 10  # median radhöjd

    bands = _bands(words)
    data_bands, text_bands = [], []
    for b in bands:
        b.sort(key=lambda w: w['x0'])
        toks = [w['text'] for w in b]
        pcts = [t for t in toks if PCT_TOK.match(t)]
        medels = [w for w in b if MEDEL_TOK.match(w['text'])]
        cy = sum((w['top']+w['bottom'])/2 for w in b)/len(b)
        text_join = ' '.join(toks)
        if len(pcts) >= 5 and medels:
            medel_w = medels[0]
            label_words = [w for w in b if w['x0'] < medel_w['x0']
                           and not PCT_TOK.match(w['text'])
                           and not re.match(r'^\d', w['text'])]
            label = ' '.join(w['text'] for w in label_words)
            andelar = [float(p.replace('%','').replace(',','.')) for p in pcts][:6]
            data_bands.append(dict(cy=cy, ytop=b[0]['top'], label=label,
                                   medel=float(medel_w['text'].replace(',','.')),
                                   andelar=andelar, extra=[]))
        else:
            text_bands.append(dict(cy=cy, ytop=b[0]['top'], text=text_join))

    # Tilldela "föräldralösa" textrader (frågetext-fortsättning) till närmaste
    # sifferrad – men inte rubrik-/struktur-/skalrader.
    structural = []
    for tb in text_bands:
        t = tb['text']
        if (SECTION_RE.match(t) or RESULT_FOR_RE.match(t) or INDEX_RE.match(t)
                or OMRADE_RE.match(t) or TREND_SUB_RE.search(t)
                or YEARROW_RE.match(t) or is_scale_noise(t)
                or 'deltagande skolor' in t.lower()):
            structural.append(tb)
            continue
        if not data_bands:
            structural.append(tb); continue
        nearest = min(data_bands, key=lambda d: abs(d['cy']-tb['cy']))
        if abs(nearest['cy']-tb['cy']) <= 2.2*lh:
            nearest['extra'].append((tb['ytop'], tb['text']))
        else:
            structural.append(tb)

    items = []
    for d in data_bands:
        parts = [(d['ytop'], d['label'])] if d['label'] else []
        parts += d['extra']
        parts.sort(key=lambda x: x[0])
        label = re.sub(r'\s+', ' ', ' '.join(p[1] for p in parts)).strip()
        items.append((d['ytop'], 'data', label, d['medel'], d['andelar']))
    for tb in structural:
        items.append((tb['ytop'], 'line', tb['text']))
    items.sort(key=lambda it: it[0])
    return items

SCALE_WORDS = set('''och hållet helt stämmer ganska bra dåligt inte alls vet ej
ena medelvärde andel antal värde till stor viss del väldigt mycket lite alltid
ofta ibland sällan aldrig instämmer instämmer helt'''.split())

def is_scale_noise(line):
    """True om raden i huvudsak är rubrik-/skalord (radbruten tabellrubrik)."""
    toks = re.findall(r'[A-Za-zåäöÅÄÖ]+', line.lower())
    if not toks:
        return True
    hit = sum(1 for t in toks if t in SCALE_WORDS)
    return hit / len(toks) >= 0.6

def parse_datarow(text):
    """Returnerar (label, medelvärde, [andelar%]) eller None."""
    pcts = re.findall(PCT, text)
    if len(pcts) not in (5, 6):
        return None
    # medelvärde = sista 'X,Y' före första procenttalet
    firstpct_pos = text.find(pcts[0])
    head = text[:firstpct_pos]
    mvs = re.findall(r'(?<!\d)(\d{1,2},\d)(?!\d)', head)
    if not mvs:
        return None
    medel = mvs[-1]
    # label = allt före medelvärdet
    mpos = head.rfind(medel)
    label = head[:mpos]
    # rensa eventuella antal-tal i slutet av label
    label = re.sub(r'[\d  ]+$', '', label).strip()
    andelar = [float(p.replace('%','').replace(',','.')) for p in pcts]
    return label, float(medel.replace(',','.')), andelar

def parse_pdf(path):
    base = os.path.splitext(os.path.basename(path))[0]
    meta = period_from_name(base)
    rows = []
    cur_group = None
    cur_sub = None
    cur_omrade = None
    cur_omrade_index = None
    pending_label = []  # textrader som ännu inte knutits till en datarad
    trend_years = None  # årshuvud i indextrend-tabell
    trend_sub = None    # delgrupp för trend-tabellen
    trends = []         # {group,subgroup,omrade,omrade_nr,year->index}
    oindex = []         # områdesindex per rapport {group,subgroup,omrade,nr,index}

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for item in extract_items(page):
                if item[1] == 'data':
                    _, _, label, medel, andelar = item
                    full_label = re.sub(r'\s+', ' ', label).strip()
                    full_label = re.sub(
                        r'^(och hållet|ganska bra|ganska dåligt|inte alls|'
                        r'del del|Vet ej|Vet inte)\s+', '', full_label, flags=re.I)
                    reverse = '(-)' in full_label
                    full_label = full_label.replace('(-)', '').strip()
                    if cur_group and full_label and not is_scale_noise(full_label):
                        rows.append(dict(
                            group=cur_group, subgroup=cur_sub,
                            omrade=(cur_omrade['namn'] if cur_omrade else None),
                            omrade_nr=(cur_omrade['nr'] if cur_omrade else None),
                            omrade_index=(cur_omrade['index'] if cur_omrade else None),
                            fraga=full_label, medel=medel,
                            andelar=andelar, n_alt=len(andelar),
                            reverse=reverse))
                    continue

                line = item[2].strip()
                if not line:
                    continue

                # Sektionsrubrik i totalrapport (Elever åk 5 Grundskola)
                m = SECTION_RE.match(line)
                if m:
                    cur_group = m.group(1)
                    cur_sub = canon_subgroup(cur_group, m.group(2))
                    trend_years = None
                    trend_sub = None
                    continue

                # --- Indextrend-tabell (2025/2026) ---
                mt = TREND_SUB_RE.search(line)
                if mt and 'deltagande skolor' in line.lower():
                    trend_sub = canon_subgroup(cur_group or '', mt.group(1))
                    trend_years = None
                    continue
                if trend_sub:
                    my = YEARROW_RE.match(line)
                    if my:
                        trend_years = my.group(1).split()
                        continue
                    if trend_years:
                        mr = TRENDROW_RE.match(line)
                        if mr:
                            vals = re.findall(r'\d{1,2},\d|[-–]', mr.group(3))
                            if len(vals) == len(trend_years):
                                rec = dict(group=cur_group, subgroup=trend_sub,
                                           omrade=mr.group(2).strip(),
                                           omrade_nr=int(mr.group(1)), values={})
                                for y, v in zip(trend_years, vals):
                                    if v not in ('-', '–'):
                                        rec['values'][y] = float(v.replace(',', '.'))
                                trends.append(rec)
                            continue

                # Tidig per-grupp-rapport: "Resultat för elever i årskurs 5..."
                m = RESULT_FOR_RE.match(line)
                if m:
                    sub = clean_subgroup(m.group(1))
                    low = sub.lower()
                    if low.startswith('elever'):
                        cur_group = 'Elever'
                    elif low.startswith('vårdnadshavare'):
                        cur_group = 'Vårdnadshavare'
                    elif 'personal' in low or 'lärare' in low:
                        cur_group = ('Undervisande lärare'
                                     if 'lärare' in low else 'Pedagogisk personal')
                    cur_sub = canon_subgroup(cur_group or '', sub)
                    cur_omrade = None
                    continue

                # Index-rad (egen rad, tidiga rapporter)
                mi = INDEX_RE.match(line)
                if mi:
                    cur_omrade_index = float(mi.group(1).replace(',', '.'))
                    if cur_omrade is not None:
                        cur_omrade['index'] = cur_omrade_index
                        oindex.append(dict(group=cur_group, subgroup=cur_sub,
                                           omrade=cur_omrade['namn'],
                                           omrade_nr=cur_omrade['nr'],
                                           index=cur_omrade_index))
                    continue

                # Frågeområde-rubrik (även när "Antal Andel" delar raden)
                mo = OMRADE_RE.match(line)
                if mo:
                    namn = mo.group(2).strip()
                    inline_idx = None
                    mii = re.search(r'\bIndex\s+(\d{1,2},\d)', namn)
                    if mii:
                        inline_idx = float(mii.group(1).replace(',', '.'))
                    namn = re.split(
                        r'\s+(?:Index|Medel\b|Medel-|Medelvärde|Stämmer|Antal|'
                        r'Helt och|Alltid|Väldigt|Instämmer|Vet ej|Vet inte|'
                        r'Till stor|Aldrig|Ofta)\b', namn)[0].strip()
                    namn = re.sub(r'\s*\(bildar ej.*$', '', namn).strip()
                    namn = namn.rstrip(' -–').strip()
                    if not namn:
                        continue
                    cur_omrade = dict(nr=int(mo.group(1)), namn=namn,
                                      index=inline_idx)
                    cur_omrade_index = inline_idx
                    if inline_idx is not None:
                        oindex.append(dict(group=cur_group, subgroup=cur_sub,
                                           omrade=namn, omrade_nr=int(mo.group(1)),
                                           index=inline_idx))
                    continue

    return meta, rows, trends, oindex

def main():
    allrows = []
    alltrends = []
    alloindex = []
    stats = []
    for path in sorted(glob.glob(os.path.join(RAW,'*.pdf'))):
        meta, rows, trends, oindex = parse_pdf(path)
        for r in rows:
            r.update(meta)
        for t in trends:
            t['source_period'] = meta['period']
        for o in oindex:
            o.update({k: meta[k] for k in ('period','label','year','term','sortkey')})
        allrows.extend(rows)
        alltrends.extend(trends)
        alloindex.extend(oindex)
        stats.append((os.path.basename(path), len(rows), len(trends), len(oindex)))
    json.dump(allrows, open(os.path.join(OUT,'rows_raw.json'),'w'), ensure_ascii=False)
    json.dump(alltrends, open(os.path.join(OUT,'trends_raw.json'),'w'), ensure_ascii=False)
    json.dump(alloindex, open(os.path.join(OUT,'oindex_raw.json'),'w'), ensure_ascii=False)
    print(f"{'FIL':30} {'RADER':>6} {'TREND':>6} {'OIDX':>6}")
    for name,n,t,o in stats:
        print(f"{name:30} {n:6} {t:6} {o:6}")
    print(f"\nRader: {len(allrows)}  trend: {len(alltrends)}  oindex: {len(alloindex)}")

if __name__ == '__main__':
    main()
