"""Flore mobilisant le jumeau d'une application (Strands) : Claims du jumeau et code de l'application comme outils.

L'usager parle toujours à Flore, la voix de Méridian ; le jumeau est une capacité qu'elle mobilise
(Flore_Conversational_Architecture §1, §209), jamais un interlocuteur qui parle en son nom.

Le modèle est configurable (JUMEAU_MODELE=deepseek|bedrock) : le code de l'agent ne change pas entre les deux.
Aucun outil ne valide : le jumeau propose, l'équipe valide (Architecture Jumeau §4.3, §4.4).
"""
import logging
from datetime import date
import os
import subprocess
import threading
from pathlib import Path

import psycopg
from strands import Agent, tool
from strands.session.file_session_manager import FileSessionManager
from strands.session.s3_session_manager import S3SessionManager

from jumeau import cbm, connaissance, methodes, temps

SESSIONS = Path(os.environ.get("JUMEAU_SESSIONS", Path.home() / ".local/share/meridian/sessions"))
MAX_SORTIE = 6000  # caractères renvoyés au modèle par outil
MAX_ARGUMENT = 200
EPUISE = "Budget d'outils de cette réponse épuisé : réponds avec ce que tu sais déjà."
journal = logging.getLogger("meridian.jumeau")


class Budget:
    """Plafonds par réponse : bornent le coût et l'effet d'une injection qui relancerait les outils en boucle.

    L'écriture dans le Travail a son propre budget : une longue exploration ne doit jamais empêcher Flore
    de consigner son plan et ce qu'elle a trouvé.
    """

    def __init__(self, outils=25, propositions=3, ecritures=12):
        self.outils, self.propositions, self.ecritures = outils, propositions, ecritures

    def outil(self):
        self.outils -= 1
        return self.outils >= 0

    def proposition(self):
        self.propositions -= 1
        return self.propositions >= 0

    def ecriture(self):
        self.ecritures -= 1
        return self.ecritures >= 0


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
    if not valeur or len(valeur) > MAX_ARGUMENT:
        raise ValueError(f"argument refusé : {valeur[:40]!r}")
    return valeur

CHARTE = Path(__file__).with_name("charte_flore.md")  # comment Flore s'exprime ; éditable par l'équipe produit

