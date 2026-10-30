"""Résolution d'identité typée : une question nomme une application, un twin ou un dépôt.

Une application est l'entité métier canonique ; un twin en est la représentation numérique durable et peut rester
provisoire ; un dépôt n'est jamais une application, seulement une SourceArtifact qui prouve le rattachement à un twin.
Le résolveur ne consulte ni modèle, ni base, ni réseau : il travaille sur les jumeaux du registre et rend toujours un
chemin typé, avec ses candidats et ses incertitudes. Une absence n'est jamais une preuve d'inexistence.
"""
from dataclasses import asdict, dataclass, field
import difflib
import re
import unicodedata

SEUIL_FAUTE = 0.85  # « conduite » ↔ « conduit » : 0,93 ; « conduire » ↔ « conduit » : 0,80 (refusé)

STATUTS_ACTIFS = {
    "actif", "active", "actifs", "actives", "canonique", "en production", "production",
    "operationnel", "operationnelle", "admis", "admise",
}
MISSIONS_PROVISOIRES = {
    "aucune", "dfggg", "inconnu", "inconnue", "sans mission", "tbd", "todo",
}
FRAGMENTS_MISSION_PROVISOIRE = (
    "a confirmer", "a definir", "a preciser", "dfggg", "mission inconnue",
    "non declare", "non declaree", "non renseigne", "non renseignee", "placeholder",
)
NOMS_PROVISOIRES = {
    "jumeau provisoire", "non nomme", "non nommee", "nouveau jumeau", "nouvelle jumeau",
    "placeholder", "sans nom", "twin provisoire", "untitled",
}

RE_JETON = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+")


@dataclass
class Resolution:
    question: str
    mentions: list[dict] = field(default_factory=list)
    chemin: list[dict] = field(default_factory=list)
    twin_id: str | None = None
    application_id: str | None = None
    statut: str = "absent"
    confiance: float = 0.0
    motif: str = ""
    candidats: list[dict] = field(default_factory=list)
    requires_confirmation: bool = False
    ambigu: bool = False
    absent: bool = False

    def as_dict(self):
        return asdict(self)

    def preambule(self):
        """Ce que Flore doit dire avant la réponse : identité provisoire, ambiguïté, absence non concluante."""
        if self.statut == "provisoire":
            source = next((e for e in self.chemin if e.get("type") == "source"), None)
            twin = next((e for e in self.chemin if e.get("type") == "twin"), None)
            depot = source["id"].split(":", 1)[-1] if source else None
            nom = twin.get("libelle") if twin else None
            debut = (f"J'ai trouvé la source `{depot}` rattachée au twin provisoire **{nom}**"
                     if depot and nom else f"J'ai trouvé un twin provisoire **{nom or 'sans nom'}**")
            proposition = f" Veux-tu le promouvoir en application **{depot}** ?" if depot else ""
            return f"{debut}. Son identité d'application n'est pas encore promue.{proposition}"
        if self.statut == "ambigu":
            noms = ", ".join(f"`{c.get('id')}`" for c in self.candidats[:5])
            return f"J'ai trouvé plusieurs twins candidats ({noms}) : lequel veux-tu consulter ?"
        if self.absent and any(m.get("type") != "inconnu" for m in self.mentions):
            return ("Je n'ai trouvé aucun twin dans le périmètre consulté. Ce n'est pas une preuve d'absence ; "
                    "précise l'application, le dépôt ou le service.")
        return ""


@dataclass(frozen=True)
class _Jeton:
    texte: str
    norme: str
    debut: int
    fin: int


def _normaliser(texte):
    sans_accents = unicodedata.normalize("NFKD", str(texte or "").lower())
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", sans_accents))


def _jetons(texte):
    return [_Jeton(m.group(0), _normaliser(m.group(0)), m.start(), m.end()) for m in RE_JETON.finditer(texte)]


def _occurrences(jetons, cible):
    mots = cible.split()
    if not mots:
        return []
    trouvees = []
    for i in range(len(jetons) - len(mots) + 1):
        if [j.norme for j in jetons[i:i + len(mots)]] == mots:
            trouvees.append((i, i + len(mots), jetons[i].debut, jetons[i + len(mots) - 1].fin))
    return trouvees


