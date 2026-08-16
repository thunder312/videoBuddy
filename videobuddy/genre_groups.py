"""Kuratierte Genre-Gruppen für die Spielfilm-Suchbegriffe.

Der EPG-Feed (epgshare01, siehe config.yaml) nutzt für "category" extrem
granulare, uneinheitlich zusammengesetzte Tags (z. B. "Sci-Fi-Film",
"Sci-Fi-Action", "Science-Fiction" nebeneinander für dasselbe Genre). Reine
Teilstring-Suche (siehe candidates.py) fängt zusammengesetzte Varianten mit
gemeinsamem Wortstamm zwar schon ab (z. B. "Sci-Fi" matcht "Sci-Fi-Action"),
aber nicht Tags ohne gemeinsamen Text (z. B. "Sci-Fi" matcht NICHT
"Science-Fiction").

Diese Tabelle bildet deshalb von Hand identifizierte deutschsprachige
Oberbegriffe auf die exakten, tatsächlich im Feed vorkommenden Tags ab.
Trägt der Nutzer einen dieser Oberbegriffe (Schlüssel, Groß-/Kleinschreibung
egal) als Spielfilm-Suchbegriff ein, matcht build_candidates() zusätzlich
alle hier hinterlegten Tags - unabhängig davon, ob sie den Suchbegriff als
Teilstring enthalten.

Basis: Analyse aller ~917 im Feed vorkommenden category-Tags (Stand
2026-08-16, Quelle epg_ripper_DE1.xml.gz). Fremdsprachige Tags (en/fr/it/nl/
tr/da aus international mitgelieferten Kanälen) wurden bewusst ausgelassen -
für die auf deutsche Sender ausgerichtete Vorschlagsliste nicht relevant.
Reine TV-Formate (Dokureihe, -soap, -magazin, Satire/Kabarett/Sitcom) wurden
bewusst NICHT aufgenommen, auch wenn sie genrenah sind: das sind Serien-/
Sendungsformate statt abendfüllender Spielfilme, siehe README "Was ist ein
Vorschlag".
"""

from __future__ import annotations

