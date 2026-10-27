"""Flore mobilisant le jumeau d'une application (Strands) : Claims du jumeau et code de l'application comme outils.

L'usager parle toujours à Flore, la voix de Méridian ; le jumeau est une capacité qu'elle mobilise
(Flore_Conversational_Architecture §1, §209), jamais un interlocuteur qui parle en son nom.

Le modèle est configurable (JUMEAU_MODELE=deepseek|bedrock) : le code de l'agent ne change pas entre les deux.
Aucun outil ne valide : le jumeau propose, l'équipe valide (Architecture Jumeau §4.3, §4.4).
"""
import logging
import os
import subprocess
import threading
from pathlib import Path

import psycopg
from strands import Agent, tool
from strands.session.file_session_manager import FileSessionManager

from jumeau import cbm, connaissance, methodes

SESSIONS = Path(os.environ.get("JUMEAU_SESSIONS", Path.home() / ".local/share/meridian/sessions"))
MAX_SORTIE = 6000  # caractères renvoyés au modèle par outil
MAX_ARGUMENT = 200
EPUISE = "Budget d'outils de cette réponse épuisé : réponds avec ce que tu sais déjà."
journal = logging.getLogger("meridian.jumeau")


class Budget:
    """Plafonds par réponse : bornent le coût et l'effet d'une injection qui relancerait les outils en boucle."""

    def __init__(self, outils=15, propositions=3):
        self.outils, self.propositions = outils, propositions

    def outil(self):
        self.outils -= 1
        return self.outils >= 0

    def proposition(self):
        self.propositions -= 1
        return self.propositions >= 0


class FilsActifs:
    """Un seul flux à la fois par fil (jumeau, membre) : deux écritures concurrentes corrompraient la session.

    ponytail: verrou en mémoire d'un seul processus ; verrou partagé (Postgres advisory) si plusieurs workers.
    """

    def __init__(self):
        self._actifs, self._verrou = set(), threading.Lock()

    def prendre(self, jumeau_id, acteur):
        with self._verrou:
            if (jumeau_id, acteur) in self._actifs:
                return False
            self._actifs.add((jumeau_id, acteur))
            return True

    def rendre(self, jumeau_id, acteur):
        with self._verrou:
            self._actifs.discard((jumeau_id, acteur))


def valeur_sure(valeur):
    """Argument passé au CLI cbm : jamais une option (« -… »), longueur bornée."""
    valeur = valeur.strip()
    if not valeur or valeur.startswith("-") or len(valeur) > MAX_ARGUMENT:
        raise ValueError(f"argument refusé : {valeur[:40]!r}")
    return valeur

CHARTE = Path(__file__).with_name("charte_flore.md")  # comment Flore s'exprime ; éditable par l'équipe produit

CONTEXTE = """## Contexte de cette conversation

- Interlocuteur : {interlocuteur}
- Application : {nom}, de l'équipe {equipe}
- Connaissances du jumeau (extraites du code au commit {sha} ; ✓ = confirmé par l'équipe) :
{autoportrait}"""


def modele():
    fournisseur = os.environ.get("JUMEAU_MODELE", "deepseek")
    if fournisseur == "deepseek":
        # ponytail: API hébergée hors Canada — réservée au code non bancaire (Architecture Jumeau §10).
        cle = os.environ.get("DEEPSEEK_API_KEY")
        if not cle:
            raise RuntimeError("Modèle non configuré : clé DeepSeek absente")
        from strands.models.openai import OpenAIModel
        return OpenAIModel(client_args={"api_key": cle, "base_url": "https://api.deepseek.com"},
                           model_id=os.environ.get("DEEPSEEK_MODELE", "deepseek-chat"))
    if fournisseur == "bedrock":
        from strands.models import BedrockModel
        if not os.environ.get("BEDROCK_MODELE"):
            raise RuntimeError("Modèle non configuré : BEDROCK_MODELE absent")
        return BedrockModel(model_id=os.environ["BEDROCK_MODELE"], region_name=os.environ.get("AWS_REGION", "ca-central-1"))
    raise RuntimeError(f"JUMEAU_MODELE inconnu : {fournisseur}")


def nettoyer(sortie, projet, copie):
    """Sortie d'outil lisible et bornée : sans préfixe de projet cbm ni chemin local de la copie."""
    texte = sortie.replace(f"{projet}.", "").replace(f"{copie}/", "")
    return texte if len(texte) <= MAX_SORTIE else texte[:MAX_SORTIE] + "\n… (sortie tronquée)"


def prompt_systeme(ctx):
    """Identité + charte (fichier versionné) + contexte de la conversation (interlocuteur, application, connaissances)."""
    profil = ctx.get("profil") or {}
    interlocuteur = f"{profil.get('nom', ctx['acteur'])} — rôle : {profil.get('role', 'non précisé')}"
    contexte = CONTEXTE.format(interlocuteur=interlocuteur, nom=ctx["jumeau"]["nom"], equipe=ctx["jumeau"]["equipe"],
                               sha=ctx["source"]["curseur"][:12],
                               autoportrait=connaissance.autoportrait(ctx["jumeau"], ctx["claims"]))
    catalogue = "\n".join(f"- {m['nom']} : {m['description']}" for m in methodes.catalogue())
    return (f"Tu es Flore, la voix de Méridian.\n\n{CHARTE.read_text(encoding='utf-8')}\n\n"
            f"## Catalogue des méthodes\n\n{catalogue}\n\n{contexte}")


