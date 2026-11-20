# Krimidinner-Generator

Erzeugt aus einem Thema ein komplettes, druckfertiges **Krimidinner-Kit** als PDFs: Story, Charaktere, Hinweise, Rätsel, Gastgeber-Anleitung, Einladungen, versiegelte Auflösung und mehr.
Die kreativen Teile schreibt eine KI, wahlweise **DeepSeek** (Standard) oder **Google Gemini**. Die Logikprüfung, die Rätsel und das Layout übernimmt deterministischer Code.

Bedienen lässt er sich über eine **passwortgeschützte Web-Oberfläche** oder über die Kommandozeile (`krimi …`).

## Was ein Kit enthält

| Datei | Inhalt |
|---|---|
| `01_gastgeber.pdf` | Vorbereitung, Ablauf je Runde mit Vorlesetexten, Verteilplan der Hinweise, Rätsel-Lösungen, Tipps, Menü, Einkaufsliste, Deko |
| `02_einladungen.pdf` | eine Einladung pro Figur mit Rolle und Kostümtipp |
| `03_charakterhefte.pdf` + `charakterhefte/*.pdf` | pro Spieler: Profil, Geheimnis, Motiv, Alibi, Beziehungen, was man sagen darf und was nicht |
| `04_hinweiskarten.pdf` | Hinweiskarten je Runde zum Ausschneiden, mit Schnittmarken |
| `05_beweisstuecke.pdf` | Brief, Zeitungsausschnitt, Notiz, Telegramm und Rätsel (Chiffre, Zahlenschloss, Wortsuche) im passenden Look |
| `06_aufloesung.pdf` | versiegelte Auflösung („Erst am Ende öffnen“) mit Schlusskette und Zeitleiste |
| `07_namensschilder.pdf` | Tischaufsteller zum Falten |
| `08_notizblaetter.pdf` | Detektiv-Notizblatt pro Spieler, dazu ein Bonus-Logikrätsel „Wer saß wo?“ |
| `kit.zip` | alles zusammen, inkl. `story.json` |

Die Formate A4 und US Letter stehen zur Wahl.

### Designs

Es gibt zehn Designs mit eigenen Farben, Schriften, Ornamenten, Zeitungskopf und Bildstil:

| Design | Passt zu |
|---|---|
| `klassisch` | Landhaus, Agatha-Christie-Stil, zeitlos |
| `chalet` | Winter, Berghütte, Skiurlaub |
| `noir` | Großstadt, Detektivbüro, 1920er–1950er |
| `weihnachten` | Heiligabend, Familienfest |
| `artdeco` | Goldene Zwanziger, Gatsby-Party, Jazz |
| `viktorianisch` | London um 1890, Sherlock Holmes |
| `riviera` | Côte d'Azur, Yacht, 1960er-Sommer |
| `western` | Saloon, Goldgräberstadt |
| `gothic` | Spukschloss, Halloween |
| `modern` | Gegenwart: Start-up, Podcast, Influencer-Villa |

- **Beim Erzeugen** wählst du das Design über Vorschaukarten oder nimmst „Automatisch“, dann sucht die KI das passende aus. In der Kommandozeile geht das mit `--design`.
- **Für ein bestehendes Kit** wählst du auf der Kit-Seite unter „Design & neu rendern“ ein anderes Design, ohne KI-Kosten. In der Kommandozeile: `krimi render output/<kit> --design western`. Das gewählte Design wird in `story.json` gespeichert.
- `krimi designs` listet alle Designs auf.
- **Eigenes Design hinzufügen:** einen Eintrag in `src/krimi/themes.py` ergänzen (Farben, Schriften, Ornamente, optional Zusatz-CSS). Web-Auswahl, KI-Prompt und PDFs übernehmen ihn automatisch.

## Schnellstart mit Docker (empfohlen)

1. **DeepSeek-API-Key besorgen**: unter <https://platform.deepseek.com/api_keys> anmelden, einen Key erstellen und unter „Top up“ etwas Guthaben aufladen. Die API ist Prepaid, ein Kit kostet nur wenige Cent.
   *Optional:* Für Illustrationen zusätzlich einen Gemini-Key unter <https://aistudio.google.com/apikey> anlegen, denn DeepSeek kann keine Bilder erzeugen.