GENRE_GROUPS: dict[str, tuple[str, ...]] = {
    "Sci-Fi": (
        "Sci-Fi-Abenteuer", "Sci-Fi-Action", "Sci-Fi-Actiondrama",
        "Sci-Fi-Anime", "Sci-Fi-Comedyserie", "Sci-Fi-Drama",
        "Sci-Fi-Dramaserie", "Sci-Fi-Film", "Sci-Fi-Horror",
        "Sci-Fi-Klassiker", "Sci-Fi-Komödie", "Sci-Fi-Popmärchen",
        "Sci-Fi-Satire", "Sci-Fi-Serie", "Sci-Fi-Thriller",
        "Science fiction", "Science-Fiction", "Science-Fiction-Drama",
        "Science-Fiction-Thriller", "Science-fiction series",
    ),
    "Krimi": (
        "Abenteuerkrimi", "Action-Krimi", "Actionkrimi", "Detektivserie",
        "Fantasykrimiserie", "Gangsterkrimi", "Justizkrimi",
        "Kampfkunst-Actionkrimi", "Krimi", "Krimi-Komödie", "Krimidoku",
        "Krimidrama", "Krimidramaserie", "Krimierie", "Krimikomödienserie",
        "Kriminaldrama", "Kriminalepos", "Kriminalfilm",
        "Kriminalhistorische Dokureihe", "Kriminalistikreihe", "Krimiposse",
        "Krimireihe", "Krimiserie", "Krimiulk", "Mysterykrimi", "Noir-Krimi",
        "Psychokrimi", "TV-Fahndung", "TV-Krimi",
    ),
    "Action": (
        "Action", "Action-Drama", "Action-Drama-Serie", "Action-Komödie",
        "Action-Krimi", "Action-Thriller", "Actionabenteuer", "Actiondrama",
        "Actionfantasy", "Actionfilm", "Actionhorror", "Actionkomödie",
        "Actionkrimi", "Actionparodie", "Actionserie", "Actionspektakel",
        "Actionthriller", "Agentenaction", "Antikaction",
        "Digitaltrickaction", "Fallschirmspringer-Action", "Fantasy-Action",
        "Fantasyaction", "Kampfkunst-Actionkrimi", "Katastrophenaction",
        "Kifferactionkomödie", "PS-Action", "Saurieraction",
        "Sci-Fi-Action", "Sci-Fi-Actiondrama", "Superhelden-Action",
        "Superhelden-Actiondrama", "Superheldenaction",
    ),
    "Abenteuer": (
        "Abenteuer", "Abenteuerdrama", "Abenteuerfilm", "Abenteuerkomödie",
        "Abenteuerkrimi", "Abenteuerparodie", "Abenteuerserie",
        "Actionabenteuer", "Fantasy-Abenteuer", "Fantasyabenteuer",
        "Historienabenteuer", "Horrorabenteuer", "Karl-May-Abenteuer",
        "Monumentalabenteuer", "Mädchenabenteuer", "Orientabenteuer",
        "Romantisches Abenteuerdrama", "Sci-Fi-Abenteuer", "Taucherabenteuer",
        "Trickabenteuer", "Westernabenteuer", "Zeichentrickabenteuer",
    ),
    "Animation": (
        "3D-Animationsserie", "Animation", "Animationskomödie",
        "Animationsserie", "Anime", "Animeserie", "Computertrickkomödie",
        "Computertrickserie", "Computertrickspaß",
        "Digitaltrick-Westernkomödie", "Digitaltrickaction",
        "Digitrickkomödie", "Digitrickmärchen", "Knetanimationsserie",
        "Sci-Fi-Anime", "Trickabenteuer", "Trickserie", "Zeichentrick",
        "Zeichentrickabenteuer", "Zeichentrickmärchen", "Zeichentrickserie",
    ),
    "Komödie": (
        "Abenteuerkomödie", "Abenteuerparodie", "Action-Komödie",
        "Actionkomödie", "Actionparodie", "Agentenklamauk",
        "Animationskomödie", "Arzttragikomödie", "Beziehungskomödie",
        "Buddy-Komödie", "Cartoonklamauk", "Cheerleaderkomödie",
        "College-Komödie", "Computertrickkomödie",
        "Digitaltrick-Westernkomödie", "Digitrickkomödie", "Erotikkomödie",
        "Familienkomödie", "Familientragikomödie", "Fantasykomödie",
        "Gaunerkomödie", "Heimat-Tragikomödie", "Horror-Komödie",
        "Horrorkomödie", "Kfz-Klamotte", "Kifferactionkomödie", "Komödie",
        "Kostümkomödie", "Krimi-Komödie", "Krimikomödienserie", "Krimiposse",
        "Krimiulk", "Liebeskomödie", "Lustspiel", "Mallorca-Klamotte",
        "Musikkomödie", "Politposse", "Provinzkomödie", "Romantikkomödie",
        "Romantische Komödie", "Schwarze Komödie", "Sci-Fi-Komödie",
        "Sexgaudi", "Sexklamauk", "Sexklamotte", "Sexkomödie",
        "Teenie-Klamauk", "Thrillerkomödie", "Tragikomödie",
        "Westernkomödie", "Westernparodie",
    ),
    "Drama": (
        "Abenteuerdrama", "Action-Drama", "Action-Drama-Serie", "Actiondrama",
        "Bergsteigerdrama", "Biopic-Drama", "Bollywood-Liebesdrama",
        "Boxer-Drama", "Boxerdrama", "Börsendrama", "Drama",
        "Drama-Miniserie", "Dramaserie", "Episodendrama", "Erotikdrama",
        "Erotisches Drama", "Familiendrama", "Filmkunstdrama", "Finanzdrama",
        "Fluchtdrama", "Gangsterdrama", "Gefängnisdrama", "Geschichtsdrama",
        "Gewaltdrama", "Heimatdrama", "Historiendrama", "Horrordrama",
        "Hundedrama", "Katastrophendrama", "Kriegsdrama", "Krigesdrama",
        "Krimidrama", "Krimidramaserie", "Kriminaldrama", "Liebesdrama",
        "Martial-Arts-Drama", "Monumentaldrama", "Mystery-Thrillerdramaserie",
        "Ne-Western-Drama", "Politdrama", "Psychodrama", "Robinsondrama",
        "Romantisches Abenteuerdrama", "Samurai-Drama", "Sci-Fi-Actiondrama",
        "Sci-Fi-Drama", "Sci-Fi-Dramaserie", "Science-Fiction-Drama",
        "Sozialdrama", "Sportlerdrama", "Superhelden-Actiondrama", "TV-Drama",
        "Tanzdrama", "Thrillerdrama",
    ),
    "Fantasy": (
        "Actionfantasy", "Digitrickmärchen", "Fantasy", "Fantasy-Abenteuer",
        "Fantasy-Action", "Fantasyabenteuer", "Fantasyaction", "Fantasyfilm",
        "Fantasykomödie", "Fantasykrimiserie", "Fantasyserie", "Märchen",
        "Märchenfilm", "Sci-Fi-Popmärchen", "Zeichentrickmärchen",
    ),
    "Horror": (
        "Actionhorror", "Grusel-Comedyserie", "Gruselromanze", "Gruselsoap",
        "Hai-Horror-Trash", "Horror", "Horror-Komödie", "Horror-Serie",
        "Horrorabenteuer", "Horrordrama", "Horrorfilm", "Horrorkomödie",
        "Horrorpersiflage", "Horrorthriller", "Sci-Fi-Horror",
        "Teeniehorrorserie",
    ),
    "Historie": (
        "Historie", "Historienabenteuer", "Historiendrama",
        "Historienromanze", "Historienserie", "Historiensoap",
        "Kriminalhistorische Dokureihe", "Mantel-und-Degen-Film",
        "Monumentalabenteuer", "Monumentaldrama", "Monumentalepos",
        "Sandalenfilm",
    ),
    "Katastrophenfilm": (
        "Katastrophenaction", "Katastrophendrama", "Katastrophenfilm",
    ),
    "Kriegsfilm": (
        "Bürgerkriegswestern", "Kriegsdrama", "Kriegsepos", "Kriegsfilm",
        "Kriegssatire",
    ),
    "Liebesfilm": (
        "Bollywood-Liebesdrama", "Familienmelodram", "Gruselromanze",
        "Historienromanze", "Las-Vegas-Romanze", "Liebesdrama", "Liebesfilm",
        "Liebeskomödie", "Liebesmelodram", "Melodram", "Musicalromanze",
        "Musikromanze", "Romantikkomödie", "Romantische Komödie",
        "Romantisches Abenteuerdrama", "Romanze", "Thrillermelodram",
        "Urlaubsromanze",
    ),
    "Musical": (
        "Musical", "Musicalklassiker", "Musicalromanze", "Musikfilm",
        "Musikkomödie", "Musikromanze", "Musikschmonzette",
    ),
    "Mystery": (
        "Mystery", "Mystery-Thrillerdramaserie", "Mystery-Thrillerserie",
        "Mysterydoku", "Mysterydokureihe", "Mysterydokursoap", "Mysterykrimi",
        "Mysteryserie", "Mysterythriller",
    ),
    "Thriller": (
        "Action-Thriller", "Actionthriller", "Agententhriller",
        "Bergsteigerthriller", "Horrorthriller", "Mystery-Thrillerdramaserie",
        "Mystery-Thrillerserie", "Mysterythriller", "Politthriller",
        "Polizeithriller", "Psychothriller", "Rechtsmedizinthriller",
        "Saurierthriller", "Sci-Fi-Thriller", "Science-Fiction-Thriller",
        "Survivalthriller", "Thriller", "Thrillerdrama", "Thrillerkomödie",
        "Thrillermelodram", "Thrillerserie",
    ),
    "Western": (
        "B-Western", "Bürgerkriegswestern", "Digitaltrick-Westernkomödie",
        "Italowestern", "Ne-Western-Drama", "Neowesternserie", "Western",
        "Westernabenteuer", "Westernklassiker", "Westernkomödie",
        "Westernparodie", "Westernsatire", "Westernserie",
    ),
    "Dokumentarfilm": (
        "Dokumentarfilm",
    ),
    "Erotik": (
        "Erotikdrama", "Erotikfilm", "Erotikkomödie", "Erotikserie",
        "Sexfilm", "Sexgaudi", "Sexklamauk", "Sexklamotte", "Sexkomödie",
    ),
    "Familienfilm": (
        "Familienchronik", "Familiendrama", "Familiendramödie",
        "Familienfilm", "Familienkomödie", "Familienmelodram",
        "Familienserie", "Familientragikomödie",
    ),
}

GENRE_GROUPS_LOWER: dict[str, tuple[str, ...]] = {
    name.lower(): tags for name, tags in GENRE_GROUPS.items()
}
