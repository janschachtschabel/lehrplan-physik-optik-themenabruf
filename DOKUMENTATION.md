# Lehrplanthemen aus dem MEM-Triplestore abrufen

**Fallstudie Physik / Optik** — Themenbereiche, Kompetenzen und Bildungsstufen
maschinenlesbar aus den digitalisierten Lehrplänen der Bundesländer.

Repository: <https://github.com/janschachtschabel/lehrplan-physik-optik-themenabruf>

---

## 1. Ausgangsfrage und Ergebnis

Gesucht waren alle Physiklehrpläne mit Bezug zum Thema Optik — nicht als
Dokumentenliste, sondern granular: die einzelnen Themenbereiche und
Kompetenzerwartungen, jeweils mit der Bildungsstufe, für die sie gelten.

Ein Lauf über alle im Store vorhandenen Bundesländer:

| Bundesland | Lehrpläne | Treffer | Datenquelle |
|---|---:|---:|---|
| Sachsen | 6 | 272 | `lp-sachsen.org` |
| Rheinland-Pfalz | 7 | 200 | `lp-rlp.org` |
| Berlin | 1 | 0 | `lehrplan.yovisto.com` |
| **Gesamt** | **14** | **472** | |

Die Zahlen sind gegenkontrolliert: die Klassenstatistik des Berichts zählt
genau 272 Knoten der Klasse `Element (SN)` und 200 der Klasse `Element (RP)` —
identisch zu den Ländersummen aus den Einzelabrufen.

Laut Projektdokumentation von MEM liegen Lehrplandaten für BY, SN, RP, BB und BE
vor. Im Abruf lieferten nur SN und RP Inhalte; Bayern und Brandenburg
erschienen nicht in der Trefferliste, Berlin mit einem Lehrplan ohne
Optik-Treffer. Ob dort Physikdaten fehlen, anders verfachlicht sind oder unter
einer nicht als „Physik" bezeichneten Fachbezeichnung liegen, ist offen.

---

## 2. Datenquelle