2. **Konfiguration anlegen**:
   ```bash
   cp .env.example .env
   ```
   In `.env` eintragen:
   ```ini
   LLM_PROVIDER=deepseek
   DEEPSEEK_API_KEY=dein-key
   APP_PASSWORD=ein-gutes-passwort       # Passwort für die Web-Oberfläche
   SESSION_SECRET=langer-zufallsstring   # z. B. python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. **Starten**:
   ```bash
   docker compose up -d --build
   ```
4. Im Browser **http://localhost:8048** öffnen und mit dem Passwort aus `.env` anmelden.

Kits und Cache landen im Ordner `./data` (`data/output/<kit>/`, `data/cache/`). Sie bleiben also auch nach einem Neustart oder Update erhalten.

Ohne Docker Compose geht es so:
```bash
docker build -t krimidinner .
docker run -d -p 8000:8000 --env-file .env -v "$PWD/data:/data" --name krimidinner krimidinner
```

> **Wichtig:** `.env` enthält Passwort und API-Key. Die Datei steht in `.gitignore` und `.dockerignore`, gehört also nie ins Repo oder ins Image.
> Soll die App aus dem Internet erreichbar sein, stell einen Reverse-Proxy mit HTTPS davor (z. B. Caddy oder Traefik).

## Die Web-Oberfläche

- **Neues Kit**: Thema, Spielerzahl (3–12), Sprache (DE/EN), Papierformat und optional Illustrationen wählen. Der Fortschritt erscheint live: Gerüst → Texte → Logikprüfung → Korrekturen → PDFs.
- **Demo-Kit**: Ein fertiges Beispiel („Mord im Chalet Edelweiß“, Silvester 1985, 6 Spieler) funktioniert auch ohne API-Key.
- **Wiederholen**: Bricht eine Generierung ab, etwa weil das DeepSeek-Guthaben oder Gemini-Kontingent aufgebraucht ist oder der Server neu gestartet wurde, erscheint auf der Kit-Seite der Button **↻ Wiederholen**. Er macht beim letzten gesicherten Schritt weiter (Gerüst, Texte, jede Korrektur, Prüfung, jedes Bild). Bereits erledigte Schritte werden nicht noch einmal bezahlt, auch nicht mit „Cache umgehen“.
- **Kit-Seite**: alle PDFs zum Ansehen oder Herunterladen, Prüfbericht mit Gegencheck-Ergebnis und KI-Verbrauch (Aufrufe, Cache-Treffer, Tokens).
- **story.json bearbeiten**: Texte, Hinweise und Rätsel direkt im Browser ändern. Danach „Speichern & prüfen“ oder „Speichern & PDFs rendern“, beides ohne KI-Kosten. Die vorige Fassung bleibt als `story.backup.json` erhalten.

## Installation ohne Docker (Entwicklung / CLI)

Voraussetzung ist Python 3.11+. WeasyPrint braucht außerdem Pango und HarfBuzz:

| System | Befehl |
|---|---|
| Debian/Ubuntu | `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core` |
| macOS (Homebrew) | `brew install pango` |
| Windows | GTK-Laufzeit installieren (siehe [WeasyPrint-Doku](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows)) oder einfach Docker verwenden |

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # Key + Passwort eintragen
```

## Kommandozeile

```bash
krimi new --theme "Silvester im Schneechalet" --players 6 --lang de   # Story + Prüfung -> output/<kit>/story.json
krimi validate output/<kit>/story.json                                # Logikprüfung (+ KI-Gegencheck)
krimi validate output/<kit>/story.json --ohne-gegencheck              # nur die feste Prüfung, kostenlos
krimi render output/<kit> --paper a4                                  # PDFs neu setzen (a4 | letter)
krimi render output/<kit> --design gothic                             # ... in einem anderen Design
krimi designs                                                         # verfügbare Designs
krimi all --theme "..." --players 6                                   # alles in einem Lauf
krimi all --theme "..." --design artdeco                              # mit festem Design (Standard: auto)
krimi all --theme "..." --no-images --paper letter
krimi resume output/<kit>                                             # abgebrochenen Lauf fortsetzen (z. B. nach Kontingent-Ende)
krimi demo                                                            # Beispiel-Kit ohne API-Key
krimi serve --port 8000                                               # Web-Oberfläche
```

