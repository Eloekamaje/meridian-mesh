"""Accès en lecture seule à un dépôt Git, au SHA indexé (jamais à l'arbre de travail)."""
import hashlib
import re
import subprocess

SHA_VALIDE = re.compile(r"[0-9a-f]{7,40}")
TAILLE_MAX = 2_000_000  # octets ; au-delà, le fichier n'est pas une preuve lisible


def _git(depot, *args):
    return subprocess.run(["git", "-C", str(depot), *args], capture_output=True, timeout=30)


def sha_courant(depot):
    return _git(depot, "rev-parse", "HEAD").stdout.decode().strip()


def _verifier(sha, chemin):
    if not SHA_VALIDE.fullmatch(sha) or chemin.startswith(("-", "/")) or ".." in chemin.split("/"):
        raise ValueError(f"preuve invalide : {sha!r}:{chemin!r}")


def lire_au_sha(depot, sha):
    def lire(chemin):
        _verifier(sha, chemin)
        objet = f"{sha}:{chemin}"
        taille = _git(depot, "cat-file", "-s", objet)
        if taille.returncode != 0 or int(taille.stdout) > TAILLE_MAX:
            return None
        texte = _git(depot, "cat-file", "blob", objet).stdout.decode("utf-8", errors="replace")
        # Numérotation de git : seul \n sépare les lignes (pas \f ni \x85 comme splitlines()).
        return texte.removesuffix("\n").split("\n") if texte else []
    return lire


def extrait(preuve, contexte=3):
    """Lignes citées et leur contexte ; `integre` indique si le contenu correspond encore au hash enregistré."""
    lignes = lire_au_sha(preuve["emplacement"], preuve["sha"])(preuve["chemin"])
    if lignes is None:
        return {"integre": False, "lignes": []}
    debut, fin = preuve["ligne_debut"], preuve["ligne_fin"]
    citation = "\n".join(lignes[debut - 1:fin])
    de, a = max(1, debut - contexte), min(len(lignes), fin + contexte)
    return {
        "integre": hashlib.sha256(citation.encode()).hexdigest() == preuve["hash"],
        "lignes": [{"n": n, "texte": lignes[n - 1], "citee": debut <= n <= fin} for n in range(de, a + 1)],
    }
