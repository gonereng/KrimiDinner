"""Design-Themen für die PDFs – eine Quelle für Farben, Schriften, Ornamente und Bildstil.

Ein neues Thema hinzufügen: Eintrag in THEMES ergänzen (Schriften müssen in templates/fonts/
liegen und in FONT_FACES registriert sein). Optional zusätzliches CSS in `extra_css`.
Web-Oberfläche, KI-Prompt und PDF-Rendering übernehmen es automatisch.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_THEME = "klassisch"


@dataclass(frozen=True)
class Theme:
    name: str
    label: str
    beschreibung: str          # für Auswahl in der Web-App und für den KI-Prompt
    colors: dict = field(default_factory=dict)
    head: str = '"Playfair Display", serif'
    body: str = '"Lora", serif'
    head_transform: str = "none"   # z. B. uppercase für Art déco
    head_spacing: str = "normal"
    ornament: str = "✦ ✦ ✦"
    cover_symbol: str = "❦ ✦ ❦"
    small_symbol: str = "✦"
    masthead: str = "Der Landbote"
    bildstil: str = ""
    extra_css: str = ""

    def css(self) -> str:
        c = self.colors
        return f""":root {{
  --c-primary: {c['primary']}; --c-accent: {c['accent']}; --c-gold: {c['gold']}; --c-red: {c['red']};
  --c-ink: {c['ink']}; --c-muted: {c['muted']}; --c-line: {c['line']}; --c-paper: {c['paper']};
  --c-panel: {c['panel']}; --c-card: {c['card']};
  --c-cover-bg: {c['cover_bg']}; --c-cover-ink: {c['cover_ink']};
  --f-head: {self.head}; --f-body: {self.body};
}}
h1, h2, h3, .cover h1, .name, .tent .name {{ text-transform: {self.head_transform}; letter-spacing: {self.head_spacing}; }}
body {{ background: {c['paper']}; }}
@page {{ @top-center {{ content: "{self.ornament}"; font-family: "DejaVu Sans", serif; font-size: 7pt;
  letter-spacing: .5em; color: {c['accent']}; vertical-align: bottom; padding-bottom: 3mm; }} }}
@page cover {{ @top-center {{ content: none; }} }}
@page sheet {{ @top-center {{ content: none; }} }}
{self.extra_css}"""

    def swatch(self) -> list[str]:
        c = self.colors
        return [c["cover_bg"], c["primary"], c["accent"], c["gold"], c["red"], c["panel"]]


def _c(primary, accent, gold, red, ink, muted, line, paper, panel, card, cover_bg, cover_ink):
    return dict(primary=primary, accent=accent, gold=gold, red=red, ink=ink, muted=muted, line=line,
                paper=paper, panel=panel, card=card, cover_bg=cover_bg, cover_ink=cover_ink)


THEMES: dict[str, Theme] = {t.name: t for t in [
    Theme("klassisch", "Klassisch",
          "Landhaus, Agatha-Christie-Stil, zeitlos – passt zu fast allem",
          _c("#5a1e2a", "#8c6a3f", "#c8a45a", "#9c1c1c", "#2a2222", "#7a6d66", "#d6c8b5",
             "#fffdf8", "#f7f0e4", "#fffcf5", "#5a1e2a", "#fbf3e6"),
          ornament="✦ ✦ ✦", cover_symbol="❦ ✦ ❦", masthead="Der Landbote",
          bildstil="Aquarell-Illustration im Stil klassischer Kriminalromane der 1930er, warme Bordeaux- und Cremetöne"),
    Theme("chalet", "Chalet",
          "Winter, Berghütte, Schnee, Skiurlaub",
          _c("#1d2b44", "#4a6c8c", "#c9a227", "#a3302a", "#1f2430", "#6b7686", "#b9c6d3",
             "#ffffff", "#eef3f8", "#fbfdff", "#1d2b44", "#f4f7fb"),
          ornament="❄ ❄ ❄", cover_symbol="❄ ✦ ❄", small_symbol="❄", masthead="Bergbote",
          bildstil="Vintage-Gouache-Illustration im Stil alter Skiplakate der 1980er, gedeckte Blau- und Goldtöne, weiches Licht"),
    Theme("noir", "Film noir",
          "Großstadt, Detektivbüro, 1920er–1950er, Schwarz-Weiß",
          _c("#151515", "#6d6d6d", "#d8c8a0", "#b3121b", "#161616", "#777777", "#c8c8c8",
             "#ffffff", "#f1f1f1", "#ffffff", "#111111", "#eeeeee"),
          body='"Special Elite", monospace', ornament="✦ ✦ ✦", cover_symbol="✦ ✦ ✦",
          masthead="The Evening Star",
          bildstil="Schwarz-Weiß-Tuschezeichnung im Film-noir-Stil, harte Schatten, Kreuzschraffur"),
    Theme("weihnachten", "Weihnachten",
          "Heiligabend, Familienfest, Tannenbaum – Tannengrün, Kerzenrot und Gold",
          _c("#1f4d36", "#a8232e", "#d4a537", "#a8232e", "#22281f", "#6e7468", "#d8d0bd",
             "#fffdf6", "#f4efe2", "#fffcf2", "#173d2b", "#fdf6e3"),
          head='"Mountains of Christmas", "Playfair Display", serif',
          ornament="✶ ❦ ✶", cover_symbol="✶ ★ ✶", small_symbol="★", masthead="Der Weihnachtsbote",
          bildstil="Nostalgische Weihnachtskarten-Illustration, Tannengrün, Kerzenrot und Gold, warmes Kerzenlicht",
          extra_css=".cover .frame { border-width: 2pt; } .cover .frame::after { border-style: dashed; }"),
    Theme("artdeco", "Art déco",
          "Die Goldenen Zwanziger, Gatsby-Party, Jazz, Glamour – Schwarz und Gold",
          _c("#1d4a4a", "#9a7b3c", "#d4af5a", "#8f1d2c", "#161616", "#6f6a60", "#d9cfb6",
             "#fffdf7", "#f3eee2", "#fffcf4", "#121212", "#f5ecd7"),
          head='"Poiret One", "Josefin Sans", sans-serif', body='"Josefin Sans", sans-serif',
          head_transform="uppercase", head_spacing=".08em",
          ornament="◆ ◇ ◆", cover_symbol="◆ ◇ ◆ ◇ ◆", small_symbol="◆", masthead="The Daily Sparkle",
          bildstil="Art-déco-Plakatillustration der 1920er, geometrische Formen, Schwarz, Petrol und Gold",
          extra_css="""
