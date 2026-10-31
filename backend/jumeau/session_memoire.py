"""Mémoire de session : résumé borné, provenance et import des conversations.

Cette couche unifie le souvenir d'une session sans recopier la conversation
privée. Elle s'appuie sur :mod:`jumeau.memoire_durable` pour le stockage, la
portée, la rétention et le refus des secrets. Le résumé ne garde que les
derniers messages utiles, sous une limite stricte de caractères ; les pièces,
les jetons et le fil complet d'un case Mongo ne sont jamais copiés.

L'identifiant d'un échange est déterministe à partir du tenant, de la session
et de la question : réenregistrer le même échange rend l'entrée existante au
lieu d'en créer une seconde. La purge ne touche que les entrées de portée
``session`` ; les autres portées restent intactes.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import re

from psycopg.rows import dict_row

from jumeau import memoire_durable, tenant as tenant_module

__all__ = [
    "SessionMemoireInvalide",
    "charger_session",
    "importer_case",
    "lister_sessions",
    "memoriser_session",
    "purger_sessions",
    "resumer_conversation",
]

_DUREE_SESSION_JOURS = 7
_MAX_RESUME = 1200
_MAX_RESUME_DEMANDE = 20_000
_MAX_LIGNES = 12
_MAX_MESSAGES = 500
_MAX_TEXTE_MESSAGE = 600
_MAX_TITRE = 200
_MAX_RESUME_CASE = 400
_MAX_QUESTION = 240

_RE_AFFECTATION = re.compile(
    r"(?i)(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"credential|password|passwd|mot[\s_-]*de[\s_-]*passe|secret|token)\s*[:=]\s*['\"]?"
    r"[A-Za-z0-9_./+~-]{6,}"
)
_RE_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9_.~+/=-]{12,}")
_RE_URL_AUTH = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_RE_PREFIXE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]{8,}|"
    r"xox[baprs]-[A-Za-z0-9-]{8,}|AKIA[A-Z0-9]{12,})\b"
)

_ROLES_UTILISATEUR = frozenset({"user", "utilisateur", "human", "humain", "client", "moi"})
_ROLES_ASSISTANT = frozenset({"assistant", "flore", "bot", "ia", "jumeau", "twin", "agent"})
_CLES_TEXTE = ("texte", "text", "content", "contenu")


class SessionMemoireInvalide(ValueError):
    """Une demande de mémoire de session ne respecte pas son contrat."""


def _tenant(tenant_id) -> str:
    try:
        return tenant_module.exiger_tenant(tenant_id).id
    except tenant_module.TenantError as exc:
        raise SessionMemoireInvalide(str(exc)) from exc


def _compact(valeur, maximum: int | None = None) -> str:
    if valeur is None or isinstance(valeur, (Mapping, list, tuple, set, frozenset, bytes, bytearray)):
        return ""
    texte = " ".join(str(valeur).split())
    if maximum is not None:
        texte = texte[:maximum].rstrip()
    return texte


def _texte_obligatoire(valeur, champ: str, maximum: int | None = None) -> str:
    texte = _compact(valeur, maximum)
    if not texte:
        raise SessionMemoireInvalide(f"{champ} obligatoire")
    return texte


def _entier_positif(valeur, champ: str, maximum: int) -> int:
    if isinstance(valeur, bool):
        raise SessionMemoireInvalide(f"{champ} doit être un entier positif")
    try:
        nombre = int(valeur)
    except (TypeError, ValueError) as exc:
        raise SessionMemoireInvalide(f"{champ} doit être un entier positif") from exc
    if nombre < 1 or nombre > maximum:
        raise SessionMemoireInvalide(f"{champ} doit être comprise entre 1 et {maximum}")
    return nombre


def _instant(valeur, champ: str, defaut=None):
    if valeur is None:
        return defaut
    if isinstance(valeur, datetime):
        instant = valeur
    elif isinstance(valeur, date):
        instant = datetime.combine(valeur, time.min)
    elif isinstance(valeur, str):
        texte = valeur.strip()
        if not texte:
            return defaut
        try:
            instant = datetime.fromisoformat(texte.replace("Z", "+00:00"))
        except ValueError as exc:
            raise SessionMemoireInvalide(f"{champ} doit être une date ISO") from exc
    else:
        raise SessionMemoireInvalide(f"{champ} doit être une date ISO")
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _sans_secret(texte: str) -> str:
    texte = _RE_URL_AUTH.sub(r"\1***@", texte)
    texte = _RE_AFFECTATION.sub("***", texte)
    texte = _RE_BEARER.sub("***", texte)
    texte = _RE_JWT.sub("***", texte)
    return _RE_PREFIXE.sub("***", texte)


def _texte_sain(valeur, maximum: int) -> str:
    return _sans_secret(_compact(valeur))[:maximum].rstrip()


def _role(valeur) -> str | None:
    texte = _compact(valeur).lower()
    if texte in _ROLES_UTILISATEUR:
        return "Utilisateur"
    if texte in _ROLES_ASSISTANT:
        return "Assistant"
    return None


def _extraire_texte(valeur, profondeur: int = 0) -> str:
    if profondeur > 4:
        return ""
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, (list, tuple)):
        morceaux = []
        for element in valeur:
            texte = _extraire_texte(element, profondeur + 1)
            if texte:
                morceaux.append(texte)
        return " ".join(morceaux)
    if isinstance(valeur, Mapping):
        for cle in _CLES_TEXTE:
            if cle in valeur:
                texte = _extraire_texte(valeur[cle], profondeur + 1)
                if texte:
                    return texte
    return ""


def _texte_message(message: Mapping) -> str:
    for cle in _CLES_TEXTE:
        if cle in message:
            texte = _extraire_texte(message[cle])
            if texte:
                return texte
    return ""


def _ligne_resume(message) -> tuple[str, str] | None:
    if not isinstance(message, Mapping):
        return None
    role = _role(message.get("role"))
    if role is None:
        return None
    texte = _sans_secret(_texte_message(message))
    texte = _compact(texte, _MAX_TEXTE_MESSAGE)
    if not texte:
        return None
    return role, texte


def resumer_conversation(messages, *, max_chars=1200) -> str:
    """Résume les derniers messages utilisateur et assistant, sans secret.

    Les mappings sans rôle utile (système, événement, outil) sont ignorés. Les
    messages sont parcourus depuis la fin pour ne garder que les plus récents ;
    chaque ligne est étiquetée ``Utilisateur`` ou ``Assistant``. La sortie ne
    dépasse jamais ``max_chars``, espaces et sauts de ligne compris. La fonction
    est pure : elle ne lit ni réseau ni base.
    """
    budget = _entier_positif(max_chars, "max_chars", _MAX_RESUME_DEMANDE)
    if messages is None or isinstance(messages, (str, bytes, bytearray)):
        return ""
    if isinstance(messages, Mapping):
        elements = [messages]
    else:
        try:
            elements = list(messages)
        except TypeError:
            return ""
    elements = elements[-_MAX_MESSAGES:]

    lignes: list[str] = []
    total = 0
    restant = budget
    for message in reversed(elements):
        extrait = _ligne_resume(message)
        if extrait is None:
            continue
        role, texte = extrait
        prefixe = f"{role} : "
        separateur = 1 if lignes else 0
        if restant < len(prefixe) + separateur + 1:
            break
        disponible = restant - len(prefixe) - separateur
        texte = texte[:disponible].rstrip()
        if not texte:
            break
        ligne = prefixe + texte
        lignes.append(ligne)
        total += len(ligne) + separateur
        restant = budget - total
        if len(lignes) >= _MAX_LIGNES or restant <= 0:
            break
    lignes.reverse()
    return "\n".join(lignes)


def _id_deterministe(tenant: str, genre: str, identifiant: str, charge: str) -> str:
    base = "\x1f".join((genre, tenant, identifiant, charge))
    empreinte = hashlib.sha256(base.encode("utf-8")).hexdigest()
    return f"session-{empreinte[:40]}"


def _limite(valeur, maximum: int = 500) -> int:
    if isinstance(valeur, bool):
        raise SessionMemoireInvalide("limite doit être un entier positif")
    try:
        borne = int(valeur)
    except (TypeError, ValueError) as exc:
        raise SessionMemoireInvalide("limite doit être un entier positif") from exc
    return max(1, min(borne, maximum))


def _jours(expire_jours) -> int:
    if isinstance(expire_jours, bool):
        raise SessionMemoireInvalide("expire_jours doit être un entier positif")
    try:
        jours = int(expire_jours)
    except (TypeError, ValueError) as exc:
        raise SessionMemoireInvalide("expire_jours doit être un entier positif") from exc
    if jours < 1 or jours > 3650:
        raise SessionMemoireInvalide("expire_jours doit être comprise entre 1 et 3650")
    return jours


def _donnees_session(donnees, *, acteur: str, session_id: str, extras=None) -> dict:
    if donnees is None:
        base: dict = {}
    elif isinstance(donnees, Mapping):
        base = dict(donnees)
    else:
        raise SessionMemoireInvalide("donnees doit être un mapping")
    base.update(extras or {})
    base["acteur"] = acteur
    base["session_id"] = session_id
    return base


def _ecrire_session(
    conn, tenant, *, identifiant: str, session_id: str, contenu: str, acteur,
    expire_jours: int, donnees=None, extras=None,
) -> dict:
    acteur_propre = _texte_obligatoire(acteur, "acteur")
    jours = _jours(expire_jours)
    contenu_propre = _texte_obligatoire(contenu, "contenu")
    charge = _donnees_session(donnees, acteur=acteur_propre, session_id=session_id, extras=extras)
    expire_le = datetime.now(timezone.utc) + timedelta(days=jours)

    existant = memoire_durable.lire(conn, tenant, identifiant)
    if existant is not None:
        return existant
    try:
        return memoire_durable.creer(
            conn, tenant, id=identifiant, scope="session", scope_id=session_id,
            classe="session", contenu=contenu_propre, provenance=f"session:{session_id}",
            expire_le=expire_le, donnees=charge,
        )
    except memoire_durable.MemoireDurableInvalide as exc:
        if "existe déjà" in str(exc):
            existant = memoire_durable.lire(conn, tenant, identifiant)
            if existant is not None:
                return existant
        raise


def memoriser_session(
    conn, tenant, session_id, question, reponse, *, acteur,
    expire_jours=7, donnees=None,
) -> dict:
    """Enregistre un échange de session sous forme de résumé borné.

    L'identifiant est déterministe à partir du tenant, de la session et de la
    question : un second appel rend l'entrée existante sans l'écraser. Le
    contenu est un résumé expurgé des secrets ; la réponse complète n'est jamais
    copiée. La provenance vaut ``session:<session_id>`` et la portée est
    ``session`` avec la classe ``session``.
    """
    tenant_id = _tenant(tenant)
    session = _texte_obligatoire(session_id, "session_id")
    question_propre = _texte_obligatoire(question, "question")
    reponse_propre = _compact(reponse)
    contenu = resumer_conversation(
        [
            {"role": "utilisateur", "texte": question_propre},
            {"role": "flore", "texte": reponse_propre},
        ],
        max_chars=_MAX_RESUME,
    )
    if not contenu:
        raise SessionMemoireInvalide("question ou réponse exploitable attendue")
    identifiant = _id_deterministe(tenant_id, "echange", session, question_propre)
    return _ecrire_session(
        conn, tenant_id, identifiant=identifiant, session_id=session, contenu=contenu,
        acteur=acteur, expire_jours=expire_jours, donnees=donnees,
        extras={"question": _texte_sain(question_propre, _MAX_QUESTION)},
    )


def _id_case(case: Mapping) -> str:
    identifiant = case.get("id")
    if identifiant in (None, ""):
        identifiant = case.get("_id")
    if isinstance(identifiant, Mapping):
        identifiant = identifiant.get("$oid")
    return _texte_obligatoire(identifiant, "case.id", 200)


def importer_case(conn, tenant, case, *, acteur) -> dict:
    """Importe un case Mongo comme souvenir de session, sans copier son contenu brut.

    Seuls ``id``, ``titre``, ``resume`` et les derniers messages utiles de
    ``conversation`` sont lus. Les pièces, les jetons et le fil complet restent
    hors du stockage. L'identifiant est stable pour un même tenant et un même
    case, donc un réimport rend l'entrée existante.
    """
    tenant_id = _tenant(tenant)
    if not isinstance(case, Mapping):
        raise SessionMemoireInvalide("case doit être un mapping")
    case_id = _id_case(case)
    session = f"case:{case_id}"
    titre = _texte_sain(case.get("titre"), _MAX_TITRE)
    resume = _texte_sain(case.get("resume"), _MAX_RESUME_CASE)
    conversation = case.get("conversation") or []

    morceaux = []
    if titre:
        morceaux.append(f"Travail « {titre} »")
    if resume:
        morceaux.append(f"Résumé : {resume}")
    echange = resumer_conversation(conversation, max_chars=700)
    if echange:
        morceaux.append(echange)
    contenu = _sans_secret("\n".join(morceaux))[:_MAX_RESUME].rstrip()
    if not contenu:
        raise SessionMemoireInvalide("case sans contenu exploitable")

    identifiant = _id_deterministe(tenant_id, "case", case_id, "")
    return _ecrire_session(
        conn, tenant_id, identifiant=identifiant, session_id=session, contenu=contenu,
        acteur=acteur, expire_jours=_DUREE_SESSION_JOURS,
        extras={"case_id": case_id, "titre": titre, "resume": resume},
    )


def charger_session(conn, tenant, session_id, limite=20) -> list[dict]:
    """Liste les souvenirs durables d'une session, du plus récent au plus ancien.

    La lecture reste bornée au tenant ; les entrées échues restent visibles tant
    qu'elles n'ont pas été purgées, conformément à la couche durable.
    """
    tenant_id = _tenant(tenant)
    session = _texte_obligatoire(session_id, "session_id")
    return memoire_durable.lister(
        conn, tenant_id, scope="session", scope_id=session, limite=limite,
    )


def purger_sessions(conn, tenant, avant=None) -> int:
    """Supprime les souvenirs de session échus, sans toucher aux autres portées.

    ``avant`` borne la date d'expiration prise en compte ; par défaut, l'instant
    UTC courant est utilisé. Seules les lignes de portée ``session`` du tenant
    sont supprimées ; les portées ``user``, ``twin`` et ``situation`` restent
    intactes.
    """
    tenant_id = _tenant(tenant)
    instant = _instant(avant, "avant", defaut=datetime.now(timezone.utc))
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM memoire_durable "
            "WHERE tenant_id = %s AND scope = 'session' "
            "AND expire_le IS NOT NULL AND expire_le <= %s",
            (tenant_id, instant),
        )
        return cur.rowcount


def lister_sessions(conn, tenant, limite=50) -> list[dict]:
    """Regroupe les souvenirs de session par ``scope_id``, pour un tenant.

    Chaque ligne rend ``session_id``, ``nombre`` d'entrées, la première et la
    dernière création, et la dernière mise à jour. Les entrées échues non
    purgées sont comptées, comme dans la vue d'administration durable.
    """
    tenant_id = _tenant(tenant)
    borne = _limite(limite)
    with conn.cursor(row_factory=dict_row) as cur:
        lignes = cur.execute(
            "SELECT scope_id AS session_id, count(*) AS nombre, "
            "min(cree_le) AS premier, max(cree_le) AS dernier, max(maj_le) AS maj_le "
            "FROM memoire_durable WHERE tenant_id = %s AND scope = 'session' "
            "GROUP BY scope_id ORDER BY dernier DESC, session_id LIMIT %s",
            (tenant_id, borne),
        ).fetchall()
    resultat = []
    for ligne in lignes:
        element = dict(ligne)
        element["nombre"] = int(element["nombre"])
        element["scope_id"] = element["session_id"]
        for cle in ("premier", "dernier", "maj_le"):
            valeur = element.get(cle)
            if isinstance(valeur, datetime):
                element[cle] = valeur.isoformat()
        resultat.append(element)
    return resultat
