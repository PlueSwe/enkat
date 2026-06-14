# Skolenkäten – dashboard & datapipeline

Interaktiv dashboard över Skolinspektionens **Skolenkäten** 2015–2026, byggd från
de publika totalrapporterna (PDF). Visar trender över tid, jämförelser mellan år
och drill-down i enskilda frågor med stapel- och pajdiagram.

## Kör dashboarden
```bash
python3 serve.py        # startar http://127.0.0.1:8777
```
Öppna sedan http://127.0.0.1:8777/ i webbläsaren. Allt är statiskt och fungerar
även offline (Chart.js är vendrad i `vendor/`).

## Flikar
- **Översikt** – nyckeltal + stabila teman (trygghet, studiero …) för elever över tid.
- **Trender** – följ ett frågeområde över åren per grupp/delgrupp. Snabbval för
  stabila teman. Lodräta linjer markerar enkätrevisionerna (2018, 2022).
- **Jämför år** – ställ alla frågeområdens index sida vid sida för två tidpunkter,
  med differenstabell.
- **Utforska** – borra ner: år → grupp → delgrupp → område → fråga, och se hela
  svarsfördelningen som pajdiagram + medelvärde.

## Datapipeline
De råa PDF:erna ingår inte i repot – hämta dem först (lista i `sources.txt`):
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install pdfplumber
python3 fetch_pdfs.py   # sources.txt -> raw/*.pdf  (30 totalrapporter)
python3 parse.py        # raw/*.pdf  -> data/*_raw.json  (extraktion)
python3 build.py        # data/*_raw.json -> skolenkaten_data.js  (normalisering)
```
Den färdiga datan (`skolenkaten_data.js`) är redan incheckad, så dashboarden
funkar direkt utan att köra pipelinen.

### Steg
1. **`raw/`** – 30 nedladdade totalrapporter (vt/ht 2015 → 2026).
2. **`parse.py`** – koordinatbaserad PDF-extraktion (pdfplumber). Hanterar två eror:
   - 2015–2017: separata rapporter per grupp, antal + andel per svarsalternativ.
   - 2018–2026: samlad totalrapport, andelar i procent, inline-index och (2025/26)
     färdiga indextrend-tabeller.
   Roterad text filtreras bort; sifferrader paras ihop med rätt frågetext via
   y-koordinater. Producerar `rows_raw.json` (frågesvar), `oindex_raw.json`
   (områdesindex), `trends_raw.json` (indextrender).
3. **`build.py`** – kanoniserar områdesnamn, slår ihop index från rapporter +
   trendtabeller, backfilllar luckor med medel av frågornas medelvärden
   (markeras `beräknad`), och skriver `skolenkaten_data.js`.

## Datakvalitet & varningar
- Skala 0–10, högre = bättre. Negativt formulerade påståenden (–) är omvänt beräknade.
- Frågor och frågeområden **reviderades** tydligast 2018 och 2022. Jämförelser
  över dessa brott är ungefärliga; stabila teman (trygghet, studiero, elevhälsa,
  förhindra kränkningar, stimulans) går dock att följa hela vägen.
- Elevernas högstadiekull bytte från **åk 9** (t.o.m. 2021) till **åk 8** (fr.o.m.
  2022) – visas som separata serier.
- 2015–2017 saknade tryckt index för åk 5; dessa punkter är beräknade (◇ ihåliga
  markörer). Beräknat index ligger i median 0,03 från officiellt där båda finns.

Källa: Skolinspektionen, öppet publicerade totalrapporter för Skolenkäten.