h1, h2, h3 { font-weight: 400; }
h2 { border-bottom: 2pt double var(--c-gold); }
.cover .frame { border: 2pt solid var(--c-gold); }
.cover .frame::after { top: 4mm; left: 4mm; right: 4mm; bottom: 4mm; border: .6pt solid var(--c-gold); }
.box { border-radius: 0; border-left: 3pt solid var(--c-gold); }
.card .head { border-bottom: 1.2pt double var(--c-gold); }
body { font-size: 10.5pt; }"""),
    Theme("viktorianisch", "Viktorianisch",
          "London um 1890, Sherlock Holmes, Nebel, Gaslicht – Sepia und Pergament",
          _c("#4a3523", "#8b6b3e", "#b8955a", "#7d1f1f", "#2d2318", "#7a6a55", "#d4c4a4",
             "#fbf5e8", "#f2e8d4", "#fbf4e4", "#3a2a1b", "#f3e7cf"),
          head='"IM Fell English", "Playfair Display", serif', body='"IM Fell English", "Lora", serif',
          ornament="❧ ❦ ❧", cover_symbol="❧ ✦ ❦", small_symbol="❦", masthead="The London Chronicle",
          bildstil="Viktorianischer Kupferstich, feine Schraffuren, Sepiatöne, Gaslaternen und Nebel",
          extra_css="""
body { font-size: 11pt; }
.box { border-style: double; border-width: 2.4pt; }
.cover .frame { border-style: double; border-width: 3pt; }"""),
    Theme("riviera", "Riviera",
          "Côte d'Azur, Yacht, Sommer in den 1960ern – Türkis, Koralle und Sand",
          _c("#16657a", "#e0674a", "#e9b949", "#c7432b", "#1f2b30", "#6a7a80", "#c9dde2",
             "#fffdf9", "#eaf5f6", "#fffefb", "#16657a", "#fff8ec"),
          head='"Josefin Sans", sans-serif', body='"Lora", serif',
          head_transform="uppercase", head_spacing=".06em",
          ornament="~ ✦ ~", cover_symbol="☀ ~ ☀", small_symbol="☀", masthead="Il Corriere della Costa",
          bildstil="Sonniges Reiseplakat der 1960er im Riviera-Stil, Türkis, Koralle und Sandtöne, flache Formen",
          extra_css="""
h1, h2 { font-weight: 700; }
.box { border-radius: 6pt; }
.card { border-radius: 3mm; }"""),
    Theme("western", "Wilder Westen",
          "Saloon, Goldgräberstadt, Postkutsche – Leder, Holz und Staub",
          _c("#5b3a1e", "#a4442a", "#c69b3c", "#8e2a1a", "#2f2219", "#7f6a55", "#d9c6a5",
             "#fbf3e2", "#f1e3c6", "#fbf1dc", "#3f2814", "#f6e8c8"),
          head='"Rye", "Playfair Display", serif', body='"Lora", serif',
          ornament="★ ✦ ★", cover_symbol="★ ★ ★", small_symbol="★", masthead="The Frontier Gazette",
          bildstil="Holzschnitt-Illustration im Stil alter Steckbriefe und Westernplakate, Sepia und Rostrot",
          extra_css="""