def _occurrences_floues(jetons, cible):
    """Une faute de frappe par mot, jamais sur un nom de dépôt : les sources se reconnaissent à l'identique."""
    mots = cible.split()
    if not mots or len("".join(mots)) < 5:
        return []
    trouvees = []
    for i in range(len(jetons) - len(mots) + 1):
        fenetre = [j.norme for j in jetons[i:i + len(mots)]]
        if fenetre == mots:
            continue
        ratios = [difflib.SequenceMatcher(None, attendu, lu).ratio() for attendu, lu in zip(mots, fenetre)]
        if min(ratios) >= SEUIL_FAUTE:
            trouvees.append((i, i + len(mots), jetons[i].debut, jetons[i + len(mots) - 1].fin,
                             round(sum(ratios) / len(ratios), 4)))
    return trouvees


def _chevauche(a, b):
    return a["debut"] < b["fin"] and b["debut"] < a["fin"]


def _sans_chevauchement(correspondances):
    """Garde les mentions les plus précises d'un même twin (le nom complet plutôt qu'un identifiant contenu)."""
    gardees = []
    for c in sorted(correspondances, key=lambda x: (-(x["fin"] - x["debut"]), x["debut"],
                                                    0 if x["matched_on"] == "nom" else 1)):
        if not any(_chevauche(c, g) for g in gardees):
            gardees.append(c)
    return sorted(gardees, key=lambda x: x["debut"])


def _provisoire(jumeau):
    """Un twin est provisoire par sa mission, son nom ou son statut — jamais par la seule absence d'un champ."""
    raisons = []
    mission = str(jumeau.get("mission") or "").strip()
    mission_norme = _normaliser(mission)
    if not mission:
        raisons.append("mission absente")
    elif mission_norme in MISSIONS_PROVISOIRES or any(f in mission_norme for f in FRAGMENTS_MISSION_PROVISOIRE):
        raisons.append(f"mission provisoire « {mission} »")

    nom = str(jumeau.get("nom") or "").strip()
    nom_norme = _normaliser(nom)
    if not nom_norme or nom_norme in NOMS_PROVISOIRES or nom_norme.startswith("nouveau jumeau"):
        raisons.append(f"nom provisoire « {nom or 'sans nom'} »")

    statut = str(jumeau.get("statut") or "").strip()
    if statut and _normaliser(statut) not in STATUTS_ACTIFS:
        raisons.append(f"statut non actif « {statut} »")
    return bool(raisons), raisons


def _nom_depot(texte):
    brut = re.split(r"\s*[·|]\s*", str(texte or "").strip(), maxsplit=1)[0]
    brut = re.sub(r"^\s*(?:D[ée]p[oô]t|Depot|Repository|Repo)\s+", "", brut, flags=re.IGNORECASE)
    return brut.strip()


def _sources(jumeau):
    for source in jumeau.get("sources_detail") or []:
        if not isinstance(source, dict):
            continue
        cle = str(source.get("cle") or "").strip()
        nom = str(source.get("nom") or "").strip()
        if not cle and not nom:
            continue
        repo = cle[4:] if cle.lower().startswith("git-") else cle
        repo_nom = _nom_depot(nom) or repo
        if not repo:
            repo = repo_nom
        if not repo:
            continue
        yield {
            "cle": cle,
            "repo": repo,
            "repo_nom": repo_nom,
            "libelle": nom or f"Dépôt {repo}",
            "preuve": f"sources_detail.cle={cle}" if cle else f"sources_detail.nom={nom}",
        }


def _correspondances_application(jetons, jumeaux):
    correspondances = []
    for jumeau in jumeaux:
        jid = str(jumeau.get("id") or jumeau.get("nom") or "").strip()
        if not jid:
            continue
        provisoire, _ = _provisoire(jumeau)
        variantes, vues = [], set()
        for champ in ("nom", "id"):
            norme = _normaliser(jumeau.get(champ))
            if norme and norme not in vues:
                vues.add(norme)
                variantes.append((champ, norme))

        exactes = []
        for champ, norme in variantes:
            for _, _, debut, fin in _occurrences(jetons, norme):
                exactes.append({
                    "twin_id": jid, "type": "twin" if provisoire else "application",
                    "debut": debut, "fin": fin, "surface": None,
                    "matched_on": champ, "confiance": 1.0,
                })
        if exactes:
            correspondances.extend(_sans_chevauchement(exactes))
            continue

        floues = []
        for champ, norme in variantes:
            for _, _, debut, fin, confiance in _occurrences_floues(jetons, norme):
                floues.append({
                    "twin_id": jid, "type": "twin" if provisoire else "application",
                    "debut": debut, "fin": fin, "surface": None,
                    "matched_on": champ, "confiance": confiance,
                })
        if floues:
            correspondances.append(max(floues, key=lambda c: (c["confiance"], -(c["fin"] - c["debut"]))))
    return correspondances


