"""Essai de bout en bout d'une source pilote réelle (Confluence ou Jira Cloud) : à lancer le jour où un compte de test
existe. Les six étapes passent par les vrais lecteurs, donc par leurs garde-fous (hôte autorisé, HTTPS, pas de
redirection, réponses bornées). Le jeton n'est jamais affiché.

    python -m jumeau.essai_source --systeme confluence --hote banque.atlassian.net --perimetre TBT \\
        --secret vault:meridian/confluence/pilote#jeton      (ou env:MERIDIAN_CONFLUENCE_PILOTE = « e-mail:jeton »)
"""
import argparse
import os
import re
import sys

from jumeau import confluence, jira
from jumeau.naissance import resoudre_secret

MODULES = {"confluence": confluence, "jira": jira}
VARIABLE_HOTE = {"confluence": "JUMEAU_CONFLUENCE_HOTE", "jira": "JUMEAU_JIRA_HOTE"}


def _manquant(args):
    """Ce qui empêche de lancer l'essai (liste vide si tout est là)."""
    manque = []
    if not (args.hote or os.environ.get(VARIABLE_HOTE[args.systeme])):
        manque.append("l'hôte (--hote banque.atlassian.net)")
    if not args.perimetre:
        manque.append("l'espace Confluence ou le projet Jira (--perimetre)")
    if not args.secret:
        manque.append("la référence du jeton « e-mail:jeton » (--secret vault:chemin#clé ou env:MERIDIAN_…)")
    return manque


def _propre(texte, secret):
    """Message d'erreur sans le jeton ni l'identifiant complet, même si un service le recopiait."""
    for morceau in (secret or "").partition(":")[::2]:
        if morceau:
            texte = texte.replace(morceau, "***")
    return texte


def executer(args, sortie=print):
    """Lance les étapes dans l'ordre ; code de sortie 0 si toutes passent, 1 sinon, 2 s'il manque de quoi commencer."""
    manque = _manquant(args)
    if manque:
        sortie("Essai impossible, il manque : " + " ; ".join(manque) + ". Aucun appel n'a été fait.")
        return 2
    if args.hote:
        os.environ[VARIABLE_HOTE[args.systeme]] = args.hote.lower()
    try:
        secret = resoudre_secret(args.secret)
    except Exception as e:  # Vault absent, variable non autorisée…
        sortie(f"Essai impossible : jeton illisible ({type(e).__name__} : {e}). Aucun appel n'a été fait.")
        return 2
    module, perimetre = MODULES[args.systeme], args.perimetre
    lecteur = {"confluence": confluence.LecteurConfluence, "jira": jira.LecteurJira}[args.systeme](
        f"essai-{perimetre}", perimetre, args.secret)
    etat = {}

    def authentification():
        c = module.compte_du_jeton(secret)
        return f"compte {c['compte']} ({c['nom']})"

    def perimetre_lu():
        trouves = module.perimetres(args.secret, perimetre)
        cles = [p["cle"].lower() for p in trouves]
        if perimetre.lower() not in cles:
            raise LookupError(f"« {perimetre} » absent des {len(trouves)} périmètres lisibles (plafond de la liste : 100 projets, 250 espaces)")
        etat["nom"] = next(p["nom"] for p in trouves if p["cle"].lower() == perimetre.lower())
        return f"{perimetre} « {etat['nom']} » lisible"

    def recherche():
        terme = args.terme or next((m for m in re.findall(r"\w{4,}", etat.get("nom", "")) if m), "") or perimetre
        trouves = lecteur.chercher(terme)
        if not trouves:
            raise LookupError(f"aucun résultat pour « {terme} » (essayer --terme avec un mot présent dans une page ou un ticket)")
        etat["ref"] = trouves[0]["ref"]
        return f"{len(trouves)} résultat(s) pour « {terme} », premier : {etat['ref']}"

    def lecture():
        d = lecteur.lire(etat["ref"])
        etat["doc"] = d
        a_version = lecteur.lire(etat["ref"], version=d["version"] if args.systeme == "confluence" else None)
        if a_version["version"] != d["version"]:
            raise ValueError(f"version demandée {d['version']}, version servie {a_version['version']}")
        return f"{etat['ref']} version {d['version']}, {len(d['lignes'])} ligne(s) lues"

    def citation():
        d = etat["doc"]
        if not lecteur.verifier(d["locator"]):
            raise ValueError(f"citation non vérifiée : {d['locator']}")
        faux = re.sub(r"#L.*", "#L99999-L99999", d["locator"])
        if lecteur.verifier(faux):
            raise ValueError("une citation hors du document a été acceptée")
        return f"{d['locator']} vérifiée ; une ligne inexistante est refusée"

    def courante():
        v = lecteur.version_courante()
        if not v:
            raise LookupError("le périmètre ne renvoie aucune version courante")
        return f"version courante de la source : {v} ; du document : {lecteur.version_actuelle(etat['ref'])}"

    reussi = True
    for nom, etape in [("authentification", authentification), ("lecture du périmètre", perimetre_lu),
                       ("recherche", recherche), ("lecture à une version", lecture),
                       ("vérification d'une citation", citation), ("version courante", courante)]:
        try:
            sortie(f"OK     {nom} : {etape()}")
        except Exception as e:
            sortie(f"ÉCHEC  {nom} : {type(e).__name__} : {_propre(str(e), secret)}")
            reussi = False
            break  # les étapes suivantes dépendent de celle-ci
    return 0 if reussi else 1


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m jumeau.essai_source", description=__doc__.split("\n\n")[0])
    p.add_argument("--systeme", choices=sorted(MODULES), required=True)
    p.add_argument("--hote", help="ex. banque.atlassian.net (sinon JUMEAU_<SYSTÈME>_HOTE)")
    p.add_argument("--perimetre", help="clé de l'espace Confluence ou du projet Jira")
    p.add_argument("--secret", help="référence du jeton : vault:chemin#clé ou env:MERIDIAN_…")
    p.add_argument("--terme", help="mot à chercher (par défaut : un mot du nom du périmètre)")
    return executer(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