CONTEXTE = """## Contexte de cette conversation

- Date du jour : {aujourdhui}
- Interlocuteur : {interlocuteur}
- Application : {nom}, de l'équipe {equipe}
- Code : {depots}{consigne_depots}
- Connaissances du jumeau (extraites du code ; ✓ = confirmé par l'équipe) :
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
    texte = sortie.replace(f"{projet}.", "").replace(f"{copie}/", "") if projet else sortie
    return texte if len(texte) <= MAX_SORTIE else texte[:MAX_SORTIE] + "\n… (sortie tronquée)"


def prompt_systeme(ctx):
    """Identité + charte (fichier versionné) + contexte de la conversation (interlocuteur, application, connaissances)."""
    profil = ctx.get("profil") or {}
    interlocuteur = f"{profil.get('nom', ctx['acteur'])} — rôle : {profil.get('role', 'non précisé')}"
    sources = ctx["sources"]
    depots = ", ".join(f"dépôt {s['nom']} (branche {s.get('branche') or 'inconnue'}, commit {s['curseur'][:12]})"
                       for s in sources)
    consigne = ("\n- Plusieurs dépôts : cite chaque preuve avec son dépôt, `dépôt:chemin#Ldébut-Lfin`, et précise le "
                "dépôt (paramètre depot) quand tu lis du code." if len(sources) > 1 else "")
    contexte = CONTEXTE.format(aujourdhui=date.today().isoformat(), interlocuteur=interlocuteur,
                               nom=ctx["jumeau"]["nom"], equipe=ctx["jumeau"]["equipe"], depots=depots,
                               consigne_depots=consigne,
                               autoportrait=connaissance.autoportrait(ctx["jumeau"], ctx["claims"]))
    catalogue = "\n".join(f"- {m['nom']} : {m['description']}" for m in methodes.catalogue())
    prompt = (f"Tu es Flore, la voix de Méridian.\n\n{CHARTE.read_text(encoding='utf-8')}\n\n"
              f"## Catalogue des méthodes\n\n{catalogue}\n\n{contexte}")
    if ctx.get("fiche"):
        prompt += f"\n\n## Fiche vivante de l'application (rédigée par le gardien du jumeau)\n\n{ctx['fiche']}"
    if ctx.get("travail"):
        prompt += f"\n\n## État du Travail (ton état de tâche : tiens-le à jour avec tes outils)\n\n{ctx['travail']}"
    return prompt


def outils(ctx, dsn, nom_modele, budget):
    jumeau, sources = ctx["jumeau"], ctx["sources"]

    def choisir(depot):
        if not depot:
            return sources
        choisies = [s for s in sources if s["nom"] == depot]
        if not choisies:
            raise ValueError(f"dépôt inconnu : {depot} (connus : {', '.join(s['nom'] for s in sources)})")
        return choisies

    def cbm_outil(nom, depot="", **arguments):
        """Une action de code sur un dépôt, ou sur tous (résultats regroupés par dépôt)."""
        if not budget.outil():
            return EPUISE
        try:
            choisies = choisir(depot)
        except ValueError as e:
            return str(e)
        parties = []
        for s in choisies:
            try:
                sortie = nettoyer(cbm.appeler(nom, project=s["index_code"], **arguments), s["index_code"], s["copie"])
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                journal.exception("outil %s (%s)", nom, s["nom"])
                sortie = "Outil indisponible pour ce dépôt."
            parties.append(sortie if len(sources) == 1 else f"### dépôt {s['nom']}\n{sortie}")
        return nettoyer("\n\n".join(parties), "", "")

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
    def architecture(depot: str = "") -> str:
        """Vue d'ensemble du code de l'application : langages, paquets, points d'entrée, routes.

        Args:
            depot: nom d'un dépôt de l'application ; vide = tous.
        """
        return cbm_outil("get_architecture", depot)

    @tool
    def chercher_texte(texte: str, depot: str = "") -> str:
        """Recherche un texte exact dans les fichiers de l'application (identifiant, chaîne, mot) ; renvoie fonctions, fichiers et lignes.

        Args:
            texte: le texte à chercher, par exemple un nom de variable, un message, une route.
            depot: nom d'un dépôt de l'application ; vide = tous.
        """
        try:
            return cbm_outil("search_code", depot, pattern=valeur_sure(texte), limit=10)
        except ValueError as e:
            return str(e)

    @tool
    def chercher_symbole(nom: str, depot: str = "") -> str:
        """Trouve les fonctions, classes ou routes dont le nom contient `nom` ; renvoie fichier et lignes.

        Args:
            nom: fragment de nom de symbole (lettres, chiffres, _).
            depot: nom d'un dépôt de l'application ; vide = tous.
        """
        fragment = "".join(c for c in nom if c.isalnum() or c == "_")[:MAX_ARGUMENT]
        return cbm_outil("search_graph", depot, name_pattern=f".*{fragment}.*", limit=15) if fragment else "Nom vide."

    @tool
    def tracer_appels(fonction: str, sens: str = "both", depot: str = "") -> str:
        """Qui appelle une fonction et ce qu'elle appelle.

        Args:
            fonction: nom de la fonction.
            sens: inbound (appelants), outbound (appelés) ou both.
            depot: nom d'un dépôt de l'application ; vide = tous.
        """
        sens = sens if sens in ("inbound", "outbound", "both") else "both"
        try:
            return cbm_outil("trace_path", depot, function_name=valeur_sure(fonction), direction=sens, depth=2)
        except ValueError as e:
            return str(e)

    @tool
    def lire_code(chemin: str, debut: int, fin: int, depot: str = "") -> dict:
        """Lit des lignes du code de l'application au commit ingéré ; renvoie le locator git:// à citer comme preuve.

        Args:
            chemin: chemin relatif du fichier dans son dépôt, par exemple backend/server.py.
            debut: première ligne (1 = début du fichier).
            fin: dernière ligne (au plus 200 lignes lues).
            depot: nom du dépôt ; vide si l'application n'en a qu'un ou si un seul dépôt contient ce fichier.
        """
        if not budget.outil():
            return {"erreur": EPUISE}
        try:
            return connaissance.lire_code(connaissance.resoudre_source(sources, depot, chemin), chemin, debut, fin)
        except (LookupError, ValueError) as e:
            return {"erreur": str(e)}

    @tool
    def proposer_connaissance(predicat: str, objet: str, type_claim: str, chemin: str, debut: int, fin: int,
                              justification: str, depot: str = "") -> str:
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
            depot: dépôt de la preuve ; vide si l'application n'en a qu'un.
        """
        if not budget.outil() or not budget.proposition():
            return "Plafond de propositions de cette réponse atteint."
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                source = connaissance.resoudre_source(sources, depot, chemin)
                cid = connaissance.proposer(conn, jumeau, source, predicat, objet, type_claim, chemin, debut, fin,
                                            justification, ctx["acteur"], nom_modele)
            ctx.setdefault("proposees", []).append(cid)
            return f"Proposition enregistrée (claim {cid}), en attente de revue par l'équipe."
        except (ValueError, LookupError) as e:
            return f"Proposition refusée : {e}"
        except psycopg.Error:
            journal.exception("proposer_connaissance")
            return "Proposition impossible pour le moment."

    @tool
    def historique_du_code(depuis: str = "", chemin: str = "", depot: str = "") -> list:
        """Historique des changements du code jusqu'au commit ingéré : date, auteur, message (le pourquoi), dépôt.

        Args:
            depuis: date AAAA-MM-JJ ; vide = les plus récents.
            chemin: fichier ou dossier pour ne voir que ses changements ; vide = tout.
            depot: nom d'un dépôt de l'application ; vide = tous.
        """
        if not budget.outil():
            return [EPUISE]
        try:
            return historique_fusionne(choisir(depot), depuis, chemin)
        except ValueError as e:
            return [f"Historique indisponible : {e}"]

    @tool
    def ce_qui_a_change(depuis: str) -> dict:
        """Ce qui a changé dans l'application depuis une date : commits et connaissances apparues ou disparues.

        Args:
            depuis: date AAAA-MM-JJ.
        """
        if not budget.outil():
            return {"erreur": EPUISE}
        try:
            with psycopg.connect(dsn) as conn:
                evolution = temps.evolution(conn, jumeau["id"], depuis)
            return {"commits": historique_fusionne(sources, depuis), **evolution}
        except (ValueError, psycopg.Error) as e:
            journal.warning("ce_qui_a_change : %s", e)
            return {"erreur": "date attendue au format AAAA-MM-JJ" if isinstance(e, ValueError) else "indisponible"}

    @tool
    def consulter_methode(nom: str) -> str:
        """Charge les consignes d'une méthode du catalogue, à suivre pour répondre.

        Args:
            nom: nom exact d'une méthode du catalogue, par exemple presenter-application.
        """
        return methodes.lire(nom) or f"Méthode inconnue. Disponibles : {', '.join(m['nom'] for m in methodes.catalogue())}"

    return [mes_connaissances, architecture, chercher_texte, chercher_symbole, tracer_appels, lire_code,
            proposer_connaissance, consulter_methode, historique_du_code, ce_qui_a_change]


