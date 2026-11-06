"""Sidecar JCL structurel : jobs, étapes, DD et procédures, sans exécution ni réseau."""
from __future__ import annotations

import re
from pathlib import Path

from meridian.domain.code_index import CouvertureFichier, Observation

__all__ = ["JclSidecar"]

PROVIDER = "jcl"
PARSER = "jcl-structural"
VERSION = "1.0"
LANGAGE = "jcl"
SUFFIXES = frozenset({".jcl", ".job", ".proc", ".prc"})

_RE_COMMANDE = re.compile(r"^//(\S*)\s+([A-Za-z]+)(?:\s+(.*))?$")
_RE_AFFECTATION = re.compile(r"^\s*([A-Za-z][\w-]*)\s*=(.*)$", re.S)
_RE_INSTREAM = re.compile(r"\bDD\s+(?:\*|DATA\b)", re.I)
_RE_THEN = re.compile(r"\s*\bTHEN\b.*$", re.I)


def _lire(chemin: Path) -> str:
    """Décode en UTF-8, puis cp1252, puis latin-1 : jamais d'exception d'encodage."""
    donnees = chemin.read_bytes()
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return donnees.decode(encodage)
        except UnicodeDecodeError:
            continue
    return donnees.decode("latin-1", errors="replace")


def _cle_fichier(racine: Path, chemin: Path) -> str:
    """Chemin stable : relatif à la racine quand il y est, absolu sinon."""
    try:
        return chemin.resolve().relative_to(racine.resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        try:
            return chemin.resolve().as_posix()
        except (OSError, RuntimeError):
            return str(chemin)


def _premier_mot(texte: str) -> str:
    """Premier mot hors espaces, en s'arrêtant hors parenthèses et littéraux."""
    profondeur = 0
    guillemet = None
    for i, caractere in enumerate(texte.strip()):
        if guillemet:
            if caractere == guillemet:
                guillemet = None
            continue
        if caractere in "'\"":
            guillemet = caractere
        elif caractere == "(":
            profondeur += 1
        elif caractere == ")":
            profondeur = max(0, profondeur - 1)
        elif caractere.isspace() and profondeur == 0:
            return texte.strip()[:i]
    return texte.strip()


def _operandes(texte: str):
    """Sépare les opérandes JCL en mots-clés et positionnels, virgules de premier niveau."""
    morceaux = []
    tampon = []
    profondeur = 0
    guillemet = None
    for caractere in texte:
        if guillemet:
            tampon.append(caractere)
            if caractere == guillemet:
                guillemet = None
        elif caractere in "'\"":
            guillemet = caractere
            tampon.append(caractere)
        elif caractere == "(":
            profondeur += 1
            tampon.append(caractere)
        elif caractere == ")":
            profondeur = max(0, profondeur - 1)
            tampon.append(caractere)
        elif caractere == "," and profondeur == 0:
            morceaux.append("".join(tampon))
            tampon = []
        else:
            tampon.append(caractere)
    if tampon or texte.strip():
        morceaux.append("".join(tampon))
    mots_cles, positionnels = {}, []
    for morceau in morceaux:
        affectation = _RE_AFFECTATION.match(morceau)
        if affectation:
            mots_cles[affectation.group(1).upper()] = _premier_mot(affectation.group(2))
        elif morceau.strip():
            positionnels.append(_premier_mot(morceau))
    return mots_cles, positionnels


def _valeur(texte: str) -> str:
    """Valeur sans guillemets englobants."""
    texte = texte.strip()
    if len(texte) >= 2 and texte[0] == texte[-1] and texte[0] in "'\"":
        return texte[1:-1]
    return texte


def _couper(ligne: str):
    """Colonnes 1-71 utiles, colonne 72 = continuation, reste = commentaire."""
    continu = len(ligne) > 71 and ligne[71] not in " \t"
    texte = ligne[:71].rstrip() if len(ligne) > 71 else ligne.rstrip()
    if not continu:
        continu = texte.endswith(",")
    return texte, continu


def _suite(ligne: str) -> bool:
    """Une ligne de continuation a un champ nom vide (``//`` suivi d'espaces)."""
    return len(ligne) > 2 and ligne[2] in " \t"


def _instructions(lignes):
    """Rend (début, fin, texte logique) ; commentaires et données inline ignorés."""
    resultat = []
    courant = None
    debut = fin = 0
    continu = False
    instream = False

    def vider():
        nonlocal courant
        if courant is not None:
            resultat.append((debut, fin, courant))
            courant = None

    for numero, brute in enumerate(lignes, 1):
        ligne = brute.rstrip("\r\n")
        if instream:
            if ligne.strip().startswith("/*"):
                instream = False
            continue
        if not ligne.strip():
            vider()
            continu = False
            continue
        if ligne.startswith("//*"):
            continue
        if ligne.startswith("/*"):
            vider()
            continu = False
            continue
        if not ligne.startswith("//"):
            vider()
            continu = False
            continue
        texte, suite = _couper(ligne)
        if courant is not None and continu and _suite(ligne):
            courant = courant.rstrip() + " " + texte[2:].strip()
            fin = numero
        else:
            vider()
            courant = texte
            debut = fin = numero
        continu = suite
        if _RE_INSTREAM.search(courant):
            vider()
            continu = False
            instream = True
    vider()
    return resultat


class JclSidecar:
    """Index structurel JCL : observations locales, aucune soumission de job."""

    provider = PROVIDER
    extensions = tuple(SUFFIXES)
    parser = PARSER
    parser_version = VERSION
    language = LANGAGE

    def index(self, racine: str, fichiers=()) -> list[Observation]:
        fichiers = tuple(fichiers or ())
        observations = []
        for chemin in self._candidats(racine, fichiers):
            if chemin.suffix.lower() not in SUFFIXES or not chemin.is_file():
                continue
            try:
                texte = _lire(chemin)
                fichier = _cle_fichier(Path(racine), chemin)
                observations.extend(self._extraire(fichier, texte))
            except Exception:
                continue
        return observations

    def couverture(self, racine: str, fichiers=()) -> list[CouvertureFichier]:
        fichiers = tuple(fichiers or ())
        trouvees = {}
        for observation in self.index(racine, fichiers=fichiers):
            trouvees.setdefault(observation.file, observation)
        lignes = {}
        for chemin in self._candidats(racine, fichiers):
            cle = _cle_fichier(Path(racine), chemin)
            if cle in lignes:
                continue
            if chemin.suffix.lower() not in SUFFIXES:
                lignes[cle] = CouvertureFichier(
                    file=cle, parser=self.parser, statut="non_supporte",
                    raison="extension non prise en charge")
            elif cle in trouvees:
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="indexe")
            elif not chemin.is_file():
                lignes[cle] = CouvertureFichier(
                    file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                    raison="fichier introuvable ou illisible")
            else:
                try:
                    _lire(chemin)
                except OSError as erreur:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser, statut="ignore",
                        raison=f"lecture impossible : {erreur}")
                else:
                    lignes[cle] = CouvertureFichier(
                        file=cle, language=LANGAGE, parser=self.parser, statut="partiel",
                        raison="aucune structure JCL reconnue")
        return [lignes[cle] for cle in sorted(lignes)]

    @staticmethod
    def _candidats(racine: str, fichiers):
        base = Path(racine)
        if fichiers:
            for nom in fichiers:
                chemin = Path(nom)
                yield chemin if chemin.is_absolute() else base / chemin
            return
        try:
            for chemin in sorted(base.rglob("*")):
                if chemin.is_file() and chemin.suffix.lower() in SUFFIXES:
                    yield chemin
        except OSError:
            return

    def _extraire(self, fichier: str, texte: str) -> list[Observation]:
        observations = []
        job = ""
        etape = ""
        conditions = []
        for debut, fin, instruction in _instructions(texte.splitlines()):
            commande = _RE_COMMANDE.match(instruction.strip())
            if not commande:
                continue
            nom = commande.group(1)
            operation = commande.group(2).upper()
            reste = (commande.group(3) or "").strip()
            mots_cles, positionnels = _operandes(reste)

            if operation == "JOB":
                if not nom:
                    continue
                job, etape = nom, ""
                attributs = {"job": nom}
                if mots_cles.get("COND"):
                    attributs["cond"] = mots_cles["COND"]
                observations.append(self._obs(
                    fichier, "jcl_job", nom, debut, fin, attributs))
                continue

            if operation == "EXEC":
                if not nom:
                    continue
                etape = nom
                pgm = _valeur(mots_cles.get("PGM", ""))
                proc = _valeur(mots_cles.get("PROC", ""))
                if not pgm and not proc and positionnels:
                    proc = _valeur(positionnels[0])
                cond = mots_cles.get("COND", "")
                attributs = {"step": nom}
                if job:
                    attributs["job"] = job
                if pgm:
                    attributs["pgm"] = pgm
                if proc:
                    attributs["proc"] = proc
                if cond:
                    attributs["cond"] = cond
                attributs.update(self._contexte_if(conditions))
                observations.append(self._obs(
                    fichier, "jcl_step", nom, debut, fin, dict(attributs)))
                if pgm:
                    attributs_programme = {"pgm": pgm, "step": nom}
                    if job:
                        attributs_programme["job"] = job
                    if cond:
                        attributs_programme["cond"] = cond
                    attributs_programme.update(self._contexte_if(conditions))
                    observations.append(self._obs(
                        fichier, "jcl_program", pgm, debut, fin, attributs_programme))
                if proc:
                    attributs_proc = {"proc": proc, "step": nom}
                    if job:
                        attributs_proc["job"] = job
                    if cond:
                        attributs_proc["cond"] = cond
                    attributs_proc.update(self._contexte_if(conditions))
                    observations.append(self._obs(
                        fichier, "jcl_proc", proc, debut, fin, attributs_proc))
                continue

            if operation == "DD":
                if not nom:
                    continue
                dsn = _valeur(mots_cles.get("DSN") or mots_cles.get("DSNAME") or "")
                disp = mots_cles.get("DISP", "")
                attributs = {"dd": nom}
                if job:
                    attributs["job"] = job
                if etape:
                    attributs["step"] = etape
                if dsn:
                    attributs["dsn"] = dsn
                if disp:
                    attributs["disp"] = disp
                attributs.update(self._contexte_if(conditions))
                observations.append(self._obs(
                    fichier, "jcl_dd", nom, debut, fin, dict(attributs)))
                if dsn:
                    attributs_dataset = {"dsn": dsn, "dd": nom}
                    if job:
                        attributs_dataset["job"] = job
                    if etape:
                        attributs_dataset["step"] = etape
                    if disp:
                        attributs_dataset["disp"] = disp
                    attributs_dataset.update(self._contexte_if(conditions))
                    observations.append(self._obs(
                        fichier, "jcl_dataset", dsn, debut, fin, attributs_dataset))
                continue

            if operation == "PROC":
                if not nom:
                    continue
                observations.append(self._obs(
                    fichier, "jcl_proc", nom, debut, fin, {"proc": nom}))
                continue

            if operation == "SET":
                affectation = _RE_AFFECTATION.match(reste)
                if not affectation:
                    continue
                variable = affectation.group(1)
                valeur = _valeur(_premier_mot(affectation.group(2)))
                attributs = {"set": variable, "value": valeur}
                if job:
                    attributs["job"] = job
                observations.append(self._obs(
                    fichier, "jcl_set", variable, debut, fin, attributs))
                continue

            if operation == "INCLUDE":
                membre = _valeur(mots_cles.get("MEMBER", ""))
                if not membre and positionnels:
                    membre = _valeur(positionnels[0])
                if not membre:
                    continue
                attributs = {"include": membre, "member": membre}
                if job:
                    attributs["job"] = job
                observations.append(self._obs(
                    fichier, "jcl_include", membre, debut, fin, attributs))
                continue

            if operation == "IF":
                condition = _RE_THEN.sub("", reste).strip()
                if condition:
                    conditions.append({"cond": condition, "branche": "then"})
                continue
            if operation == "THEN":
                continue
            if operation == "ELSE":
                if conditions:
                    conditions[-1]["branche"] = "else"
                continue
            if operation in {"ENDIF", "END-IF"}:
                if conditions:
                    conditions.pop()
                continue
        return observations

    @staticmethod
    def _contexte_if(conditions):
        if not conditions:
            return {}
        return {"if": conditions[-1]["cond"], "if_branch": conditions[-1]["branche"]}

    @staticmethod
    def _obs(fichier, kind, symbol, debut, fin, attributs=None) -> Observation:
        return Observation(
            provider=PROVIDER, parser=PARSER, parser_version=VERSION, file=fichier,
            language=LANGAGE, kind=kind, symbol=symbol, start=debut, end=fin,
            attributes=attributs or {})
