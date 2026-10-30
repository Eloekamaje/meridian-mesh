"""Harnais reproductible d'évaluation de la sélection des sections de pièces jointes.

Le jeu de questions est un JSONL : une ligne par question, avec la pièce et la section attendue (id ou titre).
Aucune base n'est nécessaire : seules les pièces fournies comptent, et la sélection est celle du vrai chemin de
Flore (`pieces.sections_pour_prompt_detail`). Quand cette fonction n'est pas encore disponible, le repli appelle
`pieces._selection_sections` et `pieces._sections_doc`, ce qui garde les tests unitaires exécutables.

    python -m evaluation_pieces --docs docs.json --questions questions.jsonl [--k 4]

Le contrat actuel de `sections_pour_prompt_detail` rend `(bloc, inclusions)` : le harnais ne lit que la liste
ordonnée des inclusions (`piece_id`, `section_id`, `titre`). Une liste seule, un mapping pièce -> sections et les
variantes voisines (`piece`/`section`/`id`, groupes `sections`, indices) sont aussi normalisés. Quand une pièce
est incluse intégralement (`section_id` « document »), toutes ses sections sont considérées comme disponibles.

Pour chaque question, le rang est la position (1-based) de la section attendue dans les inclusions de la bonne
pièce. `recall_at_k` est la part de questions dont le rang est ≤ k ; `mrr` est la moyenne des inverses des rangs,
une question sans réponse comptant 0 (le rang complet est utilisé, sans troncature à k).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pieces

CHAMPS_QUESTION = ("question", "piece", "section")
_CLES_PIECE = ("piece_id", "id_piece", "piece", "doc_id", "id_doc", "document_id", "document")
_CLES_SECTION = ("section_id", "id_section", "section", "id")
_CLES_TITRE = ("titre", "title", "nom_section")
_CLES_RANG = ("rang", "rank", "position")
_CLES_GROUPE = ("sections", "selection", "details", "resultats", "résultats")
_CLES_PIECES = ("pieces", "documents")


def _texte(valeur) -> str | None:
    """Une valeur scalaire nettoyée, ou None quand elle est absente ou vide."""
    if valeur is None or isinstance(valeur, (dict, list, tuple)):
        return None
    texte = str(valeur).strip()
    return texte or None


def _valeur_cle(dictionnaire: dict, cles: tuple[str, ...]):
    """La première valeur renseignée parmi plusieurs noms de clés acceptés."""
    for cle in cles:
        if cle in dictionnaire and dictionnaire[cle] is not None:
            return dictionnaire[cle]
    return None


def _champs_invalides(brut: dict) -> list[str]:
    """Les champs obligatoires absents, vides ou non scalaires d'une question."""
    return [champ for champ in CHAMPS_QUESTION
            if champ not in brut or _texte(brut.get(champ)) is None]


def charger_jeu(chemin) -> list[dict]:
    """Lit un JSONL de questions `{question, piece, section}` et refuse les lignes incomplètes.

    Les lignes vides sont ignorées. Une erreur cite le fichier et le numéro de ligne, avec les champs fautifs.
    """
    chemin = Path(chemin)
    questions: list[dict] = []
    with chemin.open("r", encoding="utf-8-sig") as flux:
        for numero, ligne in enumerate(flux, 1):
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                brut = json.loads(ligne)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{chemin}:{numero} : JSON invalide ({exc.msg}).") from exc
            if not isinstance(brut, dict):
                raise ValueError(f"{chemin}:{numero} : la ligne doit être un objet JSON.")
            invalides = _champs_invalides(brut)
            if invalides:
                champs = ", ".join(f"« {champ} »" for champ in invalides)
                raise ValueError(f"{chemin}:{numero} : ligne incomplète — champs manquants ou vides : {champs}.")
            questions.append({champ: _texte(brut[champ]) for champ in CHAMPS_QUESTION})
    return questions


