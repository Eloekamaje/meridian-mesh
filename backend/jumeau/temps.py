"""Le temps du jumeau : ce qui a changé, quand et pourquoi (historique Git et évolution des Claims).

« Qu'est-ce qui a changé ? » est la troisième question de la chaîne de compréhension (Stratégie §2).
L'historique s'arrête toujours au commit ingéré : le jumeau ne parle que de ce qu'il a observé.
"""
import re
import subprocess

from psycopg.rows import dict_row

from jumeau.source_git import SHA_VALIDE

DATE_VALIDE = re.compile(r"\d{4}-\d{2}-\d{2}")
MAX_COMMITS = 30
MAX_FICHIERS = 20  # par commit, pour un contexte borné
SEPARATEUR = "\x1f"


def _git(source, *args):
    r = subprocess.run(["git", "-C", source["emplacement"], *args], capture_output=True, timeout=30)
    if r.returncode != 0:
        raise ValueError(r.stderr.decode("utf-8", errors="replace").strip()[:200])
    return r.stdout.decode("utf-8", errors="replace")


def _verifier_chemin(chemin):
    if chemin.startswith(("-", "/")) or ".." in chemin.split("/"):
        raise ValueError(f"chemin refusé : {chemin!r}")


def _commits(sortie):
    """Analyse un `git log` au format sha␟date␟auteur␟message, suivi éventuellement des fichiers touchés."""
    commits = []
    for ligne in sortie.splitlines():
        if SEPARATEUR in ligne:
            sha, date, auteur, message = ligne.split(SEPARATEUR, 3)
            commits.append({"sha": sha[:12], "date": date, "auteur": auteur, "message": message, "fichiers": []})
        elif ligne.strip() and commits and len(commits[-1]["fichiers"]) < MAX_FICHIERS:
            commits[-1]["fichiers"].append(ligne.strip())
    return commits


def historique(source, depuis="", chemin="", limite=MAX_COMMITS):
    """Commits jusqu'au commit ingéré (le plus récent d'abord), filtrables par date (AAAA-MM-JJ) et par chemin."""
    if depuis and not DATE_VALIDE.fullmatch(depuis):
        raise ValueError("date attendue au format AAAA-MM-JJ")
    if chemin:
        _verifier_chemin(chemin)
    args = ["log", f"--max-count={min(limite, MAX_COMMITS)}", "--date=short", "--name-only",
            f"--format=%H{SEPARATEUR}%ad{SEPARATEUR}%an{SEPARATEUR}%s"]
    if depuis:
        args.append(f"--since={depuis}")
    args += [source["curseur"], "--"] + ([chemin] if chemin else [])
    return _commits(_git(source, *args))


def commits_entre(source, de, a):
    """Commits entre deux versions (de exclue, a incluse), avec les fichiers touchés ; tout l'historique si `de` est None."""
    for sha in filter(None, (de, a)):
        if not SHA_VALIDE.fullmatch(sha):
            raise ValueError(f"version invalide : {sha!r}")
    plage = f"{de}..{a}" if de else a
    return _commits(_git(source, "log", f"--max-count={MAX_COMMITS}", "--date=short", "--name-only",
                         f"--format=%H{SEPARATEUR}%ad{SEPARATEUR}%an{SEPARATEUR}%s", plage, "--"))


def evolution(conn, jumeau_id, depuis):
    """Claims apparus et disparus depuis une date (AAAA-MM-JJ), grâce à leurs dates de validité."""
    if not DATE_VALIDE.fullmatch(depuis):
        raise ValueError("date attendue au format AAAA-MM-JJ")
    with conn.cursor(row_factory=dict_row) as cur:
        apparus = cur.execute(
            "SELECT predicat, objet, statut, valide_depuis::date::text AS quand FROM claim "
            "WHERE jumeau_id = %s AND valide_jusqua IS NULL AND valide_depuis >= %s ORDER BY valide_depuis, objet",
            (jumeau_id, depuis)).fetchall()
        disparus = cur.execute(
            "SELECT predicat, objet, statut, valide_jusqua::date::text AS quand FROM claim "
            "WHERE jumeau_id = %s AND valide_jusqua >= %s ORDER BY valide_jusqua, objet",
            (jumeau_id, depuis)).fetchall()
    return {"apparus": apparus, "disparus": disparus}
