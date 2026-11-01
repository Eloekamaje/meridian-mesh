"""Conception greenfield : proposer l'architecture d'une application qui n'existe pas encore.

Aucun jumeau n'est mobilisé : il n'y a ni code, ni connaissances, ni preuves d'entreprise à consulter. Flore
propose donc une architecture cible explicitement hypothétique, avec ses composants, ses liens, ses hypothèses
et son hors-périmètre. Le schéma rendu à l'interface est une proposition (`mode="proposition"`, flèches
`etat="propose"`), jamais une description prouvée.
"""
import logging
import re
import unicodedata

from pydantic import BaseModel, Field
from strands import Agent

from meridian.adapters.outbound.llm import agent
from meridian.application import mesure

journal = logging.getLogger("meridian.conception")
MAX_BOITES, MAX_LIENS = 12, 20
MAX_HYPOTHESES, MAX_HORS_SCOPE = 12, 10
MAX_TEXTE, MAX_LIBELLE = 400, 80


class Composant(BaseModel):
    id: str = Field(description="identifiant stable et court, sans espace (ex. matching)")
    nom: str = Field(description="nom lisible du composant")
    role: str = Field(description="responsabilité principale du composant")


class Lien(BaseModel):
    de: str = Field(description="id du composant source")
    vers: str = Field(description="id du composant cible")
    libelle: str = Field(description="ce qui circule ou ce que fait le lien")


class ArchitectureCible(BaseModel):
    titre: str = Field(description="titre de l'architecture proposée")
    resume: str = Field(description="résumé de la proposition et de ses choix structurants")
    hypotheses: list[str] = Field(default_factory=list, description="hypothèses explicites de la proposition")
    composants: list[Composant] = Field(default_factory=list, description="composants de l'architecture cible")
    liens: list[Lien] = Field(default_factory=list, description="liens entre composants, par leurs ids")
    hors_scope: list[str] = Field(default_factory=list, description="ce que la proposition ne couvre pas")


PROMPT_SYSTEME = """Tu es un architecte logiciel. Tu conçois une application qui n'existe pas encore : c'est une
proposition greenfield, jamais la description d'un système existant ni un constat sur une entreprise.

Règles de la proposition :
- Le résumé dit clairement qu'il s'agit d'une proposition à valider, et non d'un fait établi.
- N'utilise ni registre d'entreprises, ni jumeau, ni connaissance existante : tu n'en disposes pas.
- N'invente aucune preuve, aucun identifiant d'entreprise, aucune citation et aucun chiffre présenté comme vérifié.
- Rends explicites tes hypothèses (hypotheses) et ce que tu laisses hors périmètre (hors_scope).
- Propose des composants (composants) avec un id stable, un nom lisible et un rôle, puis des liens (liens)
  entre ces ids avec un libellé. Reste dans les bornes : 12 composants et 20 liens au plus.
- Intègre la sécurité et la vie privée dès la conception : authentification, autorisation, chiffrement,
  minimisation des données, journalisation et conformité.
- Sois concret, cohérent et concis.
"""

CONSIGNE = """Question : {question}

Intention : {intention}

Conçois une architecture cible pour cette application inexistante. Le résumé doit rappeler qu'il s'agit d'une
proposition fondée sur des hypothèses explicites, sans preuve d'entreprise et sans mobilisation de jumeaux."""


def _texte(valeur, maximum=MAX_TEXTE):
    return " ".join(str(valeur or "").split())[:maximum].strip()


def _identifiant(valeur):
    """Identifiant sûr et stable : ASCII, lettres/chiffres/underscore, jamais vide, préfixé s'il commence par un chiffre."""
    brut = unicodedata.normalize("NFKD", str(valeur or "").strip()).encode("ascii", "ignore").decode("ascii")
    ident = re.sub(r"[^A-Za-z0-9_]+", "_", brut).strip("_")[:40]
    if not ident:
        return ""
    return ident if ident[0].isalpha() else f"b_{ident}"[:40]


def _champ(objet, nom):
    return objet.get(nom) if isinstance(objet, dict) else getattr(objet, nom, None)


def _architecture(valeur):
    if isinstance(valeur, ArchitectureCible):
        return valeur
    if valeur is None:
        return ArchitectureCible(titre="", resume="")
    if isinstance(valeur, str):
        texte = _texte(valeur)
        return ArchitectureCible(titre=texte, resume=texte)
    if isinstance(valeur, dict):
        return ArchitectureCible.model_validate({"titre": "", "resume": "", **valeur})
    return ArchitectureCible.model_validate(valeur)


def _fusionner(principal, secondaire):
    def joindre(a, b):
        return [*a, *b]
    return ArchitectureCible(
        titre=principal.titre or secondaire.titre,
        resume=principal.resume or secondaire.resume,
        hypotheses=joindre(principal.hypotheses, secondaire.hypotheses),
        composants=joindre(principal.composants, secondaire.composants),
        liens=joindre(principal.liens, secondaire.liens),
        hors_scope=joindre(principal.hors_scope, secondaire.hors_scope),
    )


def _textes(valeurs, limite):
    sortie, vus = [], set()
    for valeur in valeurs or []:
        texte = _texte(valeur)
        if texte and texte.casefold() not in vus:
            vus.add(texte.casefold())
            sortie.append(texte)
        if len(sortie) >= limite:
            break
    return sortie