h1, h2, h3 { font-weight: 400; }
.box { border: 1.4pt dashed var(--c-accent); }"""),
    Theme("gothic", "Gothic",
          "Spukschloss, Halloween, Gewitternacht – Mitternachtsviolett und Blutrot",
          _c("#2b1b3a", "#6b4c86", "#b9a7d4", "#8e1b1b", "#1d1622", "#6f6578", "#cfc5da",
             "#fdfbff", "#f1ecf6", "#fcfaff", "#160e1f", "#ece4f5"),
          head='"Cinzel", serif', body='"Lora", serif', head_spacing=".03em",
          ornament="☾ ✦ ☽", cover_symbol="☾ ✦ ☽", small_symbol="✦", masthead="Der Nachtkurier",
          bildstil="Düstere Gothic-Illustration, Mondlicht, Spukschloss, tiefes Violett und Schwarz, kein Blut"),
    Theme("modern", "Modern",
          "Heute: Start-up, Krimi-Podcast, Influencer-Villa – klar, minimalistisch, serifenlos",
          _c("#111111", "#2f6fde", "#f2b705", "#d6336c", "#1a1a1a", "#6b6b6b", "#e2e2e2",
             "#ffffff", "#f3f6fb", "#ffffff", "#111111", "#ffffff"),
          head='"Montserrat", sans-serif', body='"Work Sans", sans-serif',
          ornament="— • —", cover_symbol="● ● ●", small_symbol="●", masthead="Stadt-Anzeiger",
          bildstil="Moderne flache Vektor-Illustration, klare Formen, Schwarz mit Blau- und Gelbakzenten",
          extra_css="""
h1, h2, h3 { font-weight: 700; }
h2 { border-bottom: 2pt solid var(--c-accent); }
.box { border-radius: 4pt; border: 0; background: var(--c-panel); }
.cover .frame, .cover .frame::after { border-color: var(--c-accent); }"""),
]}

# @font-face-Regeln für alle lokal eingebundenen Schriften (Dateien in templates/fonts/)
FONT_FACES = [
    ("Playfair Display", "playfair-display-latin-400-normal.woff", 400, "normal"),
    ("Playfair Display", "playfair-display-latin-700-normal.woff", 700, "normal"),
    ("Playfair Display", "playfair-display-latin-400-italic.woff", 400, "italic"),
    ("Lora", "lora-latin-400-normal.woff", 400, "normal"),
    ("Lora", "lora-latin-700-normal.woff", 700, "normal"),
    ("Lora", "lora-latin-400-italic.woff", 400, "italic"),
    ("Special Elite", "special-elite-latin-400-normal.woff", 400, "normal"),
    ("Poiret One", "poiret-one-latin-400-normal.woff", 400, "normal"),
    ("Rye", "rye-latin-400-normal.woff", 400, "normal"),
    ("Cinzel", "cinzel-latin-400-normal.woff", 400, "normal"),
    ("Cinzel", "cinzel-latin-700-normal.woff", 700, "normal"),
    ("IM Fell English", "im-fell-english-latin-400-normal.woff", 400, "normal"),
    ("IM Fell English", "im-fell-english-latin-400-italic.woff", 400, "italic"),
    ("Montserrat", "montserrat-latin-400-normal.woff", 400, "normal"),
    ("Montserrat", "montserrat-latin-700-normal.woff", 700, "normal"),
    ("Work Sans", "work-sans-latin-400-normal.woff", 400, "normal"),
    ("Work Sans", "work-sans-latin-700-normal.woff", 700, "normal"),
    ("Mountains of Christmas", "mountains-of-christmas-latin-400-normal.woff", 400, "normal"),
    ("Mountains of Christmas", "mountains-of-christmas-latin-700-normal.woff", 700, "normal"),
    ("Josefin Sans", "josefin-sans-latin-400-normal.woff", 400, "normal"),
    ("Josefin Sans", "josefin-sans-latin-700-normal.woff", 700, "normal"),
]


def font_face_css(base_url: str) -> str:
    return "\n".join(
        f'@font-face {{ font-family: "{fam}"; src: url("{base_url}/{file}"); '
        f"font-weight: {w}; font-style: {style}; }}"
        for fam, file, w, style in FONT_FACES)


def get_theme(name: str | None) -> Theme:
    return THEMES.get((name or "").strip().lower(), THEMES[DEFAULT_THEME])


def normalize(name: str | None) -> str:
    """Unbekannte Namen (z. B. von der KI erfunden) -> Standard-Thema."""
    n = (name or "").strip().lower()
    return n if n in THEMES else DEFAULT_THEME


def prompt_list() -> str:
    return "\n".join(f'   - "{t.name}": {t.beschreibung}' for t in THEMES.values())