def historique_fusionne(sources, depuis="", chemin=""):
    """Historique de plusieurs dépôts, du plus récent au plus ancien, chaque commit avec son dépôt."""
    commits = [{**c, "depot": s["nom"]} for s in sources for c in temps.historique(s, depuis, chemin)]
    return sorted(commits, key=lambda c: c["date"], reverse=True)[:temps.MAX_COMMITS]


def outils_travail(ecriture, budget):
    """Outils d'écriture dans le Travail : Flore y tient son plan et y dépose ce qu'elle produit.

    Aucun outil ne décide : les décisions restent aux humains (Vision §16, « humain dans la décision »).
    """
    async def ecrire(action, *args):
        if not budget.ecriture():
            return "Plafond d'écritures dans le Travail atteint pour cette réponse."
        try:
            await action(*args)
            return "Enregistré dans le Travail."
        except ValueError as e:
            return f"Refusé : {e}"

    @tool
    async def planifier(etapes: list[str], prochaine_etape: str = "") -> str:
        """Pose ou complète le plan du Travail : les questions à lever, dans l'ordre, et la prochaine étape.

        Args:
            etapes: questions à lever pour répondre à la demande (les étapes déjà présentes sont conservées).
            prochaine_etape: ce que tu fais ensuite, en une phrase.
        """
        return await ecrire(ecriture.planifier, etapes, prochaine_etape)

    @tool
    async def lever_etape(etape: str) -> str:
        """Marque une étape du plan comme levée, quand tu as la réponse prouvée.

        Args:
            etape: texte exact de l'étape, tel qu'il figure dans le plan.
        """
        if not budget.ecriture():
            return "Plafond d'écritures dans le Travail atteint pour cette réponse."
        return "Étape levée." if await ecriture.resoudre(etape) else "Étape introuvable : recopie son texte exact."

    @tool
    async def proposer_hypothese(texte: str) -> str:
        """Ajoute au Travail une hypothèse à valider par l'équipe.

        Args:
            texte: l'hypothèse, en une phrase.
        """
        return await ecrire(ecriture.hypothese, texte)

    @tool
    async def proposer_option(titre: str, description: str, risque: str = "moyen") -> str:
        """Ajoute au Travail une option à évaluer par l'équipe.

        Args:
            titre: nom court de l'option.
            description: ce qu'elle implique, ses effets.
            risque: faible, moyen ou eleve.
        """
        return await ecrire(ecriture.option, titre, description, risque)

    @tool
    async def deposer_livrable(titre: str, contenu: str) -> str:
        """Dépose dans le Travail un document produit (fiche d'impact, note d'arbitrage, synthèse…), en Markdown.

        Args:
            titre: titre du document.
            contenu: le document, avec ses citations `chemin#Ldébut-Lfin`.
        """
        return await ecrire(ecriture.livrable, titre, contenu)

    @tool
    async def actualiser_resume(texte: str) -> str:
        """Remplace le résumé du Travail : où en est la compréhension, en deux ou trois phrases.

        Args:
            texte: le nouveau résumé.
        """
        return await ecrire(ecriture.resume, texte)

    return [planifier, lever_etape, proposer_hypothese, proposer_option, deposer_livrable, actualiser_resume]


