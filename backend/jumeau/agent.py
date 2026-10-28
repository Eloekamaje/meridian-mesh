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
from strands.agent.conversation_manager import SummarizingConversationManager
from strands.session.file_session_manager import FileSessionManager
from strands.session.s3_session_manager import S3SessionManager

from jumeau import appels, cbm, connaissance, croisement, depot, methodes, temps
from jumeau.connaissance import ancrer as ancrer_code
from jumeau.connaissance import recouper as recouper_code
from jumeau.lecteurs import NATURES, RE_CITATION_SOURCE

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
- Ce que le jumeau sait de lui-même (la fiche vivante ci-dessus fait référence) :
{autoportrait}"""


def modele(nom=None, temperature=None):
    fournisseur = os.environ.get("JUMEAU_MODELE", "deepseek")
    if fournisseur == "deepseek":
        # ponytail: API hébergée hors Canada — réservée au code non bancaire (Architecture Jumeau §10).
        cle = os.environ.get("DEEPSEEK_API_KEY")
        if not cle:
            raise RuntimeError("Modèle non configuré : clé DeepSeek absente")
        from strands.models.openai import OpenAIModel
        return OpenAIModel(client_args={"api_key": cle, "base_url": "https://api.deepseek.com"},
                           model_id=nom or os.environ.get("DEEPSEEK_MODELE", "deepseek-chat"),
                           **({} if temperature is None else {"params": {"temperature": temperature}}))
    if fournisseur == "bedrock":
        from strands.models import BedrockModel
        if not os.environ.get("BEDROCK_MODELE"):
            raise RuntimeError("Modèle non configuré : BEDROCK_MODELE absent")
        return BedrockModel(model_id=nom or os.environ["BEDROCK_MODELE"],
                            region_name=os.environ.get("AWS_REGION", "ca-central-1"),
                            **({} if temperature is None else {"temperature": temperature}))
    raise RuntimeError(f"JUMEAU_MODELE inconnu : {fournisseur}")


def modele_juge():
    """Le modèle du juge d'appui. Il ne devrait pas être celui de l'auteur : un même modèle partage ses erreurs, et
    « un fil vierge » ne fait alors qu'une seconde opinion du même esprit (plan de remédiation L1.7).

    `JUMEAU_MODELE_JUGE` (par exemple un modèle d'une autre famille, ou Bedrock d'un autre fournisseur) ; à défaut,
    le modèle de l'auteur — et la dépendance reste visible ici plutôt que dissimulée."""
    return modele(os.environ.get("JUMEAU_MODELE_JUGE") or None, temperature=0)  # un verdict, pas une prose


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
    if not sources:  # progiciel : la banque n'a pas le code, la compréhension repose sur ses autres sources
        substance = depot.substance({l.systeme for l in ctx.get("lecteurs") or []}) or "aucune"
        depots = f"non accessible (progiciel, la banque n'en a pas le code). Substance : {substance}"
    consigne = ("\n- Plusieurs dépôts : cite chaque preuve avec son dépôt, `dépôt:chemin#Ldébut-Lfin`, et précise le "
                "dépôt (paramètre depot) quand tu lis du code." if len(sources) > 1 else "")
    contexte = CONTEXTE.format(aujourdhui=date.today().isoformat(), interlocuteur=interlocuteur,
                               nom=ctx["jumeau"]["nom"], equipe=ctx["jumeau"]["equipe"], depots=depots,
                               consigne_depots=consigne,
                               autoportrait=connaissance.autoportrait(ctx["jumeau"], ctx["claims"]))
    catalogue = "\n".join(f"- {m['nom']} : {m['description']}" for m in methodes.catalogue())
    # Du plus stable au plus variable : le préfixe (charte, catalogue) reste identique d'un tour à l'autre (cache).
    prompt = (f"Tu es Flore, la voix de Méridian.\n\n{CHARTE.read_text(encoding='utf-8')}\n\n"
              f"## Catalogue des méthodes\n\n{catalogue}")
    if ctx.get("consignes"):  # après le préfixe stable, avant la fiche : elles changent rarement
        prompt += ("\n\n## Consignes de l'équipe (instructions ; la plus particulière l'emporte)\n\n"
                   + "\n".join(f"- [{c['portee']}] {c['texte']} (pourquoi : {c['pourquoi']})" for c in ctx["consignes"]))
    if ctx.get("fiche"):
        prompt += f"\n\n## Fiche vivante de l'application (rédigée par le gardien du jumeau)\n\n{ctx['fiche']}"
    prompt += f"\n\n{contexte}"
    if ctx.get("lecteurs"):
        prompt += f"\n\n## Sources branchées\n\n{'En plus du code, tu' if sources else 'Tu'} disposes de ces sources (outils chercher_dans, lire_dans) :\n"
        prompt += "\n".join(f"- {l.nom} : {l.nature}, fait autorité pour {NATURES.get(l.systeme, ('', 'son domaine'))[1]}"
                            for l in ctx["lecteurs"])
    if ctx.get("travail"):
        prompt += f"\n\n## État du Travail (ton état de tâche : tiens-le à jour avec tes outils)\n\n{ctx['travail']}"
    return prompt


