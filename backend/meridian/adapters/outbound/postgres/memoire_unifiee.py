"""Façade mémoire 4 couches (plan Cognition IA, D5) : Connaissance, Épisodes,
Recettes, Documents — une seule entrée, ``memoire``.

La façade ne crée aucun schéma et ne modifie aucun module : elle compose
l'existant, en lecture seule.

- **Connaissance** : claims ``ACCEPTED`` valides (``claim``) et beliefs
  (``objet_entreprise`` type ``BELIEF``), filtrés par recouvrement lexical de la
  question — :func:`retrieval_memoire.recuperer` ne lit les claims que pour des
  ``twin_ids`` explicites, la couche porte donc sa propre requête bornée.
- **Épisodes** : derniers épisodes groupés (:func:`journal_episodes.episodes`)
  et derniers événements de requête (``evenement_requete``, C8). Une requête
  portant le même ``question_hash`` marque l'événement ``meme_question`` et lève
  ``lie_question`` sur l'épisode qu'elle référence — pour ces épisodes liés, la
  trace compacte est jointe via :func:`journal_episodes.lire_episode`.
- **Recettes** : learnings canoniques et mémoire durable ``apprentissage`` via
  :func:`retrieval_memoire.recuperer` (composée, non modifiée), plus la mesure
  des signatures de besoins (:func:`signatures_besoins.taux_par_signature`).
- **Documents** : ``document_chunk``, recouvrement lexical borné (le retrieval
  hybride vecteurs/graphe reste à ``chunk_store.chercher`` — ici, lecture SQL
  déterministe sur la connexion de l'appelant).

Contrat : tout est borné, déterministe, sans LLM. Chaque couche est fail-soft :
une couche en panne ou vide rend une liste vide, est citée dans ``manques`` et
son erreur dans ``erreurs`` — les autres couches répondent. Le système sait ce
qu'il ne sait pas.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import contextlib
from datetime import date, datetime
from decimal import Decimal
import unicodedata
from typing import Any

from psycopg.rows import dict_row

from meridian.adapters.outbound.postgres import entreprise_depot
from meridian.adapters.outbound.postgres import evenements_requete
from meridian.adapters.outbound.postgres import journal_episodes
from meridian.adapters.outbound.postgres import retrieval_memoire
from meridian.adapters.outbound.postgres import signatures_besoins

__all__ = ["COUCHES", "MemoireUnifieeInvalide", "memoire"]

COUCHES = ("connaissance", "episodes", "recettes", "documents")

_LIMITE_MAX = 50            # borne dure de limite_par_couche
_LIMITE_CANDIDATS = 200     # lignes candidates lues avant filtrage lexical
_MAX_REQUETES = 40          # evenement_requete relus par question
_LIMITE_RETRIEVAL = 80      # candidats demandés à retrieval_memoire (borné à 100)
_MAX_OBJETS_EPISODE = 8     # trace compacte jointe à un épisode lié
_MAX_TOKENS = 8             # tokens de question utilisés en ILIKE
_EXTRAIT = 240              # longueur de l'extrait de chunk rendu


class MemoireUnifieeInvalide(ValueError):
    """Un paramètre de la façade est invalide."""


def _savepoint(conn: Any):
    """Savepoint bornant une couche ; repli sans savepoint si ``conn`` n'en offre pas."""
    if hasattr(conn, "transaction"):
        return conn.transaction()
    return contextlib.nullcontext()


# ---------------------------------------------------------------------------
# Normalisation déterministe (mêmes règles que retrieval_memoire, réimplémentées
# pour ne pas dépendre de ses internes)
# ---------------------------------------------------------------------------

def _tenant(valeur: Any) -> str:
    texte = str(valeur or "").strip()
    if not texte:
        raise MemoireUnifieeInvalide("tenant_id obligatoire")
    return texte[:128]


def _texte(valeur: Any, maximum: int = 2000) -> str:
    if valeur is None or isinstance(valeur, (Mapping, list, tuple, set, frozenset)):
        return ""
    return str(valeur).strip()[:maximum]


def _normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c)).lower()
    texte = "".join(c if c.isalnum() else " " for c in texte)
    return " ".join(texte.split())


def _tokens(question: Any) -> frozenset[str]:
    tokens = set(_normaliser(question).split())
    return frozenset(t for t in tokens if len(t) > 2) or frozenset(tokens)


def _couverture(tokens: frozenset[str], *parties: Any) -> int:
    if not tokens:
        return 0
    mots = set(_normaliser(" ".join(_texte(p) for p in parties)).split())
    return len(tokens & mots)