def _correspondances_source(jetons, jumeaux):
    correspondances = []
    for jumeau in jumeaux:
        jid = str(jumeau.get("id") or jumeau.get("nom") or "").strip()
        if not jid:
            continue
        for source in _sources(jumeau):
            variantes = {}
            cle_explicite = bool(source["cle"]) and source["cle"].lower().startswith("git-")
            for valeur, explicite in ((source["cle"], cle_explicite), (source["repo"], False),
                                      (source["repo_nom"], False)):
                norme = _normaliser(valeur)
                if norme:
                    variantes[norme] = variantes.get(norme, False) or explicite
            trouvees = []
            for norme, explicite in variantes.items():
                for _, _, debut, fin in _occurrences(jetons, norme):
                    trouvees.append({
                        "twin_id": jid, "type": "source",
                        "debut": debut, "fin": fin, "surface": None,
                        "matched_on": "source", "confiance": 1.0, "explicite": explicite,
                        "source_id": f"repo:{source['repo']}", "source_libelle": source["libelle"],
                        "source_preuve": source["preuve"],
                    })
            if trouvees:
                correspondances.extend(_sans_chevauchement(trouvees))
    return correspondances


def _filtrer_precedence(applications, sources):
    """Une clé de dépôt explicite l'emporte ; sinon un nom d'application exact l'emporte sur un nom de dépôt.
    Un rapprochement flou d'application ne peut jamais masquer une source reconnue à l'identique."""
    applications_gardees = []
    for application in applications:
        masquee = any(
            _chevauche(application, source) and (source["explicite"] or application["confiance"] < 1.0)
            for source in sources
        )
        if not masquee:
            applications_gardees.append(application)
    sources_gardees = []
    for source in sources:
        cachee = (not source["explicite"]) and any(
            application["confiance"] >= 1.0 and _chevauche(application, source)
            for application in applications_gardees
        )
        if not cachee:
            sources_gardees.append(source)
    return applications_gardees, sources_gardees


def _candidat(correspondance, jumeau):
    provisoire, raisons = _provisoire(jumeau)
    return {
        "type": "twin",
        "id": str(jumeau.get("id") or jumeau.get("nom") or correspondance["twin_id"]),
        "libelle": str(jumeau.get("nom") or jumeau.get("id") or ""),
        "statut": "provisoire" if provisoire else "canonique",
        "preuve": "; ".join(raisons) if provisoire else f"correspondance {correspondance['matched_on']}",
        "provisoire": provisoire,
        "matched_on": correspondance["matched_on"],
        "confiance": round(correspondance["confiance"], 2),
    }


def _groupes(correspondances, par_id):
    groupes = []
    for c in correspondances:
        identifiant = c.get("source_id") if c["type"] == "source" else None
        cle = (c["debut"], c["fin"], identifiant)
        groupe = next((g for g in groupes if g["cle"] == cle), None)
        if groupe is None:
            groupe = {"cle": cle, "type": c["type"], "debut": c["debut"], "fin": c["fin"],
                      "matched_on": c["matched_on"], "correspondances": []}
            groupes.append(groupe)
        groupe["correspondances"].append(c)
        types = {x["type"] for x in groupe["correspondances"]}
        groupe["type"] = "source" if "source" in types else "twin" if types == {"twin"} else "application"
    for groupe in groupes:
        surfaces = sorted({c["surface"] for c in groupe["correspondances"] if c.get("surface")})
        groupe["surface"] = surfaces[0] if surfaces else ""
        candidats = []
        for c in groupe["correspondances"]:
            candidat = _candidat(c, par_id[c["twin_id"]])
            if candidat["id"] not in {x["id"] for x in candidats}:
                candidats.append(candidat)
        groupe["candidats"] = candidats
        groupe["id"] = (groupe["correspondances"][0].get("source_id") if groupe["type"] == "source"
                        else candidats[0]["id"] if len(candidats) == 1 else None)
        groupe["confiance"] = round(max(c["confiance"] for c in groupe["correspondances"]), 2)
    return sorted(groupes, key=lambda g: g["debut"])