def _reference_piece(doc: dict) -> str | None:
    """L'identité d'une pièce : son id, à défaut son nom."""
    return _texte(doc.get("id")) or _texte(doc.get("nom"))


def _sections_doc(doc: dict) -> list[dict]:
    """Les sections d'une pièce, par le même découpage que le chemin réel."""
    fonction = getattr(pieces, "_sections_doc", None)
    sections = None
    if callable(fonction):
        try:
            sections = fonction(doc)
        except Exception:
            sections = None
    if not isinstance(sections, list):
        sections = doc.get("sections") if isinstance(doc.get("sections"), list) else []
    return [section for section in sections if isinstance(section, dict)]


def _indexer_docs(docs: list[dict]) -> list[dict]:
    """Les pièces et leurs sections, prêtes pour résoudre une référence de sélection."""
    return [{"doc": doc, "reference": _reference_piece(doc), "sections": _sections_doc(doc)} for doc in docs]


def _doc_correspond(doc: dict, piece) -> bool:
    """Vrai si la référence (id, nom ou dict de pièce) désigne ce document."""
    if isinstance(piece, dict):
        return any(_doc_correspond(doc, piece.get(cle)) for cle in ("id", "nom", "piece_id", "id_piece"))
    valeur = _texte(piece)
    return bool(valeur) and any(_texte(doc.get(cle)) == valeur for cle in ("id", "nom"))


def _resoudre_doc(index: list[dict], piece) -> dict | None:
    """L'entrée d'index correspondant à une référence de pièce, ou None."""
    if piece is None:
        return None
    for entree in index:
        if _doc_correspond(entree["doc"], piece):
            return entree
    return None


def _reference_selection(piece) -> str | None:
    """Une référence de pièce ramenée à un scalaire utilisable dans le détail."""
    if isinstance(piece, dict):
        for cle in ("id", "nom", "piece_id", "id_piece"):
            valeur = _texte(piece.get(cle))
            if valeur:
                return valeur
        return None
    return _texte(piece)


def _egales(gauche, droite) -> bool:
    """Comparaison tolérante à la casse et aux espaces, sans dépendance."""
    texte_gauche, texte_droite = _texte(gauche), _texte(droite)
    if texte_gauche is None or texte_droite is None:
        return False
    if texte_gauche == texte_droite:
        return True
    return " ".join(texte_gauche.casefold().split()) == " ".join(texte_droite.casefold().split())


def _trouver_section(sections: list[dict], identifiant=None, titre=None) -> dict | None:
    """La section qui porte cet id, à défaut ce titre."""
    if identifiant is not None:
        for section in sections:
            if _egales(section.get("id"), identifiant):
                return section
    if titre is not None:
        for section in sections:
            if _egales(section.get("titre"), titre):
                return section
    return None


def _doc_de_section(index: list[dict], identifiant=None, titre=None) -> dict | None:
    """La pièce unique qui contient cette section ; None si l'information est ambiguë."""
    candidates = [entree for entree in index
                  if _trouver_section(entree["sections"], identifiant, titre) is not None]
    return candidates[0] if len(candidates) == 1 else None


def _enrichir_entree(entree: dict, index: list[dict]) -> dict | None:
    """Complète une section sélectionnée avec son id, son titre et sa pièce quand ils sont déductibles."""
    piece = entree.get("piece")
    identifiant = entree.get("id")
    titre = entree.get("titre")
    doc = _resoudre_doc(index, piece) if piece is not None else None
    if isinstance(identifiant, int):
        if doc is not None and 0 <= identifiant < len(doc["sections"]):
            section = doc["sections"][identifiant]
            identifiant = section.get("id")
            titre = titre or section.get("titre")
        else:
            identifiant = str(identifiant)
    if doc is not None:
        piece = doc["reference"]
    elif piece is None and (identifiant is not None or titre is not None):
        doc = _doc_de_section(index, identifiant, titre)
        if doc is not None:
            piece = doc["reference"]
    if doc is not None:
        section = _trouver_section(doc["sections"], identifiant, titre)
        if section is not None:
            identifiant = identifiant if identifiant is not None else section.get("id")
            titre = titre if titre is not None else section.get("titre")
    if identifiant is None and titre is None:
        return None
    return {
        "piece": _reference_selection(piece),
        "id": _texte(identifiant),
        "titre": _texte(titre),
        "rang": entree.get("rang"),
    }


