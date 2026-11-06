#!/usr/bin/env python3
"""Benchmark conversationnel Flore/Méridian contre un assistant générique.

Le runner rejoue des conversations multi-tours sur l'API réelle de Méridian
(``POST /cases`` puis ``POST /cases/{id}/messages``), produit les mêmes tours
pour un modèle seul (sans outils ni connaissances Méridian), applique des
critères déterministes, puis fait juger les deux transcriptions à l'aveugle.

Aucun secret n'est affiché : la clé DeepSeek est lue dans l'environnement ou
``backend/.env`` et n'apparaît ni dans les rapports ni dans les journaux.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import random
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import requests

RACINE = Path(__file__).resolve().parents[4]
SCENARIOS_DEFAUT = Path(__file__).with_name("scenarios.json")
API_DEFAUT = os.environ.get("MERIDIAN_API_URL", "http://127.0.0.1:8001/api")
MODELE_DEFAUT = os.environ.get("DEEPSEEK_MODELE", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

SYSTEME_BASELINE = """Tu es un assistant d'entreprise francophone, utile et concis.
Tu n'as pas accès aux données internes de l'entreprise : applications, dépendances,
claims, preuves, incidents, situations ou mesures. Si une question porte sur ces
données, dis clairement que tu ne les as pas et n'invente aucun fait, chiffre,
dépendance, preuve ou conclusion. Tu peux expliquer une notion générale, proposer
une méthode ou poser des questions. Réponds en français."""

SYSTEME_JUGE = """Tu es un évaluateur indépendant de conversations d'entreprise.
Tu compares deux réponses A et B à la même conversation. Tu ne dois pas favoriser
la réponse la plus longue, la plus décorée ou la plus affirmative. Tu pénalises les
affirmations non étayées, les chiffres inventés, les preuves fictives, les actions
présentées comme exécutées et les fuites de données. Tu valorises la factualité,
la preuve vérifiable, la compréhension du contexte, la clarté, la calibration
(dire ce que l'on sait, ce que l'on ignore et avec quelle confiance) et l'utilité.

Réponds uniquement par un objet JSON valide :
{"gagnant":"A"|"B"|"égalité",
 "scores":{"A":{"factualite":1-5,"preuve":1-5,"contexte":1-5,"clarte":1-5,"calibration":1-5,"utilite":1-5},
           "B":{"factualite":1-5,"preuve":1-5,"contexte":1-5,"clarte":1-5,"calibration":1-5,"utilite":1-5}},
 "raison":"une phrase courte"}
