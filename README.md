# Krimidinner-Generator

Erzeugt aus einem Thema ein komplettes, druckfertiges **Krimidinner-Kit** als PDFs: Story, Charaktere, Hinweise, Rätsel, Gastgeber-Anleitung, Einladungen, versiegelte Auflösung und mehr.
Die kreativen Teile schreibt **Google Gemini**. Die Logikprüfung, die Rätsel und das Layout übernimmt deterministischer Code.

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

Die Formate A4 und US Letter stehen zur Wahl. Es gibt drei Designs: `chalet`, `klassisch` und `noir`. Gemini wählt das passende Design zum Thema, in `story.json` lässt es sich ändern.

## Schnellstart mit Docker (empfohlen)

1. **Gemini-API-Key besorgen**: unter <https://aistudio.google.com/apikey> mit einem Google-Konto anmelden und auf „API-Schlüssel erstellen“ klicken.
2. **Konfiguration anlegen**:
   ```bash
   cp .env.example .env
   ```
   In `.env` eintragen:
   ```ini
   GEMINI_API_KEY=dein-key
   APP_PASSWORD=ein-gutes-passwort       # Passwort für die Web-Oberfläche
   SESSION_SECRET=langer-zufallsstring   # z. B. python -c "import secrets; print(secrets.token_hex(32))"
   ```
3. **Starten**:
   ```bash
   docker compose up -d --build
   ```
4. Im Browser **http://localhost:8000** öffnen und mit dem Passwort aus `.env` anmelden.

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
- **Wiederholen**: Bricht eine Generierung ab, etwa weil das Gemini-Kontingent aufgebraucht ist oder der Server neu gestartet wurde, erscheint auf der Kit-Seite der Button **↻ Wiederholen**. Er macht beim letzten gesicherten Schritt weiter (Gerüst, Texte, jede Korrektur, Prüfung, jedes Bild). Bereits erledigte Schritte werden nicht noch einmal bezahlt, auch nicht mit „Cache umgehen“.
- **Kit-Seite**: alle PDFs zum Ansehen oder Herunterladen, Prüfbericht mit Gegencheck-Ergebnis und Gemini-Verbrauch (Aufrufe, Cache-Treffer, Tokens).
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
krimi validate output/<kit>/story.json                                # Logikprüfung (+ Gemini-Gegencheck)
krimi validate output/<kit>/story.json --ohne-gegencheck              # nur die feste Prüfung, kostenlos
krimi render output/<kit> --paper a4                                  # PDFs neu setzen (a4 | letter)
krimi all --theme "..." --players 6                                   # alles in einem Lauf
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
3. **Gegencheck**: Ein separater Gemini-Aufruf (`GEMINI_CHECK_MODEL`) sieht *nur* die Verdächtigen und Hinweise, nicht die Lösung, und soll den Täter ermitteln. Nennt er jemand anderen oder liegt seine Sicherheit unter 70 %, gilt das Kit als mehrdeutig.
4. **Korrekturschleife**: Die Fehlerliste geht zurück an Gemini, höchstens 3 Durchläufe. Danach bricht der Lauf mit einem klaren Bericht ab (`report.json` bzw. auf der Kit-Seite).

## Gemini: Modelle, Cache, Kosten

- Die Modelle stehen in `.env`: `GEMINI_TEXT_MODEL`, `GEMINI_CHECK_MODEL` und optional `GEMINI_IMAGE_MODEL`. Die Defaults in `.env.example` entsprechen dem Stand vom November 2026. Aktuelle Namen findest du unter <https://ai.google.dev/gemini-api/docs/models>.
- **Cache**: Jede Antwort wird unter `sha256(Modell + Prompt + Schema)` in `.cache/` abgelegt. Ein zweiter Lauf mit denselben Eingaben kostet keine API-Aufrufe.
- Bei Rate-Limits (429), Serverfehlern und Timeouts wiederholt der Client den Aufruf mit exponentiellem Backoff. Ist das **Tageskontingent** erschöpft, bricht er sofort mit einem klaren Hinweis ab. Der Fortschritt liegt dann in `output/<kit>/zwischenstand/` und lässt sich mit „Wiederholen“ bzw. `krimi resume` fortsetzen.
- Der Token-Verbrauch jedes Laufs steht in `output/<kit>/usage.json`, in der Konsole und auf der Kit-Seite.
- Alle Prompts liegen als Textdateien in `prompts/` und lassen sich dort anpassen.

## Projektstruktur

```
prompts/              Prompt-Vorlagen für Gemini
src/krimi/
  models.py           Pydantic-Modelle (zugleich Schema für Geminis JSON-Ausgabe)
  gemini_client.py    API-Zugriff, Retry, Cache, Token-Zählung
  story.py            Generierung (Gerüst -> Ausarbeitung) und Korrektur
  validate.py         Logikprüfung + Gegencheck
  puzzles.py          Rätsel (Caesar, Substitution, Zahlenschloss, Wortsuche, Sitzordnung), ohne KI, mit Seed
  images.py           optionale Illustrationen
  render.py           HTML -> PDF (WeasyPrint), Schnittmarken, Überlauf-Erkennung, ZIP
  pipeline.py         Gesamtablauf für CLI und Web
  cli.py              Kommandozeile
  web/                FastAPI-App, Vorlagen, CSS
  demo/               Beispiel-Kit (story.json)
templates/            PDF-Vorlagen (Jinja2), base.css, themes/*.css, fonts/ (OFL/Apache-lizenziert)
tests/                pytest (Logikprüfung, Rätsel, Pipeline mit simuliertem Gemini, Web)
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

Die Tests laufen ohne API-Key: Gemini wird in `tests/test_pipeline.py` simuliert. Geprüft werden Korrekturschleife, Cache (zweiter Lauf = 0 API-Aufrufe), `--no-cache` und Retry bei 429.

**Texte laufen nicht aus Boxen:** Nach dem Rendern misst `render.py` jede Karte und jedes Namensschild. Ragt Text über den Rand, wird die Schrift in Stufen verkleinert und neu gesetzt. Passt es trotzdem nicht, erscheint eine Warnung.

## Schriften

Playfair Display und Lora stehen unter der SIL Open Font License, Special Elite unter der Apache License 2.0. Alle liegen lokal in `templates/fonts/`, die Lizenztexte daneben.