def outil_dessin(dessin, budget):
    """L'outil dessiner_schema, lié au schéma d'une réponse (jumeau seul ou orchestratrice)."""
    @tool
    def dessiner_schema(type: str, titre: str, boites: list[dict], fleches: list[dict],
                        groupes: list[dict] | None = None) -> str:
        """Dessine un schéma dans ta réponse. Tu choisis et tu nommes ; chaque flèche doit être fondée, sinon elle
        n'est pas dessinée (le compte rendu te dit lesquelles corriger).

        Args:
            type: sequence (« que se passe-t-il quand… »), flux ou architecture.
            titre: ce que montre le schéma, en quelques mots.
            boites: [{"id": "route", "libelle": "Publication d'un article"}], 12 au plus, libellés dans les mots du
                métier.
            fleches: [{"de": "route", "vers": "adresse", "libelle": "fabrique l'adresse depuis le titre",
                "fondement": "app/services/articles.py#L64-L64", "appel": "get_slug_for_article"}] : fondement = la
                ligne d'appel rendue par suivre_appels (avec appel = la fonction appelée), ou c:<connaissance> ou
                r:<relation> ; 20 au plus.
            groupes: [{"libelle": "Stockage", "ids": ["depot", "base"]}] pour regrouper des boîtes (facultatif).
        """
        if not budget.outil():
            return EPUISE
        return dessin.dessiner(type, titre, boites, fleches, groupes or ())

    return dessiner_schema