def _entite(type_entite, identifiant, libelle, statut, preuve):
    return {"type": type_entite, "id": identifiant, "libelle": libelle, "statut": statut, "preuve": preuve}


def _chemin(groupe, jumeau, provisoire, raisons):
    jid = str(jumeau.get("id") or jumeau.get("nom") or "")
    nom = str(jumeau.get("nom") or jid)
    preuve_twin = "; ".join(raisons) if provisoire else (
        f"correspondance {groupe['matched_on']} ({groupe['confiance']:.2f})")
    twin = _entite("twin", jid, nom, "provisoire" if provisoire else "canonique", preuve_twin)
    application = _entite("application", jid, nom, "candidat" if provisoire else "canonique",
                          f"rattachement du twin {jid}")
    if groupe["type"] == "source":
        premiere = groupe["correspondances"][0]
        source = _entite("source", premiere["source_id"], premiere["source_libelle"], "preuve",
                         premiere["source_preuve"])
        return [source, twin, application]
    if groupe["type"] == "twin":
        return [twin, application]
    return [application]


def _motif(groupe, jumeau, provisoire, raisons):
    nom = str(jumeau.get("nom") or jumeau.get("id") or "")
    if provisoire:
        detail = " ; ".join(raisons)
        if groupe["type"] == "source":
            return (f"Dépôt rattaché au twin provisoire {nom} : application candidate, confirmation requise "
                    f"({detail}).")
        return f"Twin provisoire {nom} nommé directement : aucun échec, confirmation requise ({detail})."
    if groupe["type"] == "source":
        return f"Dépôt rattaché au twin canonique {nom} : application résolue."
    return f"Application canonique {nom} résolue par son {groupe['matched_on']}."


def resoudre(question: str, jumeaux: list[dict]) -> Resolution:
    question = str(question or "")
    jumeaux = [j for j in (jumeaux or []) if isinstance(j, dict) and (j.get("id") or j.get("nom"))]
    par_id = {str(j.get("id") or j.get("nom")): j for j in jumeaux}
    jetons = _jetons(question)

    applications = _correspondances_application(jetons, jumeaux)
    sources = _correspondances_source(jetons, jumeaux)
    applications, sources = _filtrer_precedence(applications, sources)

    for correspondance in applications + sources:
        correspondance["surface"] = question[correspondance["debut"]:correspondance["fin"]]

    groupes = _groupes(applications + sources, par_id)
    mentions = [{
        "surface": groupe["surface"],
        "type": groupe["type"],
        "id": groupe["id"],
        "matched_on": groupe["matched_on"],
        "confiance": groupe["confiance"],
    } for groupe in groupes]
    if not mentions:
        mentions.append({"surface": question.strip(), "type": "inconnu", "id": None,
                         "matched_on": "aucun", "confiance": 0.0})

    candidats = []
    for groupe in groupes:
        for candidat in groupe["candidats"]:
            if candidat["id"] not in {c["id"] for c in candidats}:
                candidats.append(candidat)

    if not candidats:
        return Resolution(
            question=question, mentions=mentions, statut="absent", confiance=0.0,
            motif="aucun candidat, absence non prouvée.",
            requires_confirmation=True, absent=True,
        )

    ambigu = len(candidats) > 1 or any(len(g["candidats"]) > 1 for g in groupes)
    if ambigu:
        return Resolution(
            question=question, mentions=mentions, statut="ambigu", confiance=0.5,
            motif="Plusieurs twins candidats pour la même mention : aucun twin retenu.",
            candidats=candidats, requires_confirmation=True, ambigu=True,
        )

    jumeau = par_id[candidats[0]["id"]]
    provisoire, raisons = _provisoire(jumeau)
    priorite = {"source": 0, "twin": 1, "application": 2}
    groupe = min((g for g in groupes if g["candidats"][0]["id"] == candidats[0]["id"]),
                 key=lambda g: priorite.get(g["type"], 3))
    statut = "provisoire" if provisoire else "canonique"
    return Resolution(
        question=question,
        mentions=mentions,
        chemin=_chemin(groupe, jumeau, provisoire, raisons),
        twin_id=candidats[0]["id"],
        application_id=candidats[0]["id"],
        statut=statut,
        confiance=groupe["confiance"],
        motif=_motif(groupe, jumeau, provisoire, raisons),
        candidats=candidats,
        requires_confirmation=provisoire,
    )