def _entrees_indices(indices, piece, rang, index: list[dict]) -> list[dict]:
    """Développe des indices de sections (le format interne de `_selection_sections`)."""
    doc = _resoudre_doc(index, piece) if piece is not None else None
    if doc is None:
        return []
    if not isinstance(indices, (list, tuple)):
        indices = [indices]
    entrees = []
    for indice in indices:
        if not isinstance(indice, int):
            entree = _enrichir_entree({"piece": piece, "id": indice, "titre": None, "rang": rang}, index)
        elif 0 <= indice < len(doc["sections"]):
            section = doc["sections"][indice]
            entree = {"piece": doc["reference"], "id": section.get("id"), "titre": section.get("titre"),
                      "rang": rang}
        else:
            entree = None
        if entree:
            entrees.append(entree)
    return entrees


def _entrees_depuis_brut(brut: dict, index: list[dict], piece_defaut=None) -> list[dict]:
    """Une entrée de sélection normalisée, ou un développement d'indices."""
    piece = _reference_selection(_valeur_cle(brut, _CLES_PIECE)) or _reference_selection(piece_defaut)
    identifiant = _valeur_cle(brut, _CLES_SECTION)
    titre = _valeur_cle(brut, _CLES_TITRE)
    if isinstance(identifiant, dict):
        imbrique = identifiant
        identifiant = _valeur_cle(imbrique, _CLES_SECTION)
        if titre is None:
            titre = _valeur_cle(imbrique, _CLES_TITRE)
    rang = _valeur_cle(brut, _CLES_RANG)
    if "indices" in brut:
        return _entrees_indices(brut["indices"], piece, rang, index)
    if identifiant is None and titre is None:
        return []
    entree = _enrichir_entree({"piece": piece, "id": identifiant, "titre": _texte(titre), "rang": rang}, index)
    return [entree] if entree else []


def _est_entree(brut: dict) -> bool:
    """Une entrée plate porte au moins un id ou un titre de section."""
    return any(cle in brut for cle in (*_CLES_SECTION, *_CLES_TITRE))


def _collecter_entrees(brut, sortie: list, piece_defaut=None) -> None:
    """Aplatit les formes acceptées du détail en entrées de section, dans l'ordre de pertinence."""
    if brut is None:
        return
    if isinstance(brut, dict):
        if any(cle in brut for cle in _CLES_GROUPE):
            piece = _valeur_cle(brut, _CLES_PIECE)
            if piece is None:
                piece = _valeur_cle(brut, ("id", "nom"))
            piece = piece if piece is not None else piece_defaut
            for cle in _CLES_GROUPE:
                if cle in brut:
                    _collecter_entrees(brut[cle], sortie, piece)
                    return
            return
        for cle in _CLES_PIECES:
            if cle in brut:
                _collecter_entrees(brut[cle], sortie, piece_defaut)
                return
        if _est_entree(brut):
            sortie.append((brut, piece_defaut))
            return
        for piece, valeur in brut.items():
            _collecter_entrees(valeur, sortie, piece)
        return
    if isinstance(brut, tuple) and len(brut) == 2:
        sortie.append(({"piece": brut[0], "section": brut[1]}, None))
        return
    if isinstance(brut, (list, tuple)):
        for element in brut:
            _collecter_entrees(element, sortie, piece_defaut)
        return
    texte = _texte(brut)
    if texte is None:
        return
    if "#" in texte:
        piece, _, identifiant = texte.partition("#")
        piece = piece.rsplit(":", 1)[-1]
        sortie.append(({"piece": piece.strip() or piece_defaut, "id": identifiant}, None))
        return
    sortie.append(({"piece": piece_defaut, "id": texte}, None))