Nützliche Optionen:
- `--no-cache` umgeht den Cache und bezahlt die Aufrufe neu.
- `--variante 2` erzeugt eine andere Geschichte zum selben Thema.
- `-v` gibt ein ausführliches Log aus.

**Von Hand nachbessern:** `story.json` im Kit-Ordner bearbeiten, dann `krimi validate …` und `krimi render …` aufrufen. Beides kostet nichts.

## Wie die Logik sichergestellt wird

1. **Zweistufige Generierung**: Zuerst entsteht nur das *Gerüst* mit Täter, Motiven, Fakten, Zeitleiste und Alibis. Erst darauf bauen Charaktertexte, Hinweise und Runden auf.
2. **Feste Prüfung** (`validate.py`):
   - genau ein Täter
   - jede Figur hat Motiv, Geheimnis und Alibi
   - Hinweise verweisen nur auf existierende Figuren und Fakten
   - jeder Unschuldige wird entlastet, der Täter nie
   - der Täter wird durch mindestens 3 Hinweise mit *verschiedenen* Fakten belastet
   - jeder Spieler bekommt pro Runde mindestens einen Hinweis
   - Runden und Hinweise passen zusammen
   - niemand ist in der Zeitleiste gleichzeitig an zwei Orten (auch über Mitternacht)
3. **Gegencheck**: Ein separater KI-Aufruf (`DEEPSEEK_CHECK_MODEL` bzw. `GEMINI_CHECK_MODEL`) sieht *nur* die Verdächtigen und Hinweise, nicht die Lösung, und soll den Täter ermitteln. Nennt er jemand anderen oder liegt seine Sicherheit unter 70 %, gilt das Kit als mehrdeutig.
4. **Korrekturschleife**: Die Fehlerliste geht zurück an die KI, höchstens 3 Durchläufe. Danach bricht der Lauf mit einem klaren Bericht ab (`report.json` bzw. auf der Kit-Seite).

## KI-Anbieter: DeepSeek oder Gemini

Welcher Anbieter Story, Texte und Prüfung schreibt, legt `LLM_PROVIDER` in `.env` fest:

| | DeepSeek (`LLM_PROVIDER=deepseek`, Standard) | Gemini (`LLM_PROVIDER=gemini`) |
|---|---|---|
| Key | `DEEPSEEK_API_KEY` | `GEMINI_API_KEY` |
| Modelle | `DEEPSEEK_TEXT_MODEL`, `DEEPSEEK_CHECK_MODEL` (Default `deepseek-v4-flash`) | `GEMINI_TEXT_MODEL`, `GEMINI_CHECK_MODEL` |
| Strukturierte Ausgabe | JSON-Modus. Das Schema steht im Prompt, ungültige Antworten bessert das Modell bis zu 2× nach | natives `response_schema` |
| Bilder | nicht möglich, dafür zusätzlich `GEMINI_API_KEY` + `GEMINI_IMAGE_MODEL` setzen | `GEMINI_IMAGE_MODEL` |

DeepSeek-spezifische Einstellungen:
- `DEEPSEEK_MAX_TOKENS` legt die maximale Antwortlänge fest (Default 32000). Wird eine Antwort abgeschnitten, kommt eine klare Fehlermeldung.
- `DEEPSEEK_THINKING` kann `enabled` oder `disabled` sein, leer heißt Modell-Standard.
- `DEEPSEEK_BASE_URL` erlaubt einen anderen OpenAI-kompatiblen Endpunkt.