def outils(ctx, dsn, nom_modele, budget):
    jumeau, source = ctx["jumeau"], ctx["source"]
    projet, copie = source["index_code"], source["copie"]

    def cbm_outil(nom, *args):
        if not budget.outil():
            return EPUISE
        try:
            return nettoyer(cbm.texte(nom, "--project", projet, *args), projet, copie)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired):
            journal.exception("outil %s", nom)
            return "Outil indisponible pour cette demande."

    @tool
    def mes_connaissances(famille: str = "", recherche: str = "") -> list:
        """Liste les Claims du jumeau (connaissances prouvées sur l'application) avec statut, maturité et preuve.

        Args:
            famille: EXPOSE, DEPEND_DE, LIT_VARIABLE, EXECUTE_IMAGE ou un autre prédicat ; vide = toutes.
            recherche: texte contenu dans l'objet du Claim ; vide = tous.
        """
        if not budget.outil():
            return [EPUISE]
        try:
            with psycopg.connect(dsn) as conn:
                return connaissance.connaissances(conn, jumeau["id"], famille or None, recherche or None)
        except psycopg.Error:
            journal.exception("mes_connaissances")
            return ["Connaissances indisponibles."]

    @tool
    def architecture() -> str:
        """Vue d'ensemble du code de l'application : langages, paquets, points d'entrée, routes."""
        return cbm_outil("get_architecture")

    @tool
    def chercher_texte(texte: str) -> str:
        """Recherche un texte exact dans les fichiers de l'application (identifiant, chaîne, mot) ; renvoie fonctions, fichiers et lignes.

        Args:
            texte: le texte à chercher, par exemple un nom de variable, un message, une route.
        """
        try:
            return cbm_outil("search_code", "--pattern", valeur_sure(texte), "--limit", "10")
        except ValueError as e:
            return str(e)

    @tool
    def chercher_symbole(nom: str) -> str:
        """Trouve les fonctions, classes ou routes dont le nom contient `nom` ; renvoie fichier et lignes.

        Args:
            nom: fragment de nom de symbole (lettres, chiffres, _).
        """
        fragment = "".join(c for c in nom if c.isalnum() or c == "_")[:MAX_ARGUMENT]
        return cbm_outil("search_graph", "--name-pattern", f".*{fragment}.*", "--limit", "15") if fragment else "Nom vide."

    @tool
    def tracer_appels(fonction: str, sens: str = "both") -> str:
        """Qui appelle une fonction et ce qu'elle appelle.

        Args:
            fonction: nom de la fonction.
            sens: inbound (appelants), outbound (appelés) ou both.
        """
        sens = sens if sens in ("inbound", "outbound", "both") else "both"
        try:
            return cbm_outil("trace_path", "--function-name", valeur_sure(fonction), "--direction", sens, "--depth", "2")
        except ValueError as e:
            return str(e)

    @tool
    def lire_code(chemin: str, debut: int, fin: int) -> dict:
        """Lit des lignes du code de l'application au commit ingéré ; renvoie le locator git:// à citer comme preuve.

        Args:
            chemin: chemin relatif du fichier, par exemple backend/server.py.
            debut: première ligne (1 = début du fichier).
            fin: dernière ligne (au plus 200 lignes lues).
        """
        if not budget.outil():
            return {"erreur": EPUISE}
        try:
            return connaissance.lire_code(source, chemin, debut, fin)
        except (LookupError, ValueError) as e:
            return {"erreur": str(e)}

    @tool
    def proposer_connaissance(predicat: str, objet: str, type_claim: str, chemin: str, debut: int, fin: int,
                              justification: str) -> str:
        """Propose au jumeau une nouvelle connaissance sur l'application, prouvée par des lignes de code.

        Elle reste PROPOSED jusqu'à la revue humaine. N'utilise que des lignes lues avec lire_code.

        Args:
            predicat: verbe en MAJUSCULES, par exemple APPLIQUE_REGLE, STOCKE, AUTORISE.
            objet: ce que fait l'application, en une phrase courte.
            type_claim: BUSINESS_RULE, CAPABILITY, DATA_FLOW, BEHAVIOR, FUNCTIONALITY, RISK, DEPENDENCY, API_USAGE…
            chemin: fichier de la preuve.
            debut: première ligne de la preuve.
            fin: dernière ligne de la preuve.
            justification: pourquoi ces lignes prouvent la connaissance.
        """
        if not budget.outil() or not budget.proposition():
            return "Plafond de propositions de cette réponse atteint."
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                cid = connaissance.proposer(conn, jumeau, source, predicat, objet, type_claim, chemin, debut, fin,
                                            justification, ctx["acteur"], nom_modele)
            return f"Proposition enregistrée (claim {cid}), en attente de revue par l'équipe."
        except ValueError as e:
            return f"Proposition refusée : {e}"
        except psycopg.Error:
            journal.exception("proposer_connaissance")
            return "Proposition impossible pour le moment."

    @tool
    def consulter_methode(nom: str) -> str:
        """Charge les consignes d'une méthode du catalogue, à suivre pour répondre.

        Args:
            nom: nom exact d'une méthode du catalogue, par exemple presenter-application.
        """
        return methodes.lire(nom) or f"Méthode inconnue. Disponibles : {', '.join(m['nom'] for m in methodes.catalogue())}"

    return [mes_connaissances, architecture, chercher_texte, chercher_symbole, tracer_appels, lire_code,
            proposer_connaissance, consulter_methode]


def construire(ctx, dsn, session, modele=None):
    """Agent du jumeau ; le fil `session` (personnel ou celui d'un Travail) est restauré depuis le disque."""
    m = modele or globals()["modele"]()
    nom_modele = m.get_config().get("model_id", "inconnu")
    SESSIONS.mkdir(parents=True, exist_ok=True)
    return Agent(model=m, system_prompt=prompt_systeme(ctx), tools=outils(ctx, dsn, nom_modele, Budget()),
                 session_manager=FileSessionManager(session_id=session, storage_dir=str(SESSIONS)),
                 callback_handler=None)