def _normaliser_selection(detail, docs: list[dict]) -> list[dict]:
    """Ramène le détail de sélection à une liste ordonnée de sections (`piece`, `id`, `titre`)."""
    index = _indexer_docs(docs)
    brutes: list = []
    _collecter_entrees(detail, brutes)
    entrees: list[dict] = []
    for brute, piece_defaut in brutes:
        if isinstance(brute, dict):
            entrees.extend(_entrees_depuis_brut(brute, index, piece_defaut))
    if entrees and all(entree.get("rang") is not None for entree in entrees):
        def cle(entree):
            try:
                return float(entree["rang"])
            except (TypeError, ValueError):
                return float("inf")

        entrees.sort(key=cle)
    return entrees


def _selection_repli(docs: list[dict], question: str) -> list[dict]:
    """La sélection de secours, construite avec les fonctions internes de `pieces`."""
    sections_doc = getattr(pieces, "_sections_doc", None)
    selectionner = getattr(pieces, "_selection_sections", None)
    if not callable(sections_doc) or not callable(selectionner):
        return []
    selection = []
    for doc in docs:
        sections = _sections_doc(doc)
        indices = selectionner(sections, str(doc.get("texte") or ""), question)
        for indice in indices or []:
            if isinstance(indice, int) and 0 <= indice < len(sections):
                section = sections[indice]
                selection.append({"piece": _reference_piece(doc), "id": _texte(section.get("id")),
                                  "titre": _texte(section.get("titre"))})
    return selection


def _selection_detail(docs: list[dict], question: str) -> list[dict]:
    """La sélection du chemin réel quand le détail existe, sinon le repli documenté.

    Le contrat actuel de `sections_pour_prompt_detail` rend `(bloc, inclusions)` ; seule la liste des
    inclusions compte ici. Une liste seule reste acceptée.
    """
    fonction = getattr(pieces, "sections_pour_prompt_detail", None)
    if not callable(fonction):
        return _selection_repli(docs, question)
    detail = fonction(docs, question)
    if isinstance(detail, tuple) and len(detail) == 2:
        if isinstance(detail[1], str) and not isinstance(detail[0], str):
            detail = detail[0]
        elif isinstance(detail[0], str) and not isinstance(detail[1], str):
            detail = detail[1]
    return _normaliser_selection(detail, docs)


def _memes_pieces(gauche, droite, index: list[dict]) -> bool:
    """Vrai si deux références désignent la même pièce (id ou nom)."""
    if gauche is None or droite is None:
        return True
    if _egales(gauche, droite):
        return True
    doc_gauche = _resoudre_doc(index, gauche)
    doc_droite = _resoudre_doc(index, droite)
    return doc_gauche is not None and doc_gauche is doc_droite


def _section_correspond(entree: dict, attendu: str) -> bool:
    """Vrai si la section sélectionnée porte l'id ou le titre attendu."""
    return any(_egales(entree.get(cle), attendu) for cle in ("id", "titre"))


def _document_integral(entree: dict, attendu: dict, index: list[dict]) -> bool:
    """Vrai si la pièce entière est fournie et contient bien la section attendue."""
    if not _egales(entree.get("id"), "document"):
        return False
    doc = _resoudre_doc(index, attendu["piece"])
    return doc is not None and any(_section_correspond(section, attendu["section"])
                                   for section in doc["sections"])


def _rang_attendu(selection: list[dict], attendu: dict, index: list[dict]) -> int | None:
    """Le rang (1-based) de la section attendue dans la sélection, None si elle n'y figure pas.

    Une pièce donnée intégralement (`section_id` « document ») contient toutes ses sections : son rang est
    celui du bloc de la pièce, à condition que la section attendue existe réellement dans cette pièce.
    """
    for rang, entree in enumerate(selection, 1):
        if entree.get("piece") is not None and not _memes_pieces(entree["piece"], attendu["piece"], index):
            continue
        if _section_correspond(entree, attendu["section"]) or _document_integral(entree, attendu, index):
            return rang
    return None