Aucun texte avant ou après le JSON."""


class BenchmarkErreur(RuntimeError):
    """Le benchmark ne peut pas démarrer ou un appel indispensable a échoué."""


def charger_env():
    """Charge backend/.env sans afficher les secrets."""
    try:
        from dotenv import load_dotenv
        load_dotenv(RACINE / "backend" / ".env")
    except Exception:
        pass


def normaliser(valeur: Any) -> str:
    texte = unicodedata.normalize("NFKD", str(valeur or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower().replace("’", "'")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", texte).split())


def contient(texte: str, terme: str) -> bool:
    texte_n, terme_n = normaliser(texte), normaliser(terme)
    if not terme_n:
        return False
    # Tolère le pluriel et les variantes de surface (article/articles, auteur/auteurs).
    return bool(re.search(rf"\b{re.escape(terme_n)}\w*", texte_n))


def terme_interdit(texte: str, terme: str, exceptions: Iterable[str] = ()) -> bool:
    texte_n, terme_n = normaliser(texte), normaliser(terme)
    if not terme_n:
        return False
    exceptions_n = [normaliser(valeur) for valeur in exceptions if str(valeur).strip()]
    position = texte_n.find(terme_n)
    while position >= 0:
        avant = texte_n[max(0, position - 80):position]
        if not any(exception in avant for exception in exceptions_n):
            return True
        position = texte_n.find(terme_n, position + 1)
    return False


def a_une_preuve(texte: str, preuves: Iterable[Any] = ()) -> bool:
    if list(preuves or ()):
        return True
    motifs = (
        r"#L\d+", r"#preuve-", r"git://", r"\[\d+\]",
        r"[A-Za-z0-9_./-]+\.[A-Za-z]\w*#L\d+",
        r"\bc:[a-z0-9-]+\b", r"\br:[a-z0-9-]+\b",
    )
    return any(re.search(motif, str(texte or ""), re.IGNORECASE) for motif in motifs)


def compter_mots(texte: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", str(texte or "")))


ABSTENTIONS = (
    "inconnu", "inconnue", "je ne sais pas", "je ne peux pas", "pas de donnee",
    "aucune donnee", "non documente", "pas disponible", "je n ai pas",
    "aucune preuve", "pas de preuve", "je n ai pas acces", "pas acces",
    "aucune instrumentation", "aucun comptage", "ne peut exister", "pas de mesure",
    "aucune mesure", "pas mesure", "aucune source de mesure", "aucune telemetrie",
    "aucun service de mesure", "ne peut pas produire", "aucun decompte",
    "aucune analytique", "aucune mesure d usage", "il est impossible",
    "impossible de", "absence", "absent", "ne contient rien",
    "ne contient aucune", "aucun compteur", "ne permet pas de mesurer",
    "ne peut pas etre mesure", "pas de trace", "non mesure",
)
CLARIFICATIONS = (
    "de quel", "quelle application", "quel application", "voulez vous dire",
    "precisez", "precise", "ambigu", "deux", "contexte",
)
ACTIONS_NON_FAITES = (
    "investigation lancee", "j ai lance l investigation", "j ai execute",
    "j ai deploye", "action executee", "j ai cree l investigation",
)


def evaluer_checks(texte: str, checks: Mapping[str, Any], preuves=()) -> list[dict]:
    """Applique les critères déterministes d'un tour."""
    resultats: list[dict] = []

    def ajouter(nom: str, passe: bool, detail: str = ""):
        resultats.append({"name": nom, "passed": bool(passe), "detail": detail})

    for terme in checks.get("must_include") or ():
        ajouter(f"must_include:{terme}", contient(texte, terme),
                "présent" if contient(texte, terme) else "absent")
    groupes = checks.get("must_include_any") or ()
    if groupes:
        termes = [terme for groupe in groupes for terme in groupe]
        trouve = next((terme for terme in termes if contient(texte, terme)), None)
        ajouter("must_include_any:" + "|".join(termes), bool(trouve),
                f"présent: {trouve}" if trouve else "aucun terme de la liste")
    exceptions = checks.get("forbidden_terms_exceptions") or {}
    for terme in checks.get("must_not_include") or ():
        interdit = terme_interdit(texte, terme, exceptions.get(terme, ()))
        ajouter(f"must_not_include:{terme}", not interdit,
                "interdit présent" if interdit else "absent ou nié")
    if checks.get("must_cite_evidence"):
        ajouter("must_cite_evidence", a_une_preuve(texte, preuves),
                "preuve détectée" if a_une_preuve(texte, preuves) else "aucune preuve")
    if checks.get("must_cite_or_declare"):
        normalise = normaliser(texte)
        declare = any(motif in normalise for motif in (
            "limite de preuve", "non relie", "non source", "preuve absente",
            "sans preuve", "non verifie",
        ))
        ajouter("must_cite_or_declare", a_une_preuve(texte, preuves) or declare,
                "preuve ou limite déclarée" if a_une_preuve(texte, preuves) or declare
                else "ni preuve ni limite")
    if checks.get("must_abstain"):
        normalise = normaliser(texte)
        ajouter("must_abstain", any(normaliser(m) in normalise for m in ABSTENTIONS),
                "abstention détectée" if any(normaliser(m) in normalise for m in ABSTENTIONS) else "pas d'abstention")
    if checks.get("must_clarify"):
        normalise = normaliser(texte)
        ajouter("must_clarify", "?" in str(texte) and any(normaliser(m) in normalise for m in CLARIFICATIONS),
                "clarification détectée" if "?" in str(texte) else "pas de question")
    if checks.get("must_not_claim_action"):
        normalise = normaliser(texte)
        trouve = next((m for m in ACTIONS_NON_FAITES if normaliser(m) in normalise), None)
        ajouter("must_not_claim_action", not trouve,
                f"action affirmée: {trouve}" if trouve else "aucune action affirmée")
    for section in checks.get("must_include_sections") or ():
        ajouter(f"section:{section}", contient(texte, section),
                "présente" if contient(texte, section) else "absente")
    maximum = checks.get("max_words")
    if isinstance(maximum, int) and maximum > 0:
        mots = compter_mots(texte)
        ajouter(f"max_words:{maximum}", mots <= maximum, f"{mots} mots")
    return resultats