def outils(ctx, dsn, nom_modele, budget):
    jumeau, sources, lecteurs = ctx["jumeau"], ctx["sources"], ctx.get("lecteurs") or []

    def lecteur_nomme(nom):
        lecteur = next((l for l in lecteurs if l.nom == nom), None)
        if not lecteur:
            raise ValueError(f"source inconnue : {nom} (connues : {', '.join(l.nom for l in lecteurs)})")
        return lecteur

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
                # Un index absent n'est pas « l'outil est indisponible » : c'est une connaissance non reconstruite,
                # et l'interlocuteur doit pouvoir le dire (plan de remédiation L0bis.4).
                sortie = (f"L'index de code est inutilisable : {cbm.cause_panne()}." if cbm.cause_panne() else
                          "L'index de code de ce dépôt n'est pas disponible : ses connaissances ne sont pas "
                          "reconstruites. Il se refait à la prochaine ingestion (le gardien le reconstruit)."
                          if not cbm.indexe(s) else "Outil indisponible pour ce dépôt.")
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
    def proposer_connaissance(predicat: str, objet: str, type_claim: str, justification: str, chemin: str = "",
                              debut: int = 0, fin: int = 0, depot: str = "", citation: str = "") -> str:
        """Propose au jumeau une nouvelle connaissance sur l'application, prouvée par des lignes de code ou de source.

        Elle reste PROPOSED jusqu'à la revue humaine. N'utilise que des lignes lues avec lire_code (chemin, debut,
        fin) ou lire_dans (citation).

        Args:
            predicat: verbe en MAJUSCULES, par exemple APPLIQUE_REGLE, STOCKE, AUTORISE.
            objet: ce que fait l'application, en une phrase courte.
            type_claim: BUSINESS_RULE, CAPABILITY, DATA_FLOW, BEHAVIOR, FUNCTIONALITY, RISK, DEPENDENCY, API_USAGE…
            justification: pourquoi ces lignes prouvent la connaissance.
            chemin: fichier de la preuve de code.
            debut: première ligne de la preuve de code.
            fin: dernière ligne de la preuve de code.
            depot: dépôt de la preuve de code ; vide si l'application n'en a qu'un.
            citation: preuve d'une source branchée, le locator rendu par lire_dans (systeme://espace/ref@version#La-Lb) ; vide pour du code.
        """
        if not budget.outil() or not budget.proposition():
            return "Plafond de propositions de cette réponse atteint."
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                if citation:
                    m = RE_CITATION_SOURCE.fullmatch(citation.strip("` "))
                    lecteur = next((l for l in lecteurs if m and l.systeme == m["systeme"] and l.espace == m["espace"]), None)
                    if not lecteur:
                        raise LookupError(f"source inconnue : {citation}")
                    cid = connaissance.proposer_source(conn, jumeau, lecteur, predicat, objet, type_claim, citation,
                                                       justification, ctx["acteur"], nom_modele)
                else:
                    source = connaissance.resoudre_source(sources, depot, chemin)
                    cid = connaissance.proposer(conn, jumeau, source, predicat, objet, type_claim, chemin, debut, fin,
                                                justification, ctx["acteur"], nom_modele)
            if connaissance.prouvable(predicat):
                return f"Proposition enregistrée (claim {cid}), en attente de revue par l'équipe."
            if (predicat or "").upper() in connaissance.FORMES:
                return (f"Proposition enregistrée (claim {cid}) comme **hypothèse** pour l'instant : elle deviendra un "
                        "fait établi si la vérification constate, dans les lignes citées, une décision (règle) ou une "
                        "déclaration de donnée, et que le juge l'appuie.")
            return (f"Proposition enregistrée (claim {cid}) comme **hypothèse** : aucune ligne ne peut établir "
                    f"« {predicat} ». Elle reste en attente de l'équipe, et elle ne recevra pas de diplôme de "
                    "maturité tant que rien ne la prouve.")
        except (ValueError, LookupError) as e:
            return f"Proposition refusée : {e}"
        except psycopg.Error:
            journal.exception("proposer_connaissance")
            return "Proposition impossible pour le moment."

    @tool
    def fusionner_connaissances(garder: int, retirer: int, raison: str) -> str:
        """Fusionne deux connaissances qui disent la même chose : `retirer` disparaît, ses preuves passent à `garder`.

        Seulement deux réponses à la même question (même prédicat) ; une connaissance validée par l'équipe se garde,
        elle ne se retire jamais.

        Args:
            garder: identifiant de la connaissance à garder (la mieux formulée, ou celle validée par l'équipe).
            retirer: identifiant de la connaissance redondante.
            raison: pourquoi elles disent la même chose.
        """
        if not budget.outil() or not budget.proposition():
            return "Plafond de cette réponse atteint."
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                depot.fusionner(conn, jumeau["id"], int(garder), int(retirer))
            journal.info("fusion %s ← %s : %s", garder, retirer, raison[:200])
            return f"Connaissance {retirer} fusionnée dans {garder}."
        except ValueError as e:
            return f"Fusion refusée : {e}"
        except psycopg.Error:
            journal.exception("fusionner_connaissances")
            return "Fusion impossible pour le moment."

    @tool
    def ancrer_connaissance(connaissance: int, citation_code: str, raison: str) -> str:
        """Rattache une connaissance issue d'une source (documentation, ticket…) au code qu'elle concerne.

        Ce n'est pas une preuve : elle ne change pas la maturité. Lis d'abord les lignes avec lire_code.

        Args:
            connaissance: identifiant de la connaissance (issue d'une source autre que le code).
            citation_code: lignes de code concernées, chemin#Ldébut-Lfin (ou depot:chemin#Ldébut-Lfin).
            raison: en une phrase, en quoi la connaissance concerne ces lignes.
        """
        if not budget.outil() or not budget.proposition():
            return "Plafond de propositions de cette réponse atteint."
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                nouvelle = ancrer_code(conn, jumeau, sources, int(connaissance), citation_code, raison)
            return f"Connaissance {connaissance} ancrée à {citation_code}." if nouvelle else "Ancrage déjà enregistré."
        except (ValueError, LookupError) as e:
            return f"Ancrage refusé : {e}"
        except psycopg.Error:
            journal.exception("ancrer_connaissance")
            return "Ancrage impossible pour le moment."

    @tool
    def recouper_connaissance(connaissance: int, citation: str, raison: str) -> str:
        """Ajoute à une connaissance existante une seconde source, d'un autre système, qui l'appuie.

        Seule une source indépendante recoupe (documentation du dépôt, source branchée) : jamais une autre ligne du
        même système, jamais une recopie. Elle ne change ni le statut ni l'objet ; la vérification est rejouée seule.
        Si la seconde source contredit, utilise signaler_contradiction. Lis d'abord les lignes (lire_code, lire_dans).

        Args:
            connaissance: identifiant de la connaissance courante de ce jumeau.
            citation: chemin#Ldébut-Lfin (code ou documentation du dépôt, ou depot:chemin#…) ou le locator d'une source branchée (systeme://espace/ref@version#La-Lb).
            raison: en une phrase, en quoi ces lignes appuient la connaissance.
        """
        if not budget.outil() or not budget.proposition():
            return "Plafond de propositions de cette réponse atteint."
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                nouvelle = recouper_code(conn, jumeau, sources, lecteurs, int(connaissance), citation,
                                                        raison, ctx["acteur"], nom_modele)
            return (f"Connaissance {connaissance} recoupée par {citation}." if nouvelle
                    else "Recoupement déjà enregistré.")
        except (ValueError, LookupError) as e:
            return f"Recoupement refusé : {e}"
        except psycopg.Error:
            journal.exception("recouper_connaissance")
            return "Recoupement impossible pour le moment."

    @tool
    def signaler_contradiction(enonce: str, citation_a: str, citation_b: str) -> str:
        """Signale que deux sources de systèmes différents se contredisent (par exemple le code et la documentation).

        Les deux citations sont vérifiées ; la contradiction reste ouverte jusqu'à la décision de l'équipe.

        Args:
            enonce: ce sur quoi les deux sources divergent, en une phrase.
            citation_a: citation lue, d'un premier système.
            citation_b: citation lue, d'un autre système.
        """
        if not budget.outil() or not budget.proposition():
            return "Plafond de propositions de cette réponse atteint."
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                cid = croisement.signaler(conn, jumeau, enonce, citation_a, citation_b, sources,
                                          ctx.get("lecteurs", []), ctx["acteur"])
            return f"Contradiction {cid} signalée, en attente de décision de l'équipe."
        except ValueError as e:
            return f"Signalement refusé : {e}"
        except psycopg.Error:
            journal.exception("signaler_contradiction")
            return "Signalement impossible pour le moment."

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

    def donnee(lecteur, contenu):
        """Contenu de source rendu comme donnée : balisé, `<` `>` neutralisés (jamais une instruction)."""
        contenu = contenu.replace("<", "‹").replace(">", "›")
        return f'<donnee source="{lecteur.nom.replace(chr(34), "")}">\n{contenu}\n</donnee>'

    def appeler_source(source, action):
        if not budget.outil():
            return EPUISE
        try:
            lecteur = lecteur_nomme(source)
            return donnee(lecteur, action(lecteur))
        except (LookupError, ValueError, OSError) as e:
            journal.warning("source %s : %s", source, e)
            return f"Source indisponible : {e}"
        except Exception:  # jeton refusé, quota, coffre indisponible : message contrôlé, jamais l'erreur brute
            journal.warning("source %s indisponible", source, exc_info=True)
            return "Source indisponible pour le moment."

    @tool
    def chercher_dans(source: str, texte: str) -> str:
        """Cherche un texte dans une source branchée (pas le code) ; renvoie les références et extraits trouvés.

        Args:
            source: nom de la source, tel qu'annoncé dans « Sources branchées ».
            texte: mots à chercher.
        """
        return appeler_source(source, lambda l: "\n".join(
            f"{r['ref']} · {r['titre']} · {r['extrait']}" for r in l.chercher(texte)) or "Aucun résultat.")

    @tool
    def lire_dans(source: str, ref: str, debut: int = 1, fin: int = 200) -> str:
        """Lit des lignes d'un document d'une source branchée ; renvoie le locator à citer comme preuve.

        Args:
            source: nom de la source, tel qu'annoncé dans « Sources branchées ».
            ref: référence du document, rendue par chercher_dans.
            debut: première ligne (1 = début).
            fin: dernière ligne (au plus 200 lignes lues).
        """
        def lire(l):
            lu = l.lire(ref, debut, fin)
            premiere = int(lu["locator"].rsplit("#L", 1)[1].split("-L")[0])
            lignes = "\n".join(f"{premiere + i}: {t}" for i, t in enumerate(lu["lignes"]))
            return f"{lu['titre']} — à citer : {lu['locator']}\n{lignes}"
        return appeler_source(source, lire)

    @tool
    def suivre_appels(fonction: str, profondeur: int = 3, depot: str = "") -> str:
        """L'enchaînement d'une fonctionnalité, lu dans le code : qui appelle qui depuis une fonction (souvent le
        gestionnaire d'une route), chaque flèche avec la ligne de l'appel à donner comme fondement à dessiner_schema.

        Args:
            fonction: nom de la fonction de départ (par exemple create_new_article).
            profondeur: niveaux d'appels suivis, de 1 à 4 (3 par défaut).
            depot: nom d'un dépôt de l'application ; vide = le premier.
        """
        if not budget.outil():
            return EPUISE
        try:
            source = choisir(depot)[0]
            fleches = appels.enchainement(source, valeur_sure(fonction), cbm.appeler,
                                          max(1, min(int(profondeur), appels.PROFONDEUR_MAX)))
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
            return f"Enchaînement indisponible : {e}"
        return nettoyer(appels.texte(fleches, source["nom"] if len(sources) > 1 else None), "", "")

    dessin = ctx.get("dessin")
    dessiner_schema = outil_dessin(dessin, budget) if dessin else None

    code = [architecture, chercher_texte, chercher_symbole, tracer_appels, suivre_appels, lire_code,
            historique_du_code, ce_qui_a_change, ancrer_connaissance]  # sans dépôt (progiciel), aucun outil de code : pas d'outil cassé
    return [mes_connaissances, proposer_connaissance, fusionner_connaissances, signaler_contradiction,
            consulter_methode, *(code if sources else []), *([chercher_dans, lire_dans] if lecteurs else []),
            *([recouper_connaissance] if sources or lecteurs else []), *([dessiner_schema] if dessin else [])]


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

    @tool
    async def demander_precision(question: str, options: list[str]) -> str:
        """Pose à l'humain une question à options, quand sa réponse change le travail et que lui seul peut trancher.

        Args:
            question: la question, en une phrase.
            options: 2 à 4 réponses possibles, courtes, une ligne chacune.
        """
        retour = await ecrire(ecriture.precision, question, options)
        if retour.startswith("Enregistré"):
            return "Question posée dans le Travail. Arrête-toi : conclus ta réponse sans y répondre et attends le choix."
        return retour

    return [planifier, lever_etape, proposer_hypothese, proposer_option, deposer_livrable, actualiser_resume,
            demander_precision]