def _question_normalisee(question) -> dict:
    """Valide et ramène une question à ses trois champs texte."""
    if not isinstance(question, dict):
        raise ValueError("question invalide : un objet {question, piece, section} est attendu.")
    invalides = _champs_invalides(question)
    if invalides:
        champs = ", ".join(f"« {champ} »" for champ in invalides)
        raise ValueError(f"question incomplète — champs manquants ou vides : {champs}.")
    return {champ: _texte(question[champ]) for champ in CHAMPS_QUESTION}


def _resume_selection(selection: list[dict]) -> list[dict]:
    """La sélection telle qu'elle apparaît dans le détail, sans les champs internes."""
    return [{"piece": entree.get("piece"), "section": entree.get("id"), "titre": entree.get("titre")}
            for entree in selection]


def evaluer(docs, questions, k: int = 4) -> dict:
    """Évalue le rang de la section attendue de chaque question.

    `docs` est une liste de pièces `{id, nom, texte, sections?}` et `questions` une liste de dicts
    `{question, piece, section}`. Pour chaque question : `rang` (1-based, None si absente de la sélection),
    `hit` (rang ≤ k), et la sélection réellement obtenue. `recall_at_k` et `mrr` sont les moyennes sur les
    questions ; une question sans réponse compte 0 dans les deux métriques. `mrr` utilise le rang complet,
    sans troncature à k.
    """
    if not isinstance(k, int) or k < 1:
        raise ValueError("k doit être un entier supérieur ou égal à 1.")
    docs = [doc for doc in (docs or []) if isinstance(doc, dict)]
    index = _indexer_docs(docs)
    details = []
    for question in questions or []:
        attendu = _question_normalisee(question)
        selection = _selection_detail(docs, attendu["question"])
        rang = _rang_attendu(selection, attendu, index)
        details.append({
            "question": attendu["question"],
            "piece": attendu["piece"],
            "section": attendu["section"],
            "rang": rang,
            "hit": rang is not None and rang <= k,
            "hit_at_k": rang is not None and rang <= k,
            "selection": _resume_selection(selection),
        })
    n = len(details)
    recall_at_k = sum(1 for detail in details if detail["hit"]) / n if n else 0.0
    mrr = sum(1.0 / detail["rang"] for detail in details if detail["rang"] is not None) / n if n else 0.0
    return {"n": n, "recall_at_k": recall_at_k, "mrr": mrr, "details": details}


def _lire_docs(chemin) -> list[dict]:
    """Lit le JSON des pièces : une liste de `{id, nom, texte, sections?}`."""
    with Path(chemin).open("r", encoding="utf-8-sig") as flux:
        docs = json.load(flux)
    if not isinstance(docs, list):
        raise ValueError("docs.json doit contenir une liste de pièces.")
    if not all(isinstance(doc, dict) for doc in docs):
        raise ValueError("docs.json : chaque pièce doit être un objet JSON.")
    return docs


def main(argv=None) -> int:
    """Point d'entrée : mesure un jeu et écrit le résultat JSON sur la sortie standard."""
    analyseur = argparse.ArgumentParser(
        prog="python -m evaluation_pieces",
        description="Évalue la sélection des sections de pièces jointes sur un jeu de questions reproductible.",
    )
    analyseur.add_argument("--docs", required=True,
                           help="JSON contenant la liste des pièces ({id, nom, texte, sections?}).")
    analyseur.add_argument("--questions", required=True,
                           help="JSONL de questions {question, piece, section} (pièce = id ou nom).")
    analyseur.add_argument("--k", type=int, default=4,
                           help="profondeur du recall@k (entier ≥ 1, défaut : 4).")
    args = analyseur.parse_args(argv)
    try:
        resultat = evaluer(_lire_docs(args.docs), charger_jeu(args.questions), k=args.k)
    except (OSError, TypeError, ValueError) as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
