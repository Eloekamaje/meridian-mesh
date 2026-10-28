"""Le contrat d'une source branchée d'un jumeau (docs/MERIDIAN_Jumeau_Sources_v1.md §3).

Toute source autre que le code est un lecteur : chercher, lire à une version, vérifier une citation. Ajouter une source,
c'est écrire un lecteur et enregistrer sa fabrique ; le contenu lu est une donnée, jamais une instruction.
"""
import re

MAX_RESULTATS = 10
MAX_LIGNES = 200
# systeme://espace/ref@version#Ldébut-Lfin — le code garde sa forme (git://… ou chemin#L…), lue par connaissance.py.
RE_CITATION_SOURCE = re.compile(
    r"(?P<systeme>(?!git)[a-z]+)://(?P<espace>[\w.-]+)/(?P<ref>[\w.-]+)@(?P<version>[\w.-]+)"
    r"#L(?P<debut>\d+)(?:-L(?P<fin>\d+))?")

# Nature de chaque système et ce pour quoi il fait autorité (§1) : annoncé à l'agent dans son prompt.
NATURES = {
    "git": ("code", "ce que l'application fait : comportement programmé, règles appliquées"),
    "confluence": ("documentation", "ce qu'elle est censée faire, pour qui, pourquoi"),
    "jira": ("trajectoire", "pourquoi elle a changé, ce qui est prévu"),
    "datadog": ("comportement", "comment elle se comporte réellement : volumes, appels réels"),
    "servicenow": ("exploitation", "comment elle échoue : incidents, criticité vécue"),
    "schema": ("donnees", "ce qu'elle détient : objets métier, sensibilité"),
}


def locator(systeme, espace, ref, version, debut, fin):
    return f"{systeme}://{espace}/{ref}@{version}#L{debut}-L{fin}"


class Lecteur:
    """Une source branchée. Les sous-classes implémentent `_chercher` et `_lire` ; les bornes et la vérification
    sont communes."""
    systeme = ""

    def __init__(self, nom, espace):
        self.nom, self.espace = nom, espace

    @property
    def nature(self):
        return NATURES.get(self.systeme, ("autre", ""))[0]

    def chercher(self, texte):
        """[{ref, titre, extrait}] bornés."""
        return [{"ref": str(r["ref"]), "titre": r["titre"][:200], "extrait": r.get("extrait", "")[:300]}
                for r in self._chercher(texte.strip()[:200])][:MAX_RESULTATS]

    def lire(self, ref, debut=1, fin=MAX_LIGNES, version=None):
        """{ref, titre, version, lignes, locator} : lignes [debut, fin] (au plus MAX_LIGNES), à `version` ou à la
        dernière version."""
        doc = self._lire(str(ref), version)
        if doc is None:
            raise LookupError(f"{self.systeme} : {ref} introuvable")
        debut, fin = max(1, int(debut)), min(int(fin), len(doc["lignes"]), int(debut) + MAX_LIGNES - 1)
        if fin < debut:
            raise ValueError(f"lignes {debut}-{fin} hors du document ({len(doc['lignes'])} lignes)")
        return {"ref": str(ref), "titre": doc["titre"], "version": str(doc["version"]),
                "lignes": doc["lignes"][debut - 1:fin],
                "locator": locator(self.systeme, self.espace, ref, doc["version"], debut, fin)}

    def verifier(self, citation):
        """La citation existe-t-elle à cette version, avec ces lignes ?"""
        m = RE_CITATION_SOURCE.fullmatch(citation.strip("` "))
        if not m or m["systeme"] != self.systeme or m["espace"] != self.espace:
            return False
        debut = int(m["debut"])
        fin = int(m["fin"] or debut)
        try:
            doc = self._lire(m["ref"], m["version"])
        except (LookupError, ValueError, OSError):
            return False
        return doc is not None and str(doc["version"]) == m["version"] and 1 <= debut <= fin <= len(doc["lignes"])

    def version_courante(self):
        """Version de la source dans son ensemble, pour que le gardien sache si elle a avancé (§6)."""
        raise NotImplementedError

    def _chercher(self, texte):
        raise NotImplementedError

    def _lire(self, ref, version):
        """{titre, version, lignes} ou None."""
        raise NotImplementedError


class LecteurMemoire(Lecteur):
    """Lecteur en mémoire, pour les tests et les démonstrations : {ref: {titre, versions: {version: [lignes]}}}."""
    systeme = "memoire"

    def __init__(self, nom, espace, documents, systeme=None):
        super().__init__(nom, espace)
        self.documents = documents
        if systeme:
            self.systeme = systeme

    def version_courante(self):
        return ",".join(f"{r}@{max(d['versions'], key=int)}" for r, d in sorted(self.documents.items()))

    def _chercher(self, texte):
        motif = texte.lower()
        for ref, d in self.documents.items():
            lignes = d["versions"][max(d["versions"], key=int)]
            trouvees = [l for l in lignes if motif in l.lower()]
            if trouvees or motif in d["titre"].lower():
                yield {"ref": ref, "titre": d["titre"], "extrait": (trouvees or [""])[0]}

    def _lire(self, ref, version):
        d = self.documents.get(ref)
        if not d:
            return None
        v = version or max(d["versions"], key=int)
        return {"titre": d["titre"], "version": v, "lignes": d["versions"][v]} if v in d["versions"] else None


FABRIQUES = {}  # type de source (table `source`) → fabrique(ligne_source) → Lecteur


def lecteurs_de(sources):
    """Lecteurs des sources branchées d'un jumeau (lignes de la table `source`), hors code (GIT)."""
    lecteurs = [(s, FABRIQUES[s["type"]](s)) for s in sources if s.get("type") in FABRIQUES]
    for s, l in lecteurs:
        l.source_id = s.get("id")  # rattache les preuves citées à leur source (table `preuve`)
    return [l for _, l in lecteurs]