Modellnamen ändern sich. Die alten DeepSeek-Namen `deepseek-chat`/`deepseek-reasoner` wurden im Juli 2026 abgeschaltet. Aktuelle Namen findest du unter <https://api-docs.deepseek.com/quick_start/pricing> bzw. <https://ai.google.dev/gemini-api/docs/models>.

## Cache und Kosten

- **Cache**: Jede Antwort wird unter `sha256(Anbieter + Modell + Prompt + Schema)` in `.cache/` abgelegt. Ein zweiter Lauf mit denselben Eingaben kostet keine API-Aufrufe.
- Bei Rate-Limits (429), Serverfehlern und Timeouts wiederholt der Client den Aufruf mit exponentiellem Backoff. Ist das **Tageskontingent** (Gemini) bzw. das **Guthaben** (DeepSeek, HTTP 402) erschöpft, bricht er sofort mit einem klaren Hinweis ab. Der Fortschritt liegt dann in `output/<kit>/zwischenstand/` und lässt sich mit „Wiederholen“ bzw. `krimi resume` fortsetzen.
- Der Token-Verbrauch jedes Laufs steht in `output/<kit>/usage.json`, in der Konsole und auf der Kit-Seite.
- Alle Prompts liegen als Textdateien in `prompts/` und lassen sich dort anpassen.

## Projektstruktur

```
prompts/              Prompt-Vorlagen für die KI
src/krimi/
  models.py           Pydantic-Modelle (zugleich Schema für die JSON-Ausgabe der KI)
  llm_client.py       KI-Zugriff (DeepSeek / Gemini), Retry, Cache, JSON-Prüfung, Token-Zählung
  story.py            Generierung (Gerüst -> Ausarbeitung) und Korrektur
  validate.py         Logikprüfung + Gegencheck
  puzzles.py          Rätsel (Caesar, Substitution, Zahlenschloss, Wortsuche, Sitzordnung), ohne KI, mit Seed
  images.py           optionale Illustrationen
  themes.py           die PDF-Designs (Farben, Schriften, Ornamente, Bildstil)
  render.py           HTML -> PDF (WeasyPrint), Schnittmarken, Überlauf-Erkennung, ZIP
  pipeline.py         Gesamtablauf für CLI und Web
  cli.py              Kommandozeile
  web/                FastAPI-App, Vorlagen, CSS
  demo/               Beispiel-Kit (story.json)
templates/            PDF-Vorlagen (Jinja2), base.css, fonts/ (OFL/Apache-lizenziert)
tests/                pytest (Logikprüfung, Rätsel, KI-Client, Pipeline mit simulierter KI, Web)
```

`puzzles.py` hängt nicht von der Story ab und lässt sich auch für eigene Rätselhefte nutzen:
```python
from krimi import puzzles
puzzles.caesar("Treffpunkt um Mitternacht", seed=1).geheimtext
puzzles.word_search(["SCHNEE", "SEKT"], "Botschaft", seed=1).rows()
puzzles.seating_puzzle(["Anna", "Ben", "Cleo", "Dan"], seed=3).texte
```

## Tests

```bash
pytest
```

Die Tests laufen ohne API-Key: Die KI wird in `tests/test_pipeline.py` simuliert, die DeepSeek-API in `tests/test_llm_client.py` mit einem Schein-HTTP-Endpunkt. Geprüft werden Korrekturschleife, Cache (zweiter Lauf = 0 API-Aufrufe), `--no-cache` und Retry bei 429.

**Texte laufen nicht aus Boxen:** Nach dem Rendern misst `render.py` jede Karte und jedes Namensschild. Ragt Text über den Rand, wird die Schrift in Stufen verkleinert und neu gesetzt. Passt es trotzdem nicht, erscheint eine Warnung.

## Schriften

Alle Schriften stammen von Google Fonts und liegen lokal in `templates/fonts/`, die Lizenztexte daneben:
- **SIL Open Font License:** Playfair Display, Lora, Poiret One, Rye, Cinzel, IM Fell English, Montserrat, Work Sans und Josefin Sans.
- **Apache License 2.0:** Special Elite und Mountains of Christmas.