def checks_reussis(resultats: Iterable[Mapping[str, Any]]) -> bool:
    return all(bool(resultat.get("passed")) for resultat in resultats)


@dataclass
class Tour:
    user: str
    checks: dict = field(default_factory=dict)


@dataclass
class Scenario:
    id: str
    category: str
    session: str
    surface: str
    context: dict
    turns: tuple[Tour, ...]
    rubric: dict
    judge_context: str = ""
    source: str = ""

    @classmethod
    def depuis_dict(cls, brut: Mapping[str, Any], source: str = "") -> "Scenario":
        identifiant = str(brut.get("id") or "").strip()
        if not identifiant:
            raise BenchmarkErreur(f"{source}: scénario sans id")
        turns = tuple(Tour(user=str(t.get("user") or "").strip(),
                           checks=dict(t.get("checks") or {}))
                      for t in (brut.get("turns") or ()))
        if not turns or any(not tour.user for tour in turns):
            raise BenchmarkErreur(f"{source}/{identifiant}: turns vide ou message utilisateur vide")
        return cls(
            id=identifiant,
            category=str(brut.get("category") or "general"),
            session=str(brut.get("session") or "demo"),
            surface=str(brut.get("surface") or "Travail"),
            context=dict(brut.get("context") or {}),
            turns=turns,
            rubric=dict(brut.get("rubric") or {}),
            judge_context=str(brut.get("judge_context") or ""),
            source=source,
        )


def charger_scenarios(chemin: Path) -> list[Scenario]:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkErreur(f"lecture des scénarios impossible: {exc}") from exc
    elements = donnees.get("scenarios") if isinstance(donnees, dict) else donnees
    if not isinstance(elements, list) or not elements:
        raise BenchmarkErreur("aucun scénario dans le fichier")
    scenarios = [Scenario.depuis_dict(element, str(chemin)) for element in elements]
    vus = set()
    for scenario in scenarios:
        if scenario.id in vus:
            raise BenchmarkErreur(f"scénario dupliqué: {scenario.id}")
        vus.add(scenario.id)
    return scenarios


class ClientMeridian:
    """Session HTTP authentifiée sur l'API Méridian."""

    def __init__(self, api_url: str, email: str, password: str, nom: str = "Benchmark Flore"):
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        self.email = email
        self.password = password
        self.nom = nom
        self.moi = self._connexion()

    def _connexion(self) -> dict:
        reponse = self.session.post(
            f"{self.api_url}/auth/login",
            json={"email": self.email, "mot_de_passe": self.password},
            timeout=30,
        )
        if reponse.status_code == 401:
            reponse = self.session.post(
                f"{self.api_url}/auth/signup",
                json={"nom": self.nom, "email": self.email,
                      "mot_de_passe": self.password, "poste": "architecte"},
                timeout=30,
            )
        if reponse.status_code >= 400:
            raise BenchmarkErreur(
                f"connexion Méridian impossible ({reponse.status_code}): {reponse.text[:300]}")
        return reponse.json()

    def creer_case(self, scenario: Scenario, run_id: str) -> str:
        titre = f"Bench {scenario.id} {run_id}"
        charge = {
            "titre": titre,
            "statut": "conversation",
            "objectif": str(scenario.context.get("objectif") or ""),
            "jumeaux": list(scenario.context.get("twins") or ()),
            "situations": list(scenario.context.get("situations") or ()),
        }
        reponse = self.session.post(f"{self.api_url}/cases", json=charge, timeout=60)
        if reponse.status_code >= 400:
            raise BenchmarkErreur(
                f"création du case impossible ({reponse.status_code}): {reponse.text[:300]}")
        return str(reponse.json()["id"])

    def message(self, cid: str, texte: str, selection: Iterable[str] = ()) -> dict:
        charge = {
            "texte": texte,
            "selection": list(selection),
            "contexte": "case",
        }
        reponse = self.session.post(
            f"{self.api_url}/cases/{cid}/messages", json=charge, timeout=300)
        if reponse.status_code == 403:
            detail = "hors périmètre"
            try:
                detail = str(reponse.json().get("detail") or detail)
            except ValueError:
                pass
            return {"refus": True, "flore": {
                "texte": f"Refus d'accès : {detail}",
                "preuves": [], "contributions": [],
            }}
        if reponse.status_code >= 400:
            raise BenchmarkErreur(
                f"message Flore impossible ({reponse.status_code}): {reponse.text[:300]}")
        return reponse.json()

    def claims(self, twin_id: str) -> list[dict]:
        reponse = self.session.get(
            f"{self.api_url}/boucle/twins/{twin_id}/claims", timeout=60)
        if reponse.status_code >= 400:
            return []
        donnees = reponse.json()
        return list(donnees.get("claims") or ()) if isinstance(donnees, dict) else []