| | |
|---|---|
| Projekt | MEM — *Metadata for Educational Media*, FWU / DigitalPakt Schule |
| Ziel | maschinenlesbare Lehrpläne der 16 Bundesländer |
| SPARQL-Endpoint | `https://sparql.mem.edufeed.org/sparql/` (Virtuoso, alle Graphen im Default-Graph, kein Reasoning, keine CORS-Header) |
| Ontologie | [`FWU-DE/lehrplan-ontologie`](https://github.com/FWU-DE/lehrplan-ontologie), Namespace `https://w3id.org/lehrplan/ontology/` |
| MCP-Server | [`FWU-DE/mem-mcp`](https://github.com/FWU-DE/mem-mcp) — dieselben Abfragen als LLM-Tools |
| Beispielabfragen | [`FWU-DE/mem-sparql-notebooks`](https://github.com/FWU-DE/mem-sparql-notebooks) |

Die Ontologie ist zweischichtig: ein Kern definiert länderübergreifende
Konzepte, die Länderontologien modellieren die konkreten Lehrpläne in der
Terminologie des jeweiligen Landes. `Lernbereich (SN)`, `Themenfeld (BB)` und
`Kompetenz (RP)` sind also verschiedene Klassen, die auf gemeinsame Kernklassen
zurückgeführt werden können.

---

## 3. Wie der Abruf funktioniert

Sechs Abfragen, jede mit einem klaren Zweck. Präfixe in allen Beispielen:

```sparql
PREFIX lp:   <https://w3id.org/lehrplan/ontology/>
PREFIX obo:  <http://purl.obolibrary.org/obo/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
```

### Stufe 1 — Lehrpläne des Fachs finden

`LP_0000438` ist die abstrakte Lehrplanklasse; die konkreten Lehrpläne
deklarieren Länder-Unterklassen. Ohne Reasoning muss der Abstieg explizit
erfolgen — und weil Virtuoso an unbeschränkten Transitivpfaden scheitert
(siehe Abschnitt 5), als beschränkte Alternative:

```sparql
SELECT DISTINCT ?lp ?lpLabel WHERE {
  { BIND(lp:LP_0000438 AS ?lpClass) }
  UNION { ?lpClass rdfs:subClassOf lp:LP_0000438 }
  UNION { ?lpClass rdfs:subClassOf/rdfs:subClassOf lp:LP_0000438 }
  ?lp rdf:type ?lpClass ;
      rdfs:label ?lpLabel ;
      lp:LP_0000537 ?fach .
  ?fach rdfs:label ?fachLabel .
  FILTER(CONTAINS(LCASE(STR(?fachLabel)), "physik"))
  FILTER(LANG(?lpLabel) IN ("de", ""))
}
```

### Stufe 2 — Kontext und Bildungsstufen der Lehrpläne

Alle beschreibenden Eigenschaften in einer Abfrage, plus den `rdf:type` des
Objekts, weil davon die Einordnung abhängt (Abschnitt 4):

```sparql
SELECT DISTINCT ?s ?p ?o ?oLabel ?oType WHERE {
  VALUES ?s { <…Lehrplan-URIs…> }
  VALUES ?p { lp:LP_0000029 lp:LP_0000537 lp:LP_0000812
              lp:LP_0000026 lp:LP_0000047 lp:LP_0000578
              lp:LP_0000833 lp:LP_0000840 lp:LP_0000024 }
  ?s ?p ?o .
  OPTIONAL { ?o rdfs:label ?oLabel FILTER(LANG(?oLabel) IN ("de", "")) }
  OPTIONAL { ?o rdf:type ?oType }
}
```

### Stufe 3 — Thementreffer je Lehrplan

Hier steckt der nützlichste Datendefekt: `obo:BFO_0000051` („hat Teil") ist in
den Ländergraphen **transitiv über-asserted**. Jeder Nachfahre erscheint als
direkter Teil jedes Vorfahren. Für eine Baumdarstellung ist das ein Problem —
für einen flachen Themen-Harvest heißt es: **ein Hop genügt für den gesamten
Lehrplan.**

```sparql
SELECT DISTINCT ?node ?nodeLabel ?type WHERE {
  <…Lehrplan…> obo:BFO_0000051 ?node .
  ?node rdfs:label ?nodeLabel .
  OPTIONAL { ?node rdf:type ?type }
  FILTER(REGEX(STR(?nodeLabel), "Optik|Licht|Linse|Spiegel|…", "i"))
}
```

### Stufe 4 — Rolle der Treffer bestimmen

Ob ein Knoten Themenbereich, Kompetenz oder Lerninhalt ist, steht nicht im
Label, sondern in den OWL-Axiomen seiner Klasse — in **zwei verschiedenen
Formen**:

- Strukturierende Klassen (`Lernbereich (SN)`, `Themenfeld (BB)`) hängen über
  eine gewöhnliche `rdfs:subClassOf`-Kette an `CE-Bereich` (`LP_0000349`).
- Kompetenz- und Inhaltsklassen (`Kompetenzerwartung (BY)`, `Kompetenz (RP)`,
  `Lernziel und Lerninhalt (SN)`) sind Unterklassen einer **anonymen
  Intersection**, die `LP_0000483` („has function specification") per
  `owl:hasValue` auf ein Funktions-Individuum festlegt:
  `LP_0000479` Kompetenzbeschreibungsfunktion, `LP_0000480`
  Lerninhaltsbeschreibungsfunktion, `LP_0000497` Bereichsfunktion.

Ein `rdfs:subClassOf*`-Aufstieg auf `CE-Kompetenzspezifikation` findet die
zweite Gruppe **nicht** — der Pfad läuft über einen Blank Node. Beide Wege
müssen abgefragt werden. Eine Klasse kann mehrere Funktionen tragen:
`Lernziel und Lerninhalt (SN)` ist Kompetenz *und* Inhalt.

### Stufe 5 — Elternknoten für den Kontext

Wegen der Über-Assertion aus Stufe 3 ist jeder Vorfahre ein behaupteter
Elternteil. Der Filter isoliert den echten:

```sparql
SELECT DISTINCT ?node ?parent ?parentLabel WHERE {
  VALUES ?node { <…Treffer-URIs…> }
  ?parent obo:BFO_0000051 ?node .
  ?parent rdfs:label ?parentLabel .
  FILTER NOT EXISTS {
    ?parent obo:BFO_0000051 ?mid . ?mid obo:BFO_0000051 ?node .
    FILTER(?mid != ?node && ?mid != ?parent)
  }
}
```

Damit steht jede Kompetenz in ihrem Lernbereich — die inhaltliche Verortung,
die eine flache Trefferliste sonst verliert.

### Stufe 6 — Prädikat-Audit

Eine Diagnoseabfrage listet alle an Lehrplänen tatsächlich verwendeten
Prädikate. Sie ist der Grund, warum das fehlende Stufen-Mapping überhaupt
aufgefallen ist, und sollte bei jeder neuen Datenlieferung mitlaufen.

---

## 4. Zwei Kodierungen für Bildungsstufen

Die Ontologie kennt fünf Stufen-Eigenschaften, alle Unterproperties von
`LP_0000024` („wird beschrieben von"):

| IRI | Bedeutung | Zielklasse |
|---|---|---|
| `LP_0000026` | hat Jahrgangsstufe | `LP_0000009` Jahrgangsstufe |
| `LP_0000047` | hat Schulstufe | `LP_0000020` Primar- / Sek I / Sek II |
| `LP_0000578` | hat Niveaustufe | `LP_0000443` (BE/BB Niveaustufen) |
| `LP_0000833` | hat Bildungsgangniveau | `LP_0000028` |
| `LP_0000840` | hat Niveau | `LP_0000037` |

Der Prädikat-Audit am Berliner Lehrplan zeigte jedoch:

```
LP_0000024   vorhanden
LP_0000029   vorhanden   (von Bundesland)
LP_0000537   vorhanden   (hat Schulfach)
LP_0000026   FEHLT
LP_0000047   FEHLT
```

Die Ländergraphen asserten also **die Oberproperty statt der spezifischen
Unterproperty**. Da Virtuoso keine Property-Hierarchie auflöst, liefert eine
Abfrage auf `LP_0000026` in diesem Fall nichts — und eine Abfrage auf
`LP_0000024` liefert alles Beschreibende gemischt.

Die Auflösung erfolgt daher über den `rdf:type` des Objekts: ist es vom Typ
`LP_0000009`, handelt es sich um eine Jahrgangsstufe; `LP_0000443` ist eine
Niveaustufe, und so weiter. Weil `Niveau` bis Tiefe 4 verschachtelt ist, werden
Unterklassen beschränkt aufgelöst. Nicht zuordenbare Objekte landen im Feld
`weitere`, statt verworfen zu werden.

> **Offener Punkt.** Die Beispiel-Kompetenzen im Bericht zeigen für
> Rheinland-Pfalz durchgängig „–" in der Stufenspalte. Für RP scheint also auch
> über `LP_0000024` keine Stufe zu greifen. Der Abschnitt
> *Bildungsstufen-Abdeckung* des Berichts quantifiziert das; sein Ergebnis ist
> hier noch nachzutragen. Die Jahrgangsstufe steckt bei RP möglicherweise nur im
> Lehrplantitel („Physik 7-9/10") oder in einer Zwischenebene des Baums.

---

## 5. Was der Endpoint erzwingt

Vier Eigenschaften, die jede Abfrage prägen. Wer sie nicht kennt, erhält leere
Ergebnisse oder Fehler 500 — in beiden Fällen ohne Hinweis auf die Ursache.

**Kein Reasoning.** Unterklassen und Unterproperties müssen explizit benannt
werden. `?s rdf:type lp:LP_0000438` liefert null Zeilen, obwohl 14 Lehrpläne im
Store liegen.

**Transitivpfade sprengen den Speicher.** Ein unbeschränktes
`?c rdfs:subClassOf* lp:LP_0000438`, gejoint gegen die Instanzdaten, endet in:

```
Virtuoso 42000 Error TN…: Exceeded 1000000000 bytes in transitive temp memory.
```

Alle Closures sind deshalb als beschränkte UNIONs ausgeschrieben. Die Tiefen
sind gemessen, nicht geschätzt: Lehrplan hat 16 direkte Unterklassen und
maximale Tiefe **1**, CE-Bereich Tiefe 3, die Intersection-Listen höchstens 7
Glieder. Der Stern war von Anfang an überdimensioniert.

**Labels ohne Sprachtag.** In den Ländergraphen sind Knotenlabels überwiegend
untagged. `FILTER(lang(?label) = "de")` verwirft sie sämtlich. Bei
Lehrplan-Labels ist der Filter dagegen nötig, weil dort deutsche *und* englische
Labels existieren — sonst zählt `LIMIT` Labelzeilen statt Lehrpläne.

**Über-asserted `BFO_0000051`.** Fluch und Segen, siehe Stufe 3 und 5.

---

## 6. Was in den Daten steckt

### Knotentypen

Jeder Treffer trägt die **vollständig materialisierte Typkette** bis in die
BFO-Oberontologie hinauf:

| Klasse | Knoten | Bedeutung |
|---|---:|---|
| `obo:BFO_0000001` … `IAO_0000030`, `owl:NamedIndividual` | 472 | Oberontologie, ohne fachliche Aussage |
| `Curriculares Element` | 472 | Kernklasse aller Lehrplanbausteine |
| `Element (SN)` | 272 | generischer Länder-Wrapper Sachsen |
| `Element (RP)` | 200 | generischer Länder-Wrapper Rheinland-Pfalz |
| `CE-Lerninhalt` | 249 | Kernklasse Lerninhalt |
| `Lernziel und Lerninhalt (SN)` | 249 | sächsische Ausprägung, Rolle *Kompetenz + Inhalt* |

Bemerkenswert: `rdf:type` ist materialisiert, die **Property-Hierarchie nicht**.
Wer daraus schließt, der Store sei durchgängig materialisiert, formuliert
Abfragen, die stillschweigend leer bleiben.

Die acht als „ohne erkennbare Rolle" gemeldeten Klassen sind sämtlich
Oberontologie- oder Wrapper-Klassen (`BFO_*`, `IAO_*`, `owl:NamedIndividual`,
`Curriculares Element`, `Element (SN)`, `Element (RP)`). Sie tragen
konstruktionsgemäß keine didaktische Rolle. Der Hinweis im Werkzeug ist an
dieser Stelle also ein falscher Alarm, kein Datenproblem.

### Trefferverteilung über die Lehrpläne

| Treffer | Bundesland | Lehrplan |
|---:|---|---|
| 111 | Rheinland-Pfalz | Physik, Grund- und Leistungsfach in der gymnasialen Oberstufe |
| 88 | Sachsen | Gymnasium Physik |
| 85 | Sachsen | Gymnasium Physik |
| 39 | Rheinland-Pfalz | Physik – Sekundarstufe II |
| 38 | Sachsen | Oberschule Physik |
| 33 | Sachsen | Fachoberschule Physik |
| 29 | Rheinland-Pfalz | Physik |
| 17 | Sachsen | Schule mit dem Förderschwerpunkt Lernen Physik |
| 11 | Sachsen | Berufliches Gymnasium Physik |
| 8 | Rheinland-Pfalz | Physik 7-9/10 |

Die Bandbreite ist selbst aussagekräftig: Oberstufenlehrpläne liefern ein
Vielfaches der Sekundarstufe-I-Pläne, und mit dem Förderschwerpunkt Lernen ist
auch ein Lehrplan für sonderpädagogische Förderung erfasst — nützlich für
differenzierte Materialempfehlungen.

### Beispieltreffer

Kompetenzen mit ihrem übergeordneten Lernbereich (Rheinland-Pfalz):

| Kompetenz | im Lernbereich |
|---|---|
| Licht sowohl als Welle als auch als Teilchen verstehen | Lernbereich 7: Quantenobjekte und Atommodelle beschreiben |
| Beugung und Interferenz am Einzel- und am Doppelspalt | Lernbereich 6: Mechanische und elektromagnetische Schwingungen |
| Brechung, Reflexion und Beugung von Wellen phänomenologisch … | Lernbereich 6: Mechanische und elektromagnetische Schwingungen |
| Verschiedene Arten ionisierender Strahlung und deren Wirkung | Lernbereich 8: Kernphysik verstehen, Chancen und Risiken |
| Gesellschaftspolitische Dimensionen der Nutzung von Kernenergie | Lernbereich 8: Kernphysik verstehen, Chancen und Risiken |

Die ersten drei Zeilen sind genau das gesuchte Material. Die letzten beiden
zeigen das Präzisionsproblem: sie stammen aus der Kernphysik und sind nur über
das Stichwort „Strahl" hereingekommen.

---

## 7. Präzision: 145 von 472 Treffern sind verdächtig

Der `REGEX`-Filter arbeitet ohne Wortgrenze. Der Bericht markiert jeden Treffer,
in dem kein Stichwort am Wortanfang steht — das sind **145 Treffer, 30,7 %**.
Zwei Mechanismen:

**Deutsche Komposita verstecken das Stichwort.**

| Label | greift über | tatsächliches Thema |
|---|---|---|
| Wahlpf**licht**lernbereich 9: Thermodynamische Systeme | `Licht` | Thermodynamik |
| Wahlpf**licht**lernbereich 11: Spezielle Relativitätstheorie | `Licht` | Relativitätstheorie |
| Lernbereich 10: … Astrophysik (Wahlpf**licht**) | `Licht` | Astrophysik |

„Wahlpflicht" und „Pflichtbereich" kommen in Lehrplänen ständig vor. Allein
dieses Muster erklärt einen großen Teil der 145 Fälle.

**Fachlich benachbart, aber nicht Optik.**

| Label | greift über |
|---|---|
| Erzeugung und Eigenschaften der Röntgen**strahl**ung | `Strahl` |
| Wärme**strahl**ung | `Strahl` |
| Arten und Eigenschaften der Kern**strahl**ung | `Strahl` |

Ob das Fehler oder Fund ist, hängt vom Zweck ab: für „Optik" im curricularen
Sinn nein, für „elektromagnetische Strahlung" durchaus.

**Empfehlung.** Die Stichwortliste in `mem_lehrplan/vocab.py` in zwei Stufen
fahren: ein enger Kern (`Optik`, `Linse`, `Spiegel`, `Brechung`, `Reflexion`,
`Beugung`, `Interferenz`, `Prisma`, `Lupe`, `Fernrohr`, `Mikroskop`) für
belastbare Ergebnisse, und breite Begriffe (`Licht`, `Strahl`, `Farbe`, `Sehen`,
`Abbildung`) nur mit anschließender Sichtprüfung über den Bericht. Die Begriffe
`Licht` und `Strahl` ganz zu streichen wäre falsch — „Lichtbrechung an Linsen"
und „Strahlengang" sind Kerntreffer.

---

## 8. Übertragung auf andere Themen und Fächer

Das Verfahren ist themenagnostisch. Nur zwei Parameter bestimmen den Zuschnitt:

```bash
python -m mem_lehrplan.cli --fach chemie \
  --stichwort Säure --stichwort Base --stichwort "pH" --csv chemie.csv -v

python -m mem_lehrplan.report chemie_lehrplaene.json
```

### Vorgehen für ein neues Thema

1. **Fachbezeichnungen prüfen.** `--list-faecher` zeigt die real vorhandenen
   Labels. Der Filter ist eine Teilstring-Suche, kein Vokabular-Lookup —
   Verbundfächer wie „Natur und Technik" (BY) oder „Mensch-Natur-Technik" (TH)
   enthalten Physikinhalte, matchen aber nicht auf „physik".
2. **Stichwörter aus der Fachsprache der Lehrpläne ziehen**, nicht aus der
   Alltagssprache. Lehrpläne schreiben „Kraftwandler", nicht „Hebel und Rolle".
3. **Klein anfangen** mit `--limit 2 -v`, dann den Bericht lesen.
4. **Verdächtige Treffer prüfen** und die Liste nachschärfen. Bei deutschen
   Komposita ist ein zusätzlicher Durchgang praktisch immer nötig.
5. **Ergebnis über die CSV auswerten**: eine Zeile pro Treffer mit Bundesland,
   Lehrplan, Stufe, Rolle, Elternknoten und Label.

### Beispiel-Stichwortsätze

| Thema | Kernbegriffe | Kritisch |
|---|---|---|
| Elektrizitätslehre | Stromstärke, Spannung, Widerstand, Schaltung, Induktion | `Strom` (Meeresströmung, Stromsparen) |
| Wärmelehre | Temperatur, Wärmekapazität, Aggregatzustand, Entropie | `Wärme` (Wärmedämmung im Kontext Nachhaltigkeit) |
| Mechanik | Kraft, Bewegung, Impuls, Energieerhaltung, Reibung | `Kraft` (Arbeitskraft, Streitkräfte) |
| Genetik (Bio) | DNA, Mitose, Vererbung, Mutation, Allel | `Zelle` (Solarzelle, Brennstoffzelle) |
| Bruchrechnung (Ma) | Bruch, Nenner, Zähler, Kürzen, Erweitern | `Bruch` (Knochenbruch, Kulturbruch) |

Die Spalte „Kritisch" ist kein Detail: die Wortgrenzenschwäche des Filters
schlägt bei jedem Thema zu, nur mit anderen Wörtern.

### Grenzen des Verfahrens

- **Lexikalisch, nicht semantisch.** Ein Lernbereich „Wie wir die Welt
  wahrnehmen" ohne Optik-Vokabular wird nicht gefunden. Ob die Knoten
  SKOS-Referenzen in die [`mem-skos-vocabs`](https://fwu-de.github.io/mem-skos-vocabs/)
  tragen, die eine konzeptbasierte Auswahl erlauben würden, ist ungeprüft und
  wäre der nächste Qualitätssprung.
- **Länderabdeckung.** Was nicht digitalisiert ist, kann nicht gefunden werden.
- **Eine Abfrage pro Lehrplan** für die Knotensuche; keine Parallelisierung.
- **Stufen je Bundesland unterschiedlich** kodiert, siehe Abschnitt 4.

---

## 9. Reproduktion

```bash
git clone https://github.com/janschachtschabel/lehrplan-physik-optik-themenabruf
cd lehrplan-physik-optik-themenabruf

python -m unittest discover                      # 49 Tests, offline
python -m mem_lehrplan.cli --limit 2 -v          # Rauchtest gegen den Endpoint
python -m mem_lehrplan.cli --csv optik.csv -v    # Vollabruf
python -m mem_lehrplan.report optik_lehrplaene.json --md bericht.md
```

Keine Abhängigkeiten außer der Standardbibliothek (Python ≥ 3.10). Optional
prüft `tools/ontology_smoke_test.py` die Rollenlogik gegen die echten
OWL-Axiome, `tools/measure_depths.py` die Pfadgrenzen.

Ausgaben: `optik_lehrplaene.json` (verschachtelt, mit Diagnostik),
`optik.csv` (eine Zeile pro Treffer), `bericht.md` (Auswertung).

---

## 10. Offene Punkte

| Punkt | Status |
|---|---|
| Stufen-Abdeckung nach Umstellung auf `LP_0000024` | Bericht liegt vor, Abschnitt noch nicht ausgewertet |
| Jahrgangsstufen für Rheinland-Pfalz | Beispiele zeigen „–"; Ort der Information unklar |
| Bayern und Brandenburg ohne Treffer | Ursache unklar (keine Daten? andere Fachbezeichnung?) |
| Stichwortliste nachschärfen | 145 verdächtige Treffer, Muster identifiziert |
| Verbundfächer einbeziehen | `--list-faecher` je Bundesland auswerten |
| Konzeptbasierte statt lexikalischer Auswahl | SKOS-Anbindung der Knoten ungeprüft |
| Falscher Alarm „ohne erkennbare Rolle" | Oberontologie-Klassen im Bericht ausfiltern |