def gestionnaire_session(session):
    """Fil de Flore : S3 si JUMEAU_SESSIONS_S3 (« compartiment/prefixe ») est défini, sinon fichiers locaux."""
    cible = os.environ.get("JUMEAU_SESSIONS_S3")
    if cible:
        bucket, _, prefix = cible.partition("/")
        return S3SessionManager(session_id=session, bucket=bucket, prefix=prefix,
                                region_name=os.environ.get("AWS_REGION", "ca-central-1"))
    SESSIONS.mkdir(parents=True, exist_ok=True)
    return FileSessionManager(session_id=session, storage_dir=str(SESSIONS))


def construire(ctx, dsn, session, modele=None, ecriture=None, budget=None):
    """Agent du jumeau ; le fil `session` (personnel ou celui d'un Travail) est restauré depuis le disque."""
    m = modele or globals()["modele"]()
    nom_modele = m.get_config().get("model_id", "inconnu")
    SESSIONS.mkdir(parents=True, exist_ok=True)
    budget = budget or Budget()
    tools = outils(ctx, dsn, nom_modele, budget) + (outils_travail(ecriture, budget) if ecriture else [])
    return Agent(model=m, system_prompt=prompt_systeme(ctx), tools=tools,
                 session_manager=gestionnaire_session(session),
                 callback_handler=None)