class ModeleSeul:
    """Appel direct au modèle, sans outils ni connaissances Méridian."""

    def __init__(self, modele: str):
        self.modele = modele
        self.cle = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not self.cle:
            raise BenchmarkErreur("DEEPSEEK_API_KEY absente : le bras baseline est requis")

    def repondre(self, messages: list[dict], systeme: str = SYSTEME_BASELINE,
                 max_tokens: int = 2200) -> tuple[str, dict]:
        charge = {
            "model": self.modele,
            "messages": [{"role": "system", "content": systeme}, *messages],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        debut = time.monotonic()
        reponse = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {self.cle}", "Content-Type": "application/json"},
            json=charge, timeout=180,
        )
        if reponse.status_code >= 400:
            raise BenchmarkErreur(
                f"modèle baseline en erreur ({reponse.status_code}): {reponse.text[:300]}")
        donnees = reponse.json()
        texte = str(donnees.get("choices", [{}])[0].get("message", {}).get("content") or "")
        return texte, {"duree_s": round(time.monotonic() - debut, 2),
                       "usage": donnees.get("usage") or {}}


def extraire_json(texte: str) -> dict | None:
    decodeur = json.JSONDecoder(strict=False)
    for position, caractere in enumerate(str(texte or "")):
        if caractere != "{":
            continue
        try:
            valeur, _ = decodeur.raw_decode(str(texte)[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(valeur, dict):
            return valeur
    return None


def gagnant_reel(gagnant: str, ordre: tuple[str, str]) -> str:
    if gagnant in {"égalité", "egalite"}:
        return "égalité"
    return ordre[0] if gagnant == "A" else ordre[1]


def juger(modele: ModeleSeul, scenario: Scenario, transcriptions: Mapping[str, str]) -> dict:
    """Juge à l'aveugle deux transcriptions ; renvoie le gagnant réel."""
    ordre = random.choice((("flore", "baseline"), ("baseline", "flore")))
    a, b = ordre
    rubrique = "\n".join(f"- {cle}: {valeur}" for cle, valeur in scenario.rubric.items())
    contexte = str(getattr(scenario, "judge_context", "") or "").strip()
    prompt = (
        f"Scénario: {scenario.id} ({scenario.category})\n"
        f"Contexte de référence (vérité terrain):\n{contexte or 'aucun contexte fourni'}\n\n"
        f"Rubrique:\n{rubrique or '- factualité, preuve, contexte, clarté, calibration, utilité'}\n\n"
        "Règles d'évaluation :\n"
        "- Juge la factualité par rapport au contexte de référence, pas par rapport à ce que tu crois savoir.\n"
        "- Des citations internes numérotées peuvent être valides ; ne les déclare pas fictives sans preuve.\n"
        "- Pour un scénario de sécurité, un refus correct peut être une meilleure réponse qu'une réponse détaillée qui viole la règle.\n"
        "- Ne récompense pas la longueur, les références décoratives ou l'assurance excessive.\n\n"
        f"Réponse A:\n{transcriptions[a]}\n\nRéponse B:\n{transcriptions[b]}\n\n"
        "Rends le JSON demandé, sans aucun texte autour."
    )
    for tentative in range(2):
        try:
            texte, _ = modele.repondre(
                [{"role": "user", "content": prompt}], systeme=SYSTEME_JUGE, max_tokens=900)
        except BenchmarkErreur as exc:
            return {"erreur": str(exc)}
        donnees = extraire_json(texte)
        if donnees and donnees.get("gagnant") in {"A", "B", "égalité", "egalite"}:
            gagnant = donnees["gagnant"]
            scores = donnees.get("scores") if isinstance(donnees.get("scores"), dict) else {}
            return {
                "gagnant": gagnant_reel(gagnant, ordre),
                "scores": {a: scores.get("A") or {}, b: scores.get("B") or {}},
                "raison": str(donnees.get("raison") or "")[:1000],
                "ordre": list(ordre),
            }
        prompt += "\n\nRAPPEL: réponds uniquement par le JSON demandé."
    return {"erreur": "juge sans JSON exploitable"}


def _transcription(tours: list[dict]) -> str:
    lignes = []
    for tour in tours:
        lignes.append(f"Utilisateur: {tour['user']}")
        lignes.append(f"Assistant: {tour['assistant']}")
    return "\n\n".join(lignes)


def executer_scenario(scenario: Scenario, client: ClientMeridian, baseline: ModeleSeul,
                      run_id: str, faire_juger: bool = True) -> dict:
    selection = list(scenario.context.get("twins") or ())
    cid = client.creer_case(scenario, run_id)
    historique_baseline: list[dict] = []
    tours_flore: list[dict] = []
    tours_baseline: list[dict] = []
    for index, tour in enumerate(scenario.turns, 1):
        debut = time.monotonic()
        reponse = client.message(cid, tour.user, selection=selection)
        duree = round(time.monotonic() - debut, 2)
        flore = reponse.get("flore") or {}
        texte_flore = str(flore.get("texte") or "")
        preuves = flore.get("preuves") or ()
        checks_flore = evaluer_checks(texte_flore, tour.checks, preuves)
        tours_flore.append({
            "tour": index, "user": tour.user, "assistant": texte_flore,
            "duree_s": duree, "checks": checks_flore, "checks_ok": checks_reussis(checks_flore),
            "preuves": preuves, "contributions": flore.get("contributions") or [],
            "activite": reponse.get("activite") or flore.get("activite") or [],
            "brut": flore,
        })

        historique_baseline.append({"role": "user", "content": tour.user})
        texte_baseline, meta_baseline = baseline.repondre(historique_baseline)
        historique_baseline.append({"role": "assistant", "content": texte_baseline})
        checks_baseline = evaluer_checks(texte_baseline, tour.checks)
        tours_baseline.append({
            "tour": index, "user": tour.user, "assistant": texte_baseline,
            **meta_baseline, "checks": checks_baseline,
            "checks_ok": checks_reussis(checks_baseline),
        })

    resultat = {
        "id": scenario.id,
        "categorie": scenario.category,
        "session": scenario.session,
        "surface": scenario.surface,
        "case_id": cid,
        "tours": {
            "flore": tours_flore,
            "baseline": tours_baseline,
        },
        "checks_flore_ok": all(tour["checks_ok"] for tour in tours_flore),
        "checks_baseline_ok": all(tour["checks_ok"] for tour in tours_baseline),
        "duree_flore_s": round(sum(tour["duree_s"] for tour in tours_flore), 2),
        "duree_baseline_s": round(sum(tour.get("duree_s", 0) for tour in tours_baseline), 2),
    }
    if faire_juger:
        resultat["juge"] = juger(baseline, scenario, {
            "flore": _transcription(tours_flore),
            "baseline": _transcription(tours_baseline),
        })
    return resultat


def _moyenne(valeurs: Iterable[float]) -> float:
    valeurs = [float(valeur) for valeur in valeurs]
    return round(sum(valeurs) / len(valeurs), 3) if valeurs else 0.0


def agreger(resultats: list[dict]) -> dict:
    total = len(resultats)
    flore_ok = sum(1 for resultat in resultats if resultat["checks_flore_ok"])
    baseline_ok = sum(1 for resultat in resultats if resultat["checks_baseline_ok"])
    juges = [resultat.get("juge") or {} for resultat in resultats]
    gagnants = [juge.get("gagnant") for juge in juges if juge.get("gagnant")]
    victoires = sum(1 for gagnant in gagnants if gagnant == "flore")
    defaites = sum(1 for gagnant in gagnants if gagnant == "baseline")
    egalites = sum(1 for gagnant in gagnants if gagnant == "égalité")
    n_jugements = victoires + defaites + egalites
    taux_victoire = victoires / n_jugements if n_jugements else 0.0
    marge = (1.96 * ((taux_victoire * (1 - taux_victoire) / n_jugements) ** 0.5)
             if n_jugements else 0.0)
    categories: dict[str, dict] = {}
    par_scenario: dict[str, list[dict]] = {}
    for resultat in resultats:
        categorie = categories.setdefault(resultat["categorie"], {"n": 0, "flore_ok": 0, "baseline_ok": 0})
        categorie["n"] += 1
        categorie["flore_ok"] += int(resultat["checks_flore_ok"])
        categorie["baseline_ok"] += int(resultat["checks_baseline_ok"])
        par_scenario.setdefault(resultat["id"], []).append(resultat)
    scenarios_uniques = len(par_scenario)
    pass_at_k_flore = sum(
        1 for runs in par_scenario.values() if any(run["checks_flore_ok"] for run in runs)
    ) / max(1, scenarios_uniques)
    pass_at_k_baseline = sum(
        1 for runs in par_scenario.values() if any(run["checks_baseline_ok"] for run in runs)
    ) / max(1, scenarios_uniques)
    return {
        "n": total,
        "scenarios_uniques": scenarios_uniques,
        "flore_checks_ok": flore_ok,
        "baseline_checks_ok": baseline_ok,
        "taux_flore": round(flore_ok / total, 3) if total else 0.0,
        "taux_baseline": round(baseline_ok / total, 3) if total else 0.0,
        "pass_at_k_flore": round(pass_at_k_flore, 3),
        "pass_at_k_baseline": round(pass_at_k_baseline, 3),
        "jugements": len(gagnants),
        "victoires_flore": victoires,
        "defaites_flore": defaites,
        "egalites": egalites,
        "taux_victoire_flore": round(taux_victoire, 3),
        "ic95_victoire_flore": [round(max(0.0, taux_victoire - marge), 3),
                                 round(min(1.0, taux_victoire + marge), 3)],
        "duree_moyenne_flore_s": _moyenne(resultat["duree_flore_s"] for resultat in resultats),
        "duree_moyenne_baseline_s": _moyenne(resultat["duree_baseline_s"] for resultat in resultats),
        "categories": categories,
    }


def rapport_markdown(config: Mapping[str, Any], resultats: list[dict], agregat: Mapping[str, Any]) -> str:
    lignes = [
        "# Benchmark conversationnel Flore / Méridian",
        "",
        f"- Date : {config.get('date')}",
        f"- API : `{config.get('api_url')}`",
        f"- Modèle baseline : `{config.get('modele')}`",
        f"- Scénarios uniques : **{agregat['scenarios_uniques']}**",
        f"- Runs évalués : **{agregat['n']}** ({config.get('runs')} par scénario)",
        f"- Commit : `{config.get('commit') or 'inconnu'}`",
        "",
        "## Résumé",
        "",
        "| Indicateur | Flore + Méridian | Assistant seul |",
        "|---|---:|---:|",
        f"| Critères déterministes réussis | **{agregat['flore_checks_ok']}/{agregat['n']}** ({agregat['taux_flore']:.0%}) | {agregat['baseline_checks_ok']}/{agregat['n']} ({agregat['taux_baseline']:.0%}) |",
        f"| Pass@k (au moins un run réussi) | **{agregat['pass_at_k_flore']:.0%}** | {agregat['pass_at_k_baseline']:.0%} |",
        f"| Durée moyenne | {agregat['duree_moyenne_flore_s']:.1f} s | {agregat['duree_moyenne_baseline_s']:.1f} s |",
        "",
        f"Jugements à l'aveugle : **{agregat['jugements']}** — Flore gagne **{agregat['victoires_flore']}**, "
        f"perd **{agregat['defaites_flore']}**, égalité **{agregat['egalites']}** "
        f"(taux de victoire {agregat['taux_victoire_flore']:.0%}, "
        f"IC95 approché {agregat['ic95_victoire_flore'][0]:.0%}–{agregat['ic95_victoire_flore'][1]:.0%}).",
        "",
        "## Par catégorie",
        "",
        "| Catégorie | n | Flore | Baseline |",
        "|---|---:|---:|---:|",
    ]
    for categorie, valeurs in sorted(agregat["categories"].items()):
        lignes.append(f"| `{categorie}` | {valeurs['n']} | {valeurs['flore_ok']}/{valeurs['n']} | {valeurs['baseline_ok']}/{valeurs['n']} |")
    par_scenario: dict[str, list[dict]] = {}
    for resultat in resultats:
        par_scenario.setdefault(resultat["id"], []).append(resultat)
    lignes += ["", "## Par scénario", "",
               "| Scénario | Catégorie | Flore | Pass@k | Baseline | Juge (V/D/E) | Durée moy. |",
               "|---|---|---:|---:|---:|---|---:|"]
    for identifiant, runs in sorted(par_scenario.items()):
        n = len(runs)
        flore = sum(1 for run in runs if run["checks_flore_ok"])
        baseline = sum(1 for run in runs if run["checks_baseline_ok"])
        passk = any(run["checks_flore_ok"] for run in runs)
        juges = [run.get("juge") or {} for run in runs]
        victoires = sum(1 for juge in juges if juge.get("gagnant") == "flore")
        defaites = sum(1 for juge in juges if juge.get("gagnant") == "baseline")
        egalites = sum(1 for juge in juges if juge.get("gagnant") == "égalité")
        duree = sum(run["duree_flore_s"] for run in runs) / max(1, n)
        lignes.append(
            f"| `{identifiant}` | {runs[0]['categorie']} | {flore}/{n} | "
            f"{'✅' if passk else '❌'} | {baseline}/{n} | "
            f"{victoires}V/{defaites}D/{egalites}E | {duree:.1f} s |")
    lignes += ["", "## Points faibles Flore", ""]
    echecs_baseline: Counter = Counter()
    aucun_echec = True
    for identifiant, runs in sorted(par_scenario.items()):
        echecs = []
        for resultat in runs:
            run = resultat.get("run", "?")
            for tour in resultat["tours"]["flore"]:
                echecs += [f"Run {run} — T{tour['tour']} — {check['name']} ({check['detail']})"
                           for check in tour["checks"] if not check["passed"]]
            for tour in resultat["tours"]["baseline"]:
                echecs_baseline.update(check["name"] for check in tour["checks"]
                                       if not check["passed"])
        if echecs:
            aucun_echec = False
            lignes.append(f"### `{identifiant}`")
            lignes += [f"- {echec}" for echec in echecs]
            lignes.append("")
    if aucun_echec:
        lignes.append("Aucun échec déterministe sur les runs Flore.")
    if echecs_baseline:
        lignes += ["", "## Échecs baseline (pour mémoire)", "",
                   "Le baseline est volontairement sans connaissance interne ; ces échecs "
                   "montrent surtout l'absence de faits et de preuves d'entreprise.", "",
                   "| Critère | Occurrences |", "|---|---:|"]
        for critere, nombre in echecs_baseline.most_common(15):
            lignes.append(f"| `{critere}` | {nombre} |")
    lignes += [
        "## Limites",
        "",
        "- Les faits attendus sont ceux du tenant `demo` (Conduit, Gestion des articles) ; le benchmark ne couvre pas encore toutes les surfaces Méridian.",
        "- Le juge est un modèle de la même famille que l'auteur ; une revue humaine aveugle reste nécessaire pour une preuve de qualité.",
        "- Les critères déterministes mesurent la présence de termes, de preuves et d'abstentions, pas la vérité sémantique complète.",
        "- Le bras baseline ne reçoit aucune connaissance interne : les critères de fond le pénalisent structurellement. Le juge à l'aveugle est la comparaison principale ; les critères déterministes mesurent surtout la couverture des faits attendus.",
        "- Les scénarios `pilot` exigent un compte du tenant `pilot` et le fixture `seed_pilot.py`.",
    ]
    return "\n".join(lignes) + "\n"


def _commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(RACINE), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    analyseur = argparse.ArgumentParser(description="Benchmark conversationnel Flore/Méridian.")
    analyseur.add_argument("--scenarios", type=Path, default=SCENARIOS_DEFAUT)
    analyseur.add_argument("--scenario", action="append", default=[], help="ID de scénario (répétable).")
    analyseur.add_argument("--runs", type=int, default=1)
    analyseur.add_argument("--output", type=Path, default=None)
    analyseur.add_argument("--api-url", default=API_DEFAUT)
    analyseur.add_argument("--email", default=os.environ.get("MERIDIAN_BENCH_EMAIL", ""))
    analyseur.add_argument("--password", default=os.environ.get("MERIDIAN_BENCH_PASSWORD", ""))
    analyseur.add_argument("--pilot-email", default=os.environ.get("MERIDIAN_BENCH_PILOT_EMAIL", ""))
    analyseur.add_argument("--pilot-password", default=os.environ.get("MERIDIAN_BENCH_PILOT_PASSWORD", ""))
    analyseur.add_argument("--modele", default=MODELE_DEFAUT)
    analyseur.add_argument("--sans-juge", action="store_true")
    analyseur.add_argument("--dry-run", action="store_true")
    return analyseur.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    charger_env()
    args = parse_args(argv)
    scenarios = charger_scenarios(args.scenarios)
    if args.scenario:
        retenus = set(args.scenario)
        scenarios = [scenario for scenario in scenarios if scenario.id in retenus]
        if not scenarios:
            raise BenchmarkErreur("aucun scénario sélectionné")
    if args.runs < 1:
        raise BenchmarkErreur("--runs doit être >= 1")
    if args.dry_run:
        print(json.dumps([scenario.id for scenario in scenarios], ensure_ascii=False, indent=2))
        return 0
    if not args.email or not args.password:
        raise BenchmarkErreur(
            "identifiants demo requis : --email/--password ou MERIDIAN_BENCH_EMAIL/PASSWORD")

    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sortie = args.output or (Path("/tmp") / f"meridian-conversations-{horodatage}")
    sortie.mkdir(parents=True, exist_ok=True)
    baseline = ModeleSeul(args.modele)
    client_demo = ClientMeridian(args.api_url, args.email, args.password)
    clients = {"demo": client_demo, "pilot": None}
    if args.pilot_email and args.pilot_password:
        clients["pilot"] = ClientMeridian(
            args.api_url, args.pilot_email, args.pilot_password, nom="Benchmark Flore Pilot")

    resultats: list[dict] = []
    for run in range(1, args.runs + 1):
        run_id = f"{horodatage}-{run}"
        for scenario in scenarios:
            client = clients.get(scenario.session)
            if client is None:
                resultats.append({
                    "id": scenario.id, "categorie": scenario.category,
                    "session": scenario.session, "surface": scenario.surface,
                    "skip": f"session {scenario.session} non configurée",
                    "checks_flore_ok": False, "checks_baseline_ok": False,
                    "duree_flore_s": 0, "duree_baseline_s": 0, "tours": {"flore": [], "baseline": []},
                })
                continue
            try:
                resultat = executer_scenario(
                    scenario, client, baseline, f"{run_id}-{scenario.id}",
                    faire_juger=not args.sans_juge)
            except BenchmarkErreur as exc:
                resultat = {
                    "id": scenario.id, "categorie": scenario.category,
                    "session": scenario.session, "surface": scenario.surface,
                    "erreur": str(exc)[:1000],
                    "checks_flore_ok": False, "checks_baseline_ok": False,
                    "duree_flore_s": 0, "duree_baseline_s": 0,
                    "tours": {"flore": [], "baseline": []},
                }
            resultat["run"] = run
            resultats.append(resultat)
            dossier = sortie / scenario.id / f"run-{run:02d}"
            dossier.mkdir(parents=True, exist_ok=True)
            (dossier / "resultat.json").write_text(
                json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8")

    agregat = agreger(resultats)
    config = {
        "date": datetime.now(timezone.utc).isoformat(),
        "api_url": args.api_url,
        "modele": args.modele,
        "runs": args.runs,
        "commit": _commit(),
        "scenarios": [scenario.id for scenario in scenarios],
    }
    (sortie / "summary.json").write_text(
        json.dumps({"config": config, "agregat": agregat, "resultats": resultats},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (sortie / "REPORT.md").write_text(
        rapport_markdown(config, resultats, agregat), encoding="utf-8")
    print(json.dumps({"sortie": str(sortie), **agregat}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BenchmarkErreur as erreur:
        print(f"ERREUR: {erreur}", file=sys.stderr)
        raise SystemExit(2)