def gestionnaire_session(session):
    """Fil de Flore : S3 si JUMEAU_SESSIONS_S3 (« compartiment/prefixe ») est défini, sinon fichiers locaux."""
    cible = os.environ.get("JUMEAU_SESSIONS_S3")
    if cible:
        bucket, _, prefix = cible.partition("/")
        return S3SessionManager(session_id=session, bucket=bucket, prefix=prefix,
                                region_name=os.environ.get("AWS_REGION", "ca-central-1"))
    SESSIONS.mkdir(parents=True, exist_ok=True)
    return FileSessionManager(session_id=session, storage_dir=str(SESSIONS))


# Vérifié dans Strands : le résumé se déclenche au dépassement de contexte ou, en proactif, au seuil ci-dessous
# (ignoré si la taille du contexte est inconnue) ; il est dans l'état du gestionnaire, que la session persiste et restaure.
RATIO_RESUME = 0.4
MESSAGES_RECENTS_CONSERVES = 12
SEUIL_COMPACTION = 0.7
CONSIGNE_RESUME = """Résume le début de cet échange pour que le travail puisse continuer sans le relire. En français, sous ces rubriques :
- Demande de l'interlocuteur : ce qu'il veut obtenir, dans ses termes.
- Ce qui est établi : les faits retenus, chacun avec sa citation de preuve `chemin#Ldébut-Lfin` conservée telle quelle.
- Décisions et validations : ce qui a été tranché ou validé, et par qui.
- Ce qui reste ouvert : questions sans réponse, points à vérifier.
- Prochaine étape.
Aucun détail d'exploration (recherches, fichiers parcourus sans résultat, outils appelés) ; ne rien inventer."""


def construire(ctx, dsn, session, modele=None, ecriture=None, budget=None):
    """Agent du jumeau ; le fil `session` (personnel ou celui d'un Travail) est restauré depuis le disque.
    Sans `session`, l'agent part d'un fil vierge (passe du gardien : sa mémoire, ce sont ses connaissances)."""
    m = modele or globals()["modele"]()
    nom_modele = m.get_config().get("model_id", "inconnu")
    SESSIONS.mkdir(parents=True, exist_ok=True)
    budget = budget or Budget()
    tools = outils(ctx, dsn, nom_modele, budget) + (outils_travail(ecriture, budget) if ecriture else [])
    return Agent(model=m, system_prompt=prompt_systeme(ctx), tools=tools,
                 session_manager=gestionnaire_session(session) if session else None,
                 conversation_manager=SummarizingConversationManager(
                     summary_ratio=RATIO_RESUME, preserve_recent_messages=MESSAGES_RECENTS_CONSERVES,
                     summarization_system_prompt=CONSIGNE_RESUME,
                     proactive_compression={"compression_threshold": SEUIL_COMPACTION}) if session else None,
                 callback_handler=None)