def _boites(composants):
    """Boîtes propres (ids normalisés, doublons écartés, 12 au plus) et alias id/nom → id retenu."""
    boites, alias, vus = [], {}, set()
    for composant in composants or []:
        nom = _texte(_champ(composant, "nom"), MAX_LIBELLE)
        ident = _identifiant(_champ(composant, "id")) or _identifiant(nom)
        if not ident or ident in vus:
            continue
        vus.add(ident)
        boites.append({"id": ident, "libelle": nom or _texte(_champ(composant, "id"), MAX_LIBELLE) or ident})
        for cle in (ident, _identifiant(_champ(composant, "id")), _identifiant(nom)):
            if cle:
                alias.setdefault(cle, ident)
                alias.setdefault(cle.casefold(), ident)
        if len(boites) >= MAX_BOITES:
            break
    return boites, alias


def _fleches(liens, alias, ids):
    """Liens dont les deux extrémités existent, dédupliqués et bornés ; tous sont des propositions."""
    fleches, vus = [], set()
    def resoudre(valeur):
        brut = _identifiant(valeur)
        if not brut:
            return None
        return alias.get(brut) or alias.get(brut.casefold())

    for lien in liens or []:
        de = resoudre(_champ(lien, "de"))
        vers = resoudre(_champ(lien, "vers"))
        if not de or not vers or de not in ids or vers not in ids:
            continue
        libelle = _texte(_champ(lien, "libelle"), MAX_LIBELLE)
        cle = (de, vers, libelle.casefold())
        if cle in vus:
            continue
        vus.add(cle)
        fleches.append({"de": de, "vers": vers, "libelle": libelle, "etat": "propose"})
        if len(fleches) >= MAX_LIENS:
            break
    return fleches


def construire_schema(plan, cible=None):
    """Schéma d'architecture pour l'interface, strictement propositionnel.

    `plan` est une ArchitectureCible (ou un dict/texte équivalent) ; `cible` peut nommer le titre, ou fournir
    une ArchitectureCible complémentaire. Les ids sont normalisés et dédupliqués, les liens orphelins ignorés,
    et le schéma ne porte aucun champ de preuve.
    """
    architecture = _architecture(plan)
    if cible is not None:
        if isinstance(cible, str):
            if nom := _texte(cible, 160):
                architecture = architecture.model_copy(update={"titre": nom})
        else:
            architecture = _fusionner(architecture, _architecture(cible))
    titre = _texte(architecture.titre, 160) or "Architecture cible"
    boites, alias = _boites(architecture.composants)
    ids = {boite["id"] for boite in boites}
    return {
        "type": "architecture",
        "mode": "proposition",
        "titre": titre,
        "boites": boites,
        "fleches": _fleches(architecture.liens, alias, ids),
        "groupes": [],
        "hypotheses": _textes(architecture.hypotheses, MAX_HYPOTHESES),
        "hors_scope": _textes(architecture.hors_scope, MAX_HORS_SCOPE),
    }


def texte_proposition(architecture):
    """Texte lisible : la proposition, son résumé, ses hypothèses et son hors-périmètre."""
    titre = _texte(architecture.titre, 160) or "Architecture cible"
    lignes = [f"**{titre} — proposition d'architecture**",
              "Voici une proposition d'architecture cible, à valider par l'équipe. Elle ne s'appuie sur aucune "
              "preuve d'entreprise et ne mobilise aucun jumeau."]
    if resume := _texte(architecture.resume, 2000):
        lignes += ["", resume]
    if hypotheses := _textes(architecture.hypotheses, MAX_HYPOTHESES):
        lignes += ["", "**Hypothèses**"] + [f"- {hypothese}" for hypothese in hypotheses]
    if hors_scope := _textes(architecture.hors_scope, MAX_HORS_SCOPE):
        lignes += ["", "**Hors périmètre**"] + [f"- {element}" for element in hors_scope]
    return "\n".join(lignes)


def _modele_configure(modele):
    if modele is not None:
        return modele
    try:
        return agent.modele()
    except Exception:
        journal.warning("conception : modèle indisponible", exc_info=True)
        return None


def _usage(a, modele):
    usage = mesure.usage(a)
    usage["cout"] = mesure.cout(usage)
    try:
        usage["modele"] = modele.get_config().get("model_id", "inconnu")
    except Exception:
        usage["modele"] = getattr(modele, "model_id", None) or "inconnu"
    return usage


async def repondre(question, intention, modele=None):
    """Répond à une demande de conception greenfield ; None si aucun modèle n'est disponible ou si le modèle échoue.

    La réponse est une proposition : aucun jumeau, aucune preuve, aucune connaissance existante. Une panne est
    silencieuse côté réponse (le serveur décide du repli) et ne diffuse jamais son message.
    """
    configure = _modele_configure(modele)
    if configure is None:
        return None
    chrono = mesure.Chrono()
    try:
        a = Agent(model=configure, system_prompt=PROMPT_SYSTEME, tools=[], callback_handler=None)
        consigne = CONSIGNE.format(question=question, intention=intention or "concevoir")
        with chrono.phase("agent"):
            resultat = await a.invoke_async(consigne, structured_output_model=ArchitectureCible)
        chrono.agent(a)
        sortie = getattr(resultat, "structured_output", None)
        if sortie is None:
            raise ValueError("sortie structurée absente")
        architecture = _architecture(sortie)
        return {
            "comportement": "concevoir",
            "proposition": True,
            "reponse": texte_proposition(architecture),
            "schemas": [construire_schema(architecture)],
            "preuves": [],
            "contributions": [],
            "jumeaux_participants": [],
            "durees": chrono.bilan(),
            "usage": _usage(a, configure),
        }
    except Exception:
        journal.warning("conception greenfield impossible", exc_info=True)
        return None