def _json_valeur(valeur: Any) -> Any:
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, Decimal):
        return float(valeur)
    return valeur


def _limite(valeur: Any) -> int:
    if isinstance(valeur, bool):
        raise MemoireUnifieeInvalide("limite_par_couche doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise MemoireUnifieeInvalide(
            "limite_par_couche doit être un entier positif") from exc
    return max(1, min(borne, _LIMITE_MAX))


def _selection(couches: Any) -> frozenset[str]:
    if couches is None:
        return frozenset(COUCHES)
    if isinstance(couches, (str, bytes, bytearray)) or not isinstance(couches, Iterable):
        raise MemoireUnifieeInvalide("couches : iterable de noms attendu")
    demandes: set[str] = set()
    for element in couches:
        nom = _texte(element, 40).lower()
        if nom not in COUCHES:
            raise MemoireUnifieeInvalide(
                f"couche inconnue : {element!r} (attendues : {', '.join(COUCHES)})")
        demandes.add(nom)
    return frozenset(demandes)


# ---------------------------------------------------------------------------
# Couche Connaissance : claims ACCEPTED + beliefs
# ---------------------------------------------------------------------------

def _claims_acceptes(conn: Any, tenant: str, tokens: frozenset[str]) -> list[dict]:
    """Claims ACCEPTED valides du tenant, filtrés par recouvrement lexical.

    ``recuperer`` ne lit les claims que pour des ``twin_ids`` explicites ; la
    façade n'en a pas — la requête est bornée (derniers ACCEPTED) puis filtrée
    lexicalement, comme les autres candidats de ``retrieval_memoire``.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, jumeau_id, sujet, predicat, objet, type, statut, maturite, "
            "confiance::float AS confiance, enregistre_le "
            "FROM claim WHERE tenant_id = %s AND statut = 'ACCEPTED' "
            "AND valide_jusqua IS NULL "
            "ORDER BY enregistre_le DESC, id DESC LIMIT %s",
            (tenant, _LIMITE_CANDIDATS)).fetchall()
    resultat: list[dict] = []
    for ligne in lignes:
        couverture = _couverture(
            tokens, ligne["sujet"], ligne["predicat"], ligne["objet"], ligne["type"])
        if tokens and not couverture:
            continue
        resultat.append({
            "genre": "claim",
            "id": str(ligne["id"]),
            "contenu": " ".join(partie for partie in (
                _texte(ligne["sujet"]), _texte(ligne["predicat"]),
                _texte(ligne["objet"])) if partie),
            "sujet": _texte(ligne["sujet"], 400),
            "predicat": _texte(ligne["predicat"], 200),
            "objet": _texte(ligne["objet"], 800),
            "statut": _texte(ligne["statut"], 40),
            "maturite": _texte(ligne["maturite"], 8),
            "confiance": float(ligne["confiance"] or 0.0),
            "jumeau_id": _texte(ligne["jumeau_id"], 200),
            "couverture": couverture,
        })
    return resultat


def _beliefs(conn: Any, tenant: str, tokens: frozenset[str]) -> list[dict]:
    """BELIEF canoniques du tenant (persistés C2), filtrés lexicalement."""
    resultat: list[dict] = []
    for ligne in entreprise_depot.lister_objets(
            conn, tenant, type_="BELIEF", limite=_LIMITE_CANDIDATS):
        donnees = ligne.get("donnees") if isinstance(ligne.get("donnees"), Mapping) else {}
        enonce = _texte(donnees.get("enonce")) or _texte(ligne.get("titre"))
        couverture = _couverture(tokens, enonce, ligne.get("titre"))
        if tokens and not couverture:
            continue
        resultat.append({
            "genre": "belief",
            "id": _texte(ligne.get("id"), 200),
            "contenu": enonce,
            "statut": _texte(donnees.get("statut"), 20) or "ACTIF",
            "source": _texte(donnees.get("source"), 40),
            "claim_ids": [str(c) for c in (donnees.get("claim_ids") or ())][:8],
            "confiance": 0.0,
            "couverture": couverture,
        })
    return resultat


def _couche_connaissance(
        conn: Any, tenant: str, tokens: frozenset[str], limite: int) -> list[dict]:
    entrees = _claims_acceptes(conn, tenant, tokens) + _beliefs(conn, tenant, tokens)
    entrees.sort(key=lambda e: (
        -e["couverture"], e["genre"], -e["confiance"], e["id"]))
    return entrees[:limite]


# ---------------------------------------------------------------------------
# Couche Épisodes : journal d'épisodes + événements de requête
# ---------------------------------------------------------------------------

def _couche_episodes(
        conn: Any, tenant: str, question: str, limite: int) -> list[dict]:
    empreinte = evenements_requete.question_hash(question) if question else ""
    with conn.cursor(row_factory=dict_row) as cur:
        requetes = cur.execute(
            "SELECT id, question_hash, classe, verdict_sonde, confiance, "
            "inconnu_question, inconnu_raison, episode_id, quand "
            "FROM evenement_requete WHERE tenant_id = %s "
            "ORDER BY quand DESC, id DESC LIMIT %s",
            (tenant, _MAX_REQUETES)).fetchall()
    episodes_lies = {
        str(r["episode_id"]) for r in requetes
        if empreinte and r["question_hash"] == empreinte and r["episode_id"]}

    entrees: list[dict] = []
    for groupe in journal_episodes.episodes(conn, tenant, limite=_LIMITE_CANDIDATS):
        episode_id = _texte(groupe.get("episode_id"), 256)
        entrees.append({
            "genre": "episode",
            "id": episode_id,
            "episode_id": episode_id,
            "evenements": int(groupe.get("evenements") or 0),
            "quand": _texte(groupe.get("dernier")),
            "premier": _texte(groupe.get("premier")),
            "lie_question": episode_id in episodes_lies,
        })
    for ligne in requetes:
        meme = bool(empreinte) and ligne["question_hash"] == empreinte
        entrees.append({
            "genre": "requete",
            "id": str(ligne["id"]),
            "classe": _texte(ligne.get("classe"), 64),
            "verdict_sonde": _texte(ligne.get("verdict_sonde"), 32),
            "confiance": _json_valeur(ligne.get("confiance")),
            "inconnu_question": bool(ligne.get("inconnu_question")),
            "inconnu_raison": _texte(ligne.get("inconnu_raison"), 500),
            "episode_id": _texte(ligne.get("episode_id"), 128),
            "quand": _json_valeur(ligne.get("quand")),
            "meme_question": meme,
        })
    # liés à la question d'abord, puis récence, puis clé stable — déterministe
    entrees.sort(key=lambda e: (
        e.get("lie_question") or e.get("meme_question") or False,
        str(e.get("quand") or ""), e["genre"], e["id"]), reverse=True)
    entrees = entrees[:limite]
    # trace compacte des seuls épisodes retenus et liés (lecture bornée)
    for entree in entrees:
        if entree["genre"] == "episode" and entree["lie_question"]:
            entree["trace"] = [
                {"objet": f"{e['objet_type']}:{e['objet_id']}", "action": e["action"]}
                for e in journal_episodes.lire_episode(
                    conn, tenant, entree["episode_id"])[:_MAX_OBJETS_EPISODE]]
    return entrees


# ---------------------------------------------------------------------------
# Couche Recettes : learnings + mesure des signatures de besoins
# ---------------------------------------------------------------------------

def _couche_recettes(
        conn: Any, tenant: str, question: str, limite: int) -> list[dict]:
    entrees: list[dict] = []
    # ``recuperer`` est composée telle quelle : learnings canoniques et mémoire
    # durable « apprentissage » ressortent déjà classés et assainis.
    candidats = retrieval_memoire.recuperer(
        conn, tenant, question=question, limite=_LIMITE_RETRIEVAL)
    learnings: list[dict] = []
    for candidat in candidats:
        if candidat.source == "learning" or (
                candidat.source == "durable" and candidat.classe == "apprentissage"):
            vue = candidat.as_dict()
            vue["genre"] = "learning"
            learnings.append(vue)
    entrees.extend(learnings)
    # mesure des signatures de besoins (C5) : les stats triées par signature
    stats = signatures_besoins.taux_par_signature(conn, tenant)
    for signature, mesure in stats.items():
        if not signature:
            continue
        entrees.append({
            "genre": "signature",
            "id": f"signature:{signature}",
            "signature": signature,
            "contenu": signature,
            "total": int(mesure.get("total") or 0),
            "juges": int(mesure.get("juges") or 0),
            "confirmes": int(mesure.get("confirmes") or 0),
            "taux_confirme": mesure.get("taux_confirme"),
            "ic95": mesure.get("ic95"),
            "score": float(mesure.get("taux_confirme") or 0.0),
        })
    # learnings par score décroissant (déjà classés), signatures par nom — stable
    entrees.sort(key=lambda e: (
        0 if e["genre"] == "learning" else 1,
        -float(e.get("score") or 0.0), e["id"]))
    return entrees[:limite]


# ---------------------------------------------------------------------------
# Couche Documents : chunks documentaires, recouvrement lexical borné
# ---------------------------------------------------------------------------

def _couche_documents(
        conn: Any, tenant: str, tokens: frozenset[str], limite: int) -> list[dict]:
    # préfiltre SQL borné : un ILIKE par token utile (le tri fin reste Python)
    filtre = "tenant_id = %s"
    parametres: list[Any] = [tenant]
    utiles = sorted(tokens)[:_MAX_TOKENS]
    if utiles:
        filtre += " AND (" + " OR ".join(
            "(coalesce(titre, '') || ' ' || coalesce(section, '') || ' ' || texte) "
            "ILIKE '%%' || %s || '%%'" for _ in utiles) + ")"
        parametres.extend(utiles)
    parametres.append(_LIMITE_CANDIDATS)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT id, source_id, twin_id, document_ref, version, ordinal, section, "
            "titre, texte, locator, updated_at FROM document_chunk "
            f"WHERE {filtre} ORDER BY updated_at DESC, id DESC LIMIT %s",
            parametres).fetchall()
    candidats: list[tuple[int, Mapping]] = []
    for ligne in lignes:
        couverture = _couverture(
            tokens, ligne.get("titre"), ligne.get("section"), ligne.get("texte"))
        if tokens and not couverture:
            continue
        candidats.append((couverture, ligne))
    # pertinence décroissante, puis récence, puis id croissant — tris stables
    candidats.sort(key=lambda paire: paire[1]["id"])
    candidats.sort(key=lambda paire: str(paire[1]["updated_at"] or ""), reverse=True)
    candidats.sort(key=lambda paire: paire[0], reverse=True)
    resultat: list[dict] = []
    for couverture, ligne in candidats[:limite]:
        resultat.append({
            "genre": "chunk",
            "id": str(ligne["id"]),
            "document_ref": _texte(ligne.get("document_ref"), 400),
            "version": _texte(ligne.get("version"), 80),
            "ordinal": int(ligne.get("ordinal") or 0),
            "section": _texte(ligne.get("section"), 200),
            "titre": _texte(ligne.get("titre"), 400),
            "extrait": _texte(ligne.get("texte"), _EXTRAIT),
            "locator": _texte(ligne.get("locator"), 600),
            "twin_id": _texte(ligne.get("twin_id"), 200),
            "source_id": ligne.get("source_id"),
            "quand": _json_valeur(ligne.get("updated_at")),
            "couverture": couverture,
        })
    return resultat


# ---------------------------------------------------------------------------
# Façade
# ---------------------------------------------------------------------------

def memoire(
    conn: Any, tenant_id: Any, question: Any, *,
    limite_par_couche: Any = 5, couches: Any = None,
) -> dict:
    """Interroge les 4 couches de mémoire pour une question ; jamais bloquant.

    Rend ``{connaissance, episodes, recettes, documents, totaux, manques,
    erreurs}`` : les 4 clés de couches sont toujours présentes (liste vide si la
    couche n'était pas demandée), ``totaux`` compte les entrées par couche,
    ``manques`` cite les couches **demandées** qui n'ont rien rendu, ``erreurs``
    associe à chaque couche en panne le type de sa défaillance.

    Chaque couche lit dans un savepoint borné : une erreur SQL d'une couche ne
    contamine ni la transaction appelante ni les autres couches.
    """
    tenant = _tenant(tenant_id)
    borne = _limite(limite_par_couche)
    demandees = _selection(couches)
    texte_question = _texte(question, 4000)
    tokens = _tokens(texte_question)

    sortie: dict[str, list[dict]] = {nom: [] for nom in COUCHES}
    erreurs: dict[str, str] = {}
    for nom in COUCHES:
        if nom not in demandees:
            continue
        try:
            with _savepoint(conn):
                if nom == "connaissance":
                    sortie[nom] = _couche_connaissance(conn, tenant, tokens, borne)
                elif nom == "episodes":
                    sortie[nom] = _couche_episodes(conn, tenant, texte_question, borne)
                elif nom == "recettes":
                    sortie[nom] = _couche_recettes(conn, tenant, texte_question, borne)
                else:
                    sortie[nom] = _couche_documents(conn, tenant, tokens, borne)
        except Exception as exc:
            erreurs[nom] = f"{type(exc).__name__}: {_texte(exc, 200)}"
            sortie[nom] = []
    manques = [nom for nom in COUCHES if nom in demandees and not sortie[nom]]
    totaux = {nom: len(sortie[nom]) for nom in COUCHES}
    totaux["total"] = sum(totaux.values())
    return {
        **sortie,
        "totaux": totaux,
        "manques": manques,
        "erreurs": erreurs,
    }
