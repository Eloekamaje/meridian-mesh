import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowsClockwise,
  ArrowUpRight,
  BookOpen,
  ChartLineUp,
  CircleNotch,
  Compass,
  Lightbulb,
  MagnifyingGlass,
  RocketLaunch,
  Scales,
  WarningCircle,
  X,
} from "@phosphor-icons/react";
import api from "@/lib/api";
import Depliable from "@/components/ui/Depliable";
import IdentifiantCopiable from "@/components/ui/IdentifiantCopiable";

const STADES = [
  { type: "SITUATION", famille: "emergence", label: "Situations", court: "Situation", couleur: "#60A5FA", Icone: Lightbulb },
  { type: "INVESTIGATION", famille: "investigation", label: "Investigations", court: "Investigation", couleur: "#38BDF8", Icone: MagnifyingGlass },
  { type: "DECISION", famille: "decision", label: "Décisions", court: "Décision", couleur: "#F2B84B", Icone: Scales },
  { type: "INITIATIVE", famille: "decision", label: "Initiatives", court: "Initiative", couleur: "#FB923C", Icone: RocketLaunch },
  { type: "OUTCOME", famille: "resultat_apprentissage", label: "Outcomes", court: "Outcome", couleur: "#34D399", Icone: ChartLineUp },
  { type: "LEARNING", famille: "resultat_apprentissage", label: "Learnings", court: "Learning", couleur: "#A78BFA", Icone: BookOpen },
];

const STADES_PAR_TYPE = new Map(STADES.map((stade) => [stade.type, stade]));

const FAMILLES = [
  { value: "emergence", label: "Émergence — situations" },
  { value: "investigation", label: "Investigation" },
  { value: "decision", label: "Décision — décisions et initiatives" },
  { value: "resultat_apprentissage", label: "Résultat — outcomes et learnings" },
];

const FAMILLES_LABEL = new Map([
  ["emergence", "Émergence"],
  ["investigation", "Investigation"],
  ["decision", "Décision"],
  ["resultat_apprentissage", "Résultat & apprentissage"],
  ["identite_structure", "Identité & structure"],
  ["sources_preuves", "Sources & preuves"],
  ["connaissance", "Connaissance"],
  ["interaction_gouvernance", "Interaction & gouvernance"],
]);

const MODES = [
  ["DECLARED", "Déclaré"],
  ["OBSERVED", "Observé"],
  ["INFERRED", "Inféré"],
  ["PROPOSED", "Proposé"],
  ["CONFIRMED", "Confirmé"],
];

const MODES_LABEL = new Map(MODES);

const OUTCOME_INITIAL = {
  initiative_id: "",
  metrique: "",
  valeur: "",
  unite: "",
  cible: "",
  preuves: "",
  enseignement: "",
};

const TYPES_TWIN = [
  ["PROCESS", "Processus"],
  ["CAPABILITY", "Capacité"],
  ["JOURNEY", "Parcours"],
  ["ORGANIZATION", "Organisation"],
  ["PRODUCT", "Produit"],
  ["DATA_DOMAIN", "Domaine de données"],
];

const LABELS_TWIN = new Map(TYPES_TWIN);

const TWIN_INITIAL = {
  id: "",
  type: "PROCESS",
  nom: "",
  mission: "",
  domaine: "",
  equipe: "à confirmer",
};

const CONTENEURS_COMPTES = [
  "comptes", "par_type", "types", "parType", "par_famille", "familles",
  "synthese", "totaux", "totals", "donnees",
];

const texte = (valeur) => (valeur == null ? "" : String(valeur));

const sansAccents = (valeur) =>
  texte(valeur).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

function valeurDe(objet, ...cles) {
  for (const cle of cles) {
    const directe = objet?.[cle];
    if (directe !== undefined && directe !== null && directe !== "") return directe;
    const donnee = objet?.donnees?.[cle];
    if (donnee !== undefined && donnee !== null && donnee !== "") return donnee;
  }
  return null;
}

function idDeValeur(valeur) {
  if (valeur == null) return null;
  if (typeof valeur === "object") {
    const identifiant = valeur.id ?? valeur._id;
    return identifiant == null ? null : texte(identifiant);
  }
  return texte(valeur) || null;
}

function idObjet(objet) {
  if (typeof objet === "string") return objet;
  return idDeValeur(objet?.id ?? objet?._id);
}

function typeObjet(objet) {
  return texte(valeurDe(objet, "type")).trim().toUpperCase();
}

function familleObjet(objet) {
  return texte(valeurDe(objet, "famille")).trim().toLowerCase();
}

function titreObjet(objet) {
  if (typeof objet === "string") return objet;
  return texteAffichable(valeurDe(objet, "titre")) || idObjet(objet) || "Objet sans titre";
}

function resumeObjet(objet) {
  return texteAffichable(valeurDe(
    objet,
    "resume", "description", "question", "enonce", "interpretation", "rationale", "choix",
  ));
}

function dateLisible(valeur) {
  if (!valeur) return null;
  const date = new Date(valeur);
  if (Number.isNaN(date.getTime())) return texte(valeur);
  return date.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
}

function texteAffichable(valeur) {
  if (valeur == null) return "";
  if (Array.isArray(valeur)) {
    return valeur
      .filter((element) => element == null || typeof element !== "object")
      .map((element) => texte(element))
      .filter(Boolean)
      .join(", ");
  }
  if (typeof valeur === "object") return "";
  return texte(valeur);
}

function messageErreur(erreur, defaut = "La boucle est momentanément indisponible.") {
  const detail = erreur?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return defaut;
}

function idTravail(objet) {
  const direct = valeurDe(
    objet,
    "travail_id", "case_id", "work_id", "travailId", "caseId", "lien_travail",
    "travail", "case", "dossier", "work",
  );
  const lien = idDeValeur(direct);
  if (lien) return lien;
  const liens = objet?.liens || objet?.donnees?.liens || {};
  return idDeValeur(liens.travail) || idDeValeur(liens.case) || idDeValeur(liens.work) || null;
}

function idsAtlas(objet) {
  const brut = valeurDe(objet, "twin_ids", "twin_id", "jumeaux", "jumeau_ids")
    || objet?.donnees?.liens?.jumeaux
    || objet?.donnees?.liens?.twin_ids;
  const liste = Array.isArray(brut) ? brut : [brut];
  return [...new Set(liste.map(idDeValeur).filter(Boolean))];
}

function listeValeurs(objet, ...cles) {
  const brut = valeurDe(objet, ...cles);
  const liste = Array.isArray(brut) ? brut : [brut];
  return liste.filter((valeur) => valeur !== undefined && valeur !== null && valeur !== "");
}

function listeIdentifiants(objet, ...cles) {
  return [...new Set(listeValeurs(objet, ...cles).map(idDeValeur).filter(Boolean))];
}

function trouverNombre(source, cles, profondeur = 0) {
  if (!source || typeof source !== "object" || Array.isArray(source) || profondeur > 3) return null;
  const clesReelles = Object.keys(source);
  const normalisees = new Map(
    clesReelles.map((cle) => [sansAccents(cle).replace(/[^a-z0-9]/g, ""), cle]),
  );
  for (const cle of cles) {
    const candidats = [cle, texte(cle).toLowerCase(), sansAccents(cle).replace(/[^a-z0-9]/g, "")];
    for (const candidat of candidats) {
      const reelle = clesReelles.includes(candidat) ? candidat : normalisees.get(candidat);
      if (reelle === undefined) continue;
      const valeur = source[reelle];
      if (valeur === null || valeur === "" || typeof valeur === "object") continue;
      const nombre = Number(valeur);
      if (Number.isFinite(nombre)) return nombre;
    }
  }
  for (const conteneur of CONTENEURS_COMPTES) {
    const valeur = source[conteneur];
    if (valeur && typeof valeur === "object" && !Array.isArray(valeur)) {
      const nombre = trouverNombre(valeur, cles, profondeur + 1);
      if (nombre !== null) return nombre;
    }
  }
  return null;
}

function compteSynthese(synthese, stade) {
  return trouverNombre(synthese, [
    stade.type, stade.type.toLowerCase(), stade.label, stade.label.toLowerCase(),
    stade.court, stade.court.toLowerCase(),
  ]);
}

function totalSynthese(synthese) {
  return trouverNombre(synthese, ["total", "nb_objets", "nombre_objets", "total_objets", "compte_total"]);
}

function CarteObjet({ objet, stade, actif, onOuvrir }) {
  const mode = texte(valeurDe(objet, "mode")).toUpperCase();
  const version = valeurDe(objet, "version");
  const date = dateLisible(valeurDe(objet, "maj_le", "observe_le", "cree_le"));
  const resume = resumeObjet(objet);

  return (
    <button
      type="button"
      onClick={() => onOuvrir(objet)}
      data-testid="boucle-objet"
      data-objet-id={idObjet(objet) || undefined}
      className={`group w-full rounded-xl border px-3.5 py-3 text-left transition-colors ${
        actif
          ? "border-[#60A5FA]/60 bg-[#0F1D28] ring-1 ring-[#60A5FA]/20"
          : "border-[rgba(148,163,184,0.16)] bg-[#0B1620] hover:border-[#41576D] hover:bg-[#0F1D28]"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span
          className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full"
          style={{ backgroundColor: stade.couleur }}
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-code text-[10px] uppercase tracking-[0.18em]" style={{ color: stade.couleur }}>
              {stade.court}
            </span>
            {mode && (
              <span className="rounded border border-[rgba(148,163,184,0.18)] px-1.5 py-px font-code text-[10px] text-[#94A3B8]">
                {MODES_LABEL.get(mode) || mode}
              </span>
            )}
            {version != null && (
              <span className="font-code text-[10px] text-[#7C93A8]">v{texte(version)}</span>
            )}
          </div>
          <h3 className="mt-1 line-clamp-2 text-sm font-semibold leading-snug text-[#F2F6F8]">
            {titreObjet(objet)}
          </h3>
          {resume && (
            <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-[#94A3B8]">{resume}</p>
          )}
          <div className="mt-2 flex items-center justify-between gap-2 font-code text-[10px] text-[#7C93A8]">
            <span className="truncate">{FAMILLES_LABEL.get(familleObjet(objet)) || familleObjet(objet) || "Famille inconnue"}</span>
            {date && <span className="shrink-0">{date}</span>}
          </div>
        </div>
      </div>
    </button>
  );
}

function EtapeChaine({ etape, index, dernier }) {
  const stade = STADES_PAR_TYPE.get(typeObjet(etape));
  return (
    <li className="relative flex gap-3 pb-3 last:pb-0" data-testid="boucle-chaine-etape">
      <div className="relative flex w-4 shrink-0 justify-center">
        <span
          className="mt-1 h-2 w-2 rounded-full"
          style={{ backgroundColor: stade?.couleur || "#7C93A8" }}
          aria-hidden="true"
        />
        {!dernier && <span className="absolute bottom-0 top-3 w-px bg-[rgba(148,163,184,0.18)]" />}
      </div>
      <div className="min-w-0">
        <div className="font-code text-[10px] uppercase tracking-[0.18em] text-[#7C93A8]">
          {stade?.court || typeObjet(etape) || `Étape ${index + 1}`}
        </div>
        <div className="mt-0.5 text-xs leading-relaxed text-[#D8E2EA]">{titreObjet(etape)}</div>
      </div>
    </li>
  );
}

function PanneauDetail({ objet, etat, chaine, historique, onFermer, onReessayer, onNaviguer, onOuvrirId }) {
  if (!objet) return null;

  const stade = STADES_PAR_TYPE.get(typeObjet(objet));
  const identifiant = idObjet(objet);
  const amont = chaine.filter((etape) => idObjet(etape) !== identifiant);
  const travail = idTravail(objet);
  const atlas = idsAtlas(objet);
  const preuves = listeValeurs(objet, "preuves", "preuve_ids", "preuve_id");
  const claims = listeIdentifiants(objet, "claim_ids", "claims", "claim_id");
  const outcomes = listeIdentifiants(objet, "outcome_ids", "outcome_id");
  const mode = texte(valeurDe(objet, "mode")).toUpperCase();
  const resume = resumeObjet(objet);
  const resumeChaine = etat.chargement
    ? "Chargement du contexte…"
    : etat.erreur
      ? "Contexte indisponible · afficher"
      : amont.length > 0
        ? `${amont.length} étape(s) de contexte · afficher`
        : "Aucune chaîne amont · afficher";
  const precisions = [
    ["Statut", texteAffichable(valeurDe(objet, "statut"))],
    ["Choix", texteAffichable(valeurDe(objet, "choix"))],
    ["Acteur", texteAffichable(valeurDe(objet, "acteur"))],
    ["Métrique", texteAffichable(valeurDe(objet, "metrique"))],
    ["Valeur observée", texteAffichable(valeurDe(objet, "valeur_observee"))],
    ["Valeur attendue", texteAffichable(valeurDe(objet, "valeur_attendue"))],
    ["Période", texteAffichable(valeurDe(objet, "periode"))],
    ["Propriétaire", texteAffichable(valeurDe(objet, "proprietaire"))],
  ].filter(([, contenu]) => contenu);

  return (
    <div className="fixed inset-0 z-50 flex justify-end" data-testid="boucle-detail">
      <button
        type="button"
        aria-label="Fermer le détail"
        onClick={onFermer}
        data-testid="boucle-detail-fond"
        className="absolute inset-0 bg-black/55 backdrop-blur-[2px]"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Détail de ${titreObjet(objet)}`}
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto border-l border-[rgba(148,163,184,0.18)] bg-[#091420] px-5 py-5 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em]">
              {stade && <span style={{ color: stade.couleur }}>{stade.label}</span>}
              {!stade && <span className="text-[#94A3B8]">{typeObjet(objet) || "Objet"}</span>}
              {mode && <span className="rounded border border-[rgba(148,163,184,0.2)] px-1.5 py-px text-[#94A3B8]">{MODES_LABEL.get(mode) || mode}</span>}
            </div>
            <h2 className="mt-2 font-display text-lg font-black leading-tight text-[#F2F6F8]" data-testid="boucle-detail-titre">
              {titreObjet(objet)}
            </h2>
            <p className="mt-1 font-code text-[10px] text-[#7C93A8]">
              {FAMILLES_LABEL.get(familleObjet(objet)) || familleObjet(objet) || "Famille inconnue"}
              {identifiant ? ` · ${identifiant}` : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onFermer}
            data-testid="boucle-detail-fermer"
            title="Fermer le détail"
            aria-label="Fermer le détail"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[rgba(148,163,184,0.18)] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
          >
            <X size={15} />
          </button>
        </div>

        {resume && <p className="mt-4 text-sm leading-relaxed text-[#CBD5E1]">{resume}</p>}

        <div className="mt-5 flex flex-wrap gap-2">
          {travail && (
            <button
              type="button"
              onClick={() => onNaviguer(`/travaux/${encodeURIComponent(travail)}`)}
              data-testid="boucle-lien-travail"
              className="flex items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 py-1.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD]"
            >
              Ouvrir le travail <ArrowUpRight size={12} />
            </button>
          )}
          {atlas.length > 0 && (
            <button
              type="button"
              onClick={() => onNaviguer(`/atlas?focus=${encodeURIComponent(atlas[0])}`)}
              data-testid="boucle-lien-atlas"
              className="flex items-center gap-1.5 rounded-md border border-[#60A5FA]/40 bg-[#60A5FA]/[0.06] px-3 py-1.5 text-[11px] font-semibold text-[#BFDBFE] transition-colors hover:bg-[#60A5FA]/12"
            >
              <Compass size={12} /> Voir dans l'Atlas
            </button>
          )}
        </div>

        {(preuves.length > 0 || claims.length > 0 || outcomes.length > 0) && (
          <Depliable
            id="boucle-liens"
            testid="boucle-liens"
            className="mt-5"
            titre="Preuves et liens"
            resume={`${preuves.length + claims.length + outcomes.length} identifiant(s) lié(s) · afficher`}
          >
            <p className="mb-2 text-[11px] leading-relaxed text-[#7C93A8]">
              Les claims et les preuves n'ont pas de page dédiée : leur identifiant est sélectionnable et copiable.
              Les outcomes ouvrent leur détail.
            </p>

            {preuves.length > 0 && (
              <div>
                <h4 className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Preuves</h4>
                <ul className="mt-1 flex flex-wrap gap-1.5" data-testid="boucle-preuves">
                  {preuves.map((preuve, index) => {
                    const identifiantPreuve = idDeValeur(preuve);
                    const libelle = typeof preuve === "object"
                      ? texteAffichable(preuve.source)
                        || texteAffichable(preuve.detail)
                        || texteAffichable(preuve.locator)
                      : "";
                    return (
                      <li
                        key={`${identifiantPreuve || libelle || "preuve"}-${index}`}
                        data-testid="boucle-preuve"
                        className="flex max-w-full flex-wrap items-center gap-1.5"
                      >
                        {libelle && <span className="min-w-0 truncate font-code text-[10px] text-[#BFDBFE]">{libelle}</span>}
                        {identifiantPreuve ? (
                          <IdentifiantCopiable
                            identifiant={identifiantPreuve}
                            libelle="Preuve"
                            testid={`boucle-preuve-${index}`}
                          />
                        ) : (
                          !libelle && <span className="font-code text-[10px] text-[#94A3B8]">Preuve {index + 1}</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}

            {claims.length > 0 && (
              <div className="mt-2">
                <h4 className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Claims liés</h4>
                <ul className="mt-1 flex flex-wrap gap-1.5" data-testid="boucle-claims">
                  {claims.map((claim) => (
                    <li key={claim} data-testid="boucle-claim" className="max-w-full">
                      <IdentifiantCopiable
                        identifiant={claim}
                        libelle="Claim"
                        testid={`boucle-claim-${claim}`}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {outcomes.length > 0 && (
              <div className="mt-2">
                <h4 className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Outcomes liés</h4>
                <ul className="mt-1 flex flex-wrap gap-1.5" data-testid="boucle-outcomes">
                  {outcomes.map((outcomeId) => (
                    <li key={outcomeId}>
                      <button
                        type="button"
                        onClick={() => onOuvrirId(outcomeId)}
                        title={`Ouvrir le détail de l'outcome ${outcomeId}`}
                        data-testid={`boucle-outcome-lien-${outcomeId}`}
                        className="flex max-w-full items-center gap-1 rounded border border-[#34D399]/35 bg-[#34D399]/[0.06] px-1.5 py-0.5 font-code text-[10px] text-[#6EE7B7] transition-colors hover:bg-[#34D399]/12"
                      >
                        <span className="truncate">{outcomeId}</span> <ArrowUpRight size={10} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Depliable>
        )}

        <Depliable
          id="boucle-chaine-section"
          testid="boucle-chaine-section"
          className="mt-6"
          titre="Chaîne amont"
          resume={resumeChaine}
        >
          {etat.chargement && (
            <p className="flex items-center gap-2 text-xs text-[#7C93A8]" data-testid="boucle-detail-chargement">
              <CircleNotch size={14} className="animate-spin" /> Chargement du détail…
            </p>
          )}
          {!etat.chargement && etat.erreur && (
            <div className="rounded-lg border border-[#F87171]/30 bg-[#F87171]/[0.06] p-3" data-testid="boucle-detail-erreur">
              <p className="flex items-start gap-2 text-xs text-[#FCA5A5]">
                <WarningCircle size={14} className="mt-0.5 shrink-0" /> {etat.erreur}
              </p>
              <button
                type="button"
                onClick={onReessayer}
                data-testid="boucle-detail-reessayer"
                className="mt-2 rounded-md border border-[#F87171]/40 px-2.5 py-1 text-[11px] font-semibold text-[#FCA5A5] transition-colors hover:bg-[#F87171]/10"
              >
                Réessayer
              </button>
            </div>
          )}
          {!etat.chargement && !etat.erreur && amont.length === 0 && (
            <p className="text-xs text-[#7C93A8]" data-testid="boucle-chaine-vide">
              Aucune chaîne amont enregistrée.
            </p>
          )}
          {!etat.chargement && !etat.erreur && amont.length > 0 && (
            <ol data-testid="boucle-chaine">
              {amont.map((etape, index) => (
                <EtapeChaine
                  key={idObjet(etape) || `${index}-${titreObjet(etape)}`}
                  etape={etape}
                  index={index}
                  dernier={index === amont.length - 1}
                />
              ))}
            </ol>
          )}
        </Depliable>

        {precisions.length > 0 && (
          <section className="mt-5" aria-labelledby="boucle-precisions-titre">
            <h3 id="boucle-precisions-titre" className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]">
              Précisions
            </h3>
            <dl className="mt-2 space-y-1.5" data-testid="boucle-precisions">
              {precisions.map(([libelle, contenu]) => (
                <div key={libelle} className="flex gap-3 text-xs">
                  <dt className="w-28 shrink-0 text-[#7C93A8]">{libelle}</dt>
                  <dd className="min-w-0 flex-1 text-[#D8E2EA]">{contenu}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        <section className="mt-5" aria-labelledby="boucle-reperes-titre">
          <h3 id="boucle-reperes-titre" className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]">
            Repères
          </h3>
          <dl className="mt-2 space-y-1.5 text-xs">
            <div className="flex gap-3">
              <dt className="w-28 shrink-0 text-[#7C93A8]">Version</dt>
              <dd className="text-[#D8E2EA]">{texte(valeurDe(objet, "version")) || "—"}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-28 shrink-0 text-[#7C93A8]">Observé le</dt>
              <dd className="text-[#D8E2EA]">{dateLisible(valeurDe(objet, "observe_le")) || "—"}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-28 shrink-0 text-[#7C93A8]">Mis à jour le</dt>
              <dd className="text-[#D8E2EA]">{dateLisible(valeurDe(objet, "maj_le", "cree_le")) || "—"}</dd>
            </div>
          </dl>
        </section>

        {historique.length > 0 && (
          <section className="mt-5" aria-labelledby="boucle-historique-titre" data-testid="boucle-historique">
            <h3 id="boucle-historique-titre" className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]">
              Historique
            </h3>
            <ul className="mt-2 space-y-1.5">
              {historique.slice(-8).reverse().map((entree, index) => (
                <li key={`${entree?.version || index}-${index}`} className="flex items-center justify-between gap-3 text-[11px] text-[#94A3B8]" data-testid="boucle-historique-version">
                  <span>Version {texte(entree?.version) || "—"}</span>
                  <span className="font-code text-[10px] text-[#7C93A8]">{dateLisible(entree?.maj_le || entree?.cree_le) || "—"}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </aside>
    </div>
  );
}

export default function Boucle() {
  const navigate = useNavigate();
  const [objets, setObjets] = useState([]);
  const [tenant, setTenant] = useState(null);
  const [synthese, setSynthese] = useState(null);
  const [syntheseErreur, setSyntheseErreur] = useState(false);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState(null);
  const [rechargement, setRechargement] = useState(0);
  const [recherche, setRecherche] = useState("");
  const [filtres, setFiltres] = useState({ famille: "", type: "", mode: "" });
  const [selection, setSelection] = useState(null);
  const [detail, setDetail] = useState({ chargement: false, erreur: null, data: null });
  const refDetail = useRef(0);
  const [formulaireOutcome, setFormulaireOutcome] = useState(OUTCOME_INITIAL);
  const [outcomeEnCours, setOutcomeEnCours] = useState(false);
  const [outcomeErreur, setOutcomeErreur] = useState("");
  const [outcomeSucces, setOutcomeSucces] = useState("");
  const [twins, setTwins] = useState([]);
  const [twinsChargement, setTwinsChargement] = useState(true);
  const [twinsErreur, setTwinsErreur] = useState("");
  const [rechargementTwins, setRechargementTwins] = useState(0);
  const [formulaireTwin, setFormulaireTwin] = useState(TWIN_INITIAL);
  const [twinEnCours, setTwinEnCours] = useState(false);
  const [twinErreur, setTwinErreur] = useState("");
  const [twinSucces, setTwinSucces] = useState("");

  useEffect(() => {
    let annule = false;
    setChargement(true);
    setErreur(null);
    const params = { limite: 500 };
    if (filtres.famille) params.famille = filtres.famille;
    if (filtres.type) params.type = filtres.type;
    if (filtres.mode) params.mode = filtres.mode;
    api.get("/boucle/objets", { params })
      .then((reponse) => {
        if (annule) return;
        const liste = Array.isArray(reponse.data)
          ? reponse.data
          : Array.isArray(reponse.data?.objets) ? reponse.data.objets : [];
        setObjets(liste);
        setTenant(reponse.data?.tenant || null);
      })
      .catch((cause) => {
        if (annule) return;
        setObjets([]);
        setErreur(messageErreur(cause));
      })
      .finally(() => {
        if (!annule) setChargement(false);
      });
    return () => { annule = true; };
  }, [filtres.famille, filtres.type, filtres.mode, rechargement]);

  useEffect(() => {
    let annule = false;
    setSyntheseErreur(false);
    api.get("/boucle/synthese")
      .then((reponse) => {
        if (annule) return;
        setSynthese(reponse.data || null);
      })
      .catch(() => {
        if (annule) return;
        setSynthese(null);
        setSyntheseErreur(true);
      });
    return () => { annule = true; };
  }, [rechargement]);

  useEffect(() => {
    let annule = false;
    setTwinsChargement(true);
    setTwinsErreur("");
    api.get("/boucle/twins", { params: { limite: 200 } })
      .then((reponse) => {
        if (annule) return;
        const liste = Array.isArray(reponse.data)
          ? reponse.data
          : Array.isArray(reponse.data?.twins) ? reponse.data.twins : [];
        setTwins(liste);
      })
      .catch((cause) => {
        if (annule) return;
        setTwins([]);
        setTwinsErreur(messageErreur(cause, "Les twins typés sont indisponibles."));
      })
      .finally(() => {
        if (!annule) setTwinsChargement(false);
      });
    return () => { annule = true; };
  }, [rechargementTwins]);

  const chargerDetail = useCallback((identifiant) => {
    if (!identifiant) return;
    const jeton = refDetail.current + 1;
    refDetail.current = jeton;
    setDetail({ chargement: true, erreur: null, data: null });
    api.get(`/boucle/objets/${encodeURIComponent(identifiant)}`, { params: { historique: true } })
      .then((reponse) => {
        if (refDetail.current !== jeton) return;
        setDetail({ chargement: false, erreur: null, data: reponse.data || null });
      })
      .catch((cause) => {
        if (refDetail.current !== jeton) return;
        setDetail({
          chargement: false,
          erreur: messageErreur(cause, "Impossible de charger le détail de cet objet."),
          data: null,
        });
      });
  }, []);

  const ouvrirObjet = (objet) => {
    setSelection(objet);
    const identifiant = idObjet(objet);
    if (identifiant) chargerDetail(identifiant);
    else setDetail({ chargement: false, erreur: null, data: null });
  };

  useEffect(() => {
    if (!selection) return undefined;
    const fermer = (evenement) => {
      if (evenement.key === "Escape") setSelection(null);
    };
    document.addEventListener("keydown", fermer);
    return () => document.removeEventListener("keydown", fermer);
  }, [selection]);

  const objetsFiltres = useMemo(() => {
    const requete = sansAccents(recherche.trim());
    if (!requete) return objets;
    return objets.filter((objet) =>
      sansAccents([
        titreObjet(objet),
        resumeObjet(objet),
        idObjet(objet),
        typeObjet(objet),
        familleObjet(objet),
        valeurDe(objet, "mode"),
      ].join(" ")).includes(requete)
    );
  }, [objets, recherche]);

  const sections = useMemo(
    () => STADES
      .map((stade) => ({ ...stade, objets: objetsFiltres.filter((objet) => typeObjet(objet) === stade.type) }))
      .filter((stade) => stade.objets.length > 0),
    [objetsFiltres],
  );

  const autres = useMemo(
    () => objetsFiltres.filter((objet) => !STADES_PAR_TYPE.has(typeObjet(objet))),
    [objetsFiltres],
  );

  const twinsNonApplicatifs = useMemo(
    () => twins.filter((twin) => LABELS_TWIN.has(texte(twin?.type).trim().toUpperCase())),
    [twins],
  );

  const compteStade = (stade) => {
    const compte = compteSynthese(synthese, stade);
    return compte !== null ? compte : objets.filter((objet) => typeObjet(objet) === stade.type).length;
  };

  const total = totalSynthese(synthese) ?? objets.length;
  const filtresActifs = Boolean(recherche.trim() || filtres.famille || filtres.type || filtres.mode);
  const objetDetail = detail.data?.objet || selection;
  const chaineDetail = Array.isArray(detail.data?.chaine)
    ? detail.data.chaine
    : Array.isArray(detail.data?.objet?.chaine) ? detail.data.objet.chaine : [];
  const historiqueDetail = Array.isArray(detail.data?.historique)
    ? detail.data.historique
    : Array.isArray(detail.data?.objet?.historique) ? detail.data.objet.historique : [];

  const reinitialiser = () => {
    setRecherche("");
    setFiltres({ famille: "", type: "", mode: "" });
  };

  const changerFiltre = (cle, valeur) => {
    setFiltres((avant) => ({ ...avant, [cle]: valeur }));
  };

  const actualiser = () => setRechargement((valeur) => valeur + 1);

  const ouvrirParId = (identifiant) => {
    if (!identifiant) return;
    const connu = objets.find((objet) => idObjet(objet) === identifiant);
    setSelection(connu || { id: identifiant, type: "", famille: "" });
    chargerDetail(identifiant);
  };

  const changerOutcome = (cle, valeur) => {
    setFormulaireOutcome((avant) => ({ ...avant, [cle]: valeur }));
  };

  const creerOutcome = async (evenement) => {
    evenement.preventDefault();
    setOutcomeErreur("");
    setOutcomeSucces("");

    const initiative = texte(formulaireOutcome.initiative_id).trim();
    const metrique = texte(formulaireOutcome.metrique).trim();
    const valeurBrute = texte(formulaireOutcome.valeur).trim().replace(",", ".");
    const cibleBrute = texte(formulaireOutcome.cible).trim().replace(",", ".");
    const unite = texte(formulaireOutcome.unite).trim();
    const enseignement = texte(formulaireOutcome.enseignement).trim();

    if (!initiative) {
      setOutcomeErreur("L'identifiant de l'initiative liée est obligatoire.");
      return;
    }
    if (!metrique) {
      setOutcomeErreur("La métrique est obligatoire.");
      return;
    }
    if (!valeurBrute) {
      setOutcomeErreur("La valeur mesurée est obligatoire.");
      return;
    }
    if (!Number.isFinite(Number(valeurBrute))) {
      setOutcomeErreur("La valeur mesurée doit être un nombre.");
      return;
    }
    if (cibleBrute && !Number.isFinite(Number(cibleBrute))) {
      setOutcomeErreur("La cible doit être un nombre.");
      return;
    }
    if (!enseignement) {
      setOutcomeErreur("L'enseignement est obligatoire : un outcome produit toujours une leçon explicite.");
      return;
    }

    const mesure = { metrique, valeur: Number(valeurBrute) };
    if (unite) mesure.unite = unite;
    const corps = { initiative_id: initiative, mesure, enseignement };
    if (cibleBrute) corps.cible = Number(cibleBrute);
    const preuves = texte(formulaireOutcome.preuves)
      .split(",")
      .map((preuve) => preuve.trim())
      .filter(Boolean);
    if (preuves.length > 0) corps.preuve_ids = preuves;

    setOutcomeEnCours(true);
    try {
      const reponse = await api.post("/boucle/outcomes", corps);
      const identifiantOutcome = texte(reponse.data?.outcome?.id).trim();
      const identifiantLearning = texte(reponse.data?.learning?.id).trim();
      setOutcomeSucces([
        identifiantOutcome ? `Outcome ${identifiantOutcome} enregistré.` : "Outcome enregistré.",
        identifiantLearning ? `Learning ${identifiantLearning} capitalisé.` : "",
        "La liste et la synthèse sont actualisées.",
      ].filter(Boolean).join(" "));
      setFormulaireOutcome({ ...OUTCOME_INITIAL });
      actualiser();
    } catch (cause) {
      setOutcomeErreur(messageErreur(cause, "L'outcome n'a pas pu être enregistré."));
    } finally {
      setOutcomeEnCours(false);
    }
  };

  const changerTwin = (cle, valeur) => {
    setFormulaireTwin((avant) => ({ ...avant, [cle]: valeur }));
    if (twinErreur) setTwinErreur("");
  };

  const creerTwin = async (evenement) => {
    evenement.preventDefault();
    setTwinErreur("");
    setTwinSucces("");

    const identifiant = texte(formulaireTwin.id).trim();
    const type = texte(formulaireTwin.type).trim().toUpperCase();
    const nom = texte(formulaireTwin.nom).trim();
    const mission = texte(formulaireTwin.mission).trim();
    const domaine = texte(formulaireTwin.domaine).trim();
    const equipe = texte(formulaireTwin.equipe).trim();

    if (!identifiant) {
      setTwinErreur("L'identifiant du twin est obligatoire.");
      return;
    }
    if (identifiant.length > 128) {
      setTwinErreur("L'identifiant du twin ne peut pas dépasser 128 caractères.");
      return;
    }
    if (!LABELS_TWIN.has(type)) {
      setTwinErreur("Le type du twin est obligatoire et doit être un type non applicatif proposé.");
      return;
    }
    if (!nom) {
      setTwinErreur("Le nom du twin est obligatoire.");
      return;
    }
    if (nom.length > 200) {
      setTwinErreur("Le nom du twin ne peut pas dépasser 200 caractères.");
      return;
    }
    if (mission.length > 2000) {
      setTwinErreur("La mission ne peut pas dépasser 2000 caractères.");
      return;
    }
    if (domaine.length > 128) {
      setTwinErreur("Le domaine ne peut pas dépasser 128 caractères.");
      return;
    }
    if (equipe.length > 200) {
      setTwinErreur("L'équipe ne peut pas dépasser 200 caractères.");
      return;
    }

    const corps = { id: identifiant, type, nom, equipe: equipe || "à confirmer" };
    if (mission) corps.mission = mission;
    if (domaine) corps.domaine = domaine;

    setTwinEnCours(true);
    try {
      const reponse = await api.post("/boucle/twins", corps);
      const identifiantCree = texte(reponse.data?.twin?.id).trim() || identifiant;
      setTwinSucces(`Twin ${identifiantCree} enregistré. La liste des twins est actualisée.`);
      setFormulaireTwin({ ...TWIN_INITIAL });
      setRechargementTwins((valeur) => valeur + 1);
    } catch (cause) {
      setTwinErreur(messageErreur(cause, "Le twin n'a pas pu être créé."));
    } finally {
      setTwinEnCours(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#071019] px-4 py-5 pb-20 sm:px-8 sm:py-8 lg:px-12" data-testid="boucle-page">
      <div className="mx-auto max-w-[1500px]">
        <header className="rise">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#60A5FA]">Boucle</div>
              <h1 className="mt-1 font-display text-xl font-black tracking-tight text-[#F2F6F8]" data-testid="boucle-titre">
                De la situation au learning
              </h1>
              <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[#94A3B8]">
                La mémoire vivante de ce que l'entreprise observe, comprend, décide, tente et apprend.
              </p>
            </div>
            <button
              type="button"
              onClick={actualiser}
              data-testid="boucle-actualiser"
              className="flex h-8 items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
            >
              <ArrowsClockwise size={13} className={chargement ? "animate-spin" : ""} /> Actualiser
            </button>
          </div>
        </header>

        <section
          className="rise mt-5 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4"
          aria-labelledby="boucle-twin-titre"
          data-testid="boucle-twin-form"
        >
          <div className="flex items-start gap-2">
            <Compass size={14} className="mt-0.5 shrink-0 text-[#60A5FA]" />
            <div className="min-w-0">
              <h2 id="boucle-twin-titre" className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]">
                Créer un twin non applicatif
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-[#7C93A8]">
                Un processus, une capacité, un parcours ou une organisation peut entrer dans le Mesh sans passer par
                la commande d'application.
              </p>
            </div>
          </div>

          <form onSubmit={creerTwin} noValidate className="mt-3">
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label htmlFor="boucle-twin-id" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Identifiant
                </label>
                <input
                  id="boucle-twin-id"
                  value={formulaireTwin.id}
                  onChange={(evenement) => changerTwin("id", evenement.target.value)}
                  required
                  maxLength={128}
                  autoComplete="off"
                  placeholder="process-facturation"
                  data-testid="boucle-twin-id"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 font-code text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="boucle-twin-type" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Type
                </label>
                <select
                  id="boucle-twin-type"
                  value={formulaireTwin.type}
                  onChange={(evenement) => changerTwin("type", evenement.target.value)}
                  required
                  data-testid="boucle-twin-type"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2 text-xs text-[#D8E2EA] focus:border-[#60A5FA]/60 focus:outline-none"
                >
                  {TYPES_TWIN.map(([valeur, libelle]) => (
                    <option key={valeur} value={valeur}>{libelle}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="boucle-twin-nom" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Nom
                </label>
                <input
                  id="boucle-twin-nom"
                  value={formulaireTwin.nom}
                  onChange={(evenement) => changerTwin("nom", evenement.target.value)}
                  required
                  maxLength={200}
                  autoComplete="off"
                  placeholder="Facturation client"
                  data-testid="boucle-twin-nom"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="boucle-twin-domaine" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Domaine (optionnel)
                </label>
                <input
                  id="boucle-twin-domaine"
                  value={formulaireTwin.domaine}
                  onChange={(evenement) => changerTwin("domaine", evenement.target.value)}
                  maxLength={128}
                  autoComplete="off"
                  placeholder="Finance"
                  data-testid="boucle-twin-domaine"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="boucle-twin-equipe" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Équipe (optionnel)
                </label>
                <input
                  id="boucle-twin-equipe"
                  value={formulaireTwin.equipe}
                  onChange={(evenement) => changerTwin("equipe", evenement.target.value)}
                  maxLength={200}
                  autoComplete="off"
                  placeholder="à confirmer"
                  data-testid="boucle-twin-equipe"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="boucle-twin-mission" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Mission (optionnel)
                </label>
                <textarea
                  id="boucle-twin-mission"
                  value={formulaireTwin.mission}
                  onChange={(evenement) => changerTwin("mission", evenement.target.value)}
                  maxLength={2000}
                  rows={1}
                  placeholder="Ce que ce twin rend possible et pour qui…"
                  data-testid="boucle-twin-mission"
                  className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 py-1.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={twinEnCours}
                data-testid="boucle-twin-enregistrer"
                className="flex h-8 items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {twinEnCours ? "Enregistrement…" : "Créer le twin"}
              </button>
              {twinErreur && (
                <p role="alert" data-testid="boucle-twin-erreur" className="text-xs text-[#FCA5A5]">
                  {twinErreur}
                </p>
              )}
              {twinSucces && (
                <p role="status" data-testid="boucle-twin-succes" className="text-xs text-[#6EE7B7]">
                  {twinSucces}
                </p>
              )}
            </div>
          </form>

          <div className="mt-4 border-t border-[rgba(148,163,184,0.12)] pt-3" data-testid="boucle-twins">
            <h3 className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
              Twins typés connus · {twinsNonApplicatifs.length}
            </h3>
            {twinsChargement && (
              <p className="mt-2 flex items-center gap-2 text-xs text-[#7C93A8]" data-testid="boucle-twins-chargement">
                <CircleNotch size={12} className="animate-spin" /> Chargement des twins…
              </p>
            )}
            {!twinsChargement && twinsErreur && (
              <div className="mt-2" data-testid="boucle-twins-erreur">
                <p className="text-xs text-[#FCA5A5]" role="alert">{twinsErreur}</p>
                <button
                  type="button"
                  onClick={() => setRechargementTwins((valeur) => valeur + 1)}
                  data-testid="boucle-twins-reessayer"
                  className="mt-1.5 rounded-md border border-[rgba(148,163,184,0.2)] px-2.5 py-1 text-[11px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
                >
                  Réessayer
                </button>
              </div>
            )}
            {!twinsChargement && !twinsErreur && twinsNonApplicatifs.length === 0 && (
              <p className="mt-2 text-xs text-[#7C93A8]" data-testid="boucle-twins-vide">
                Aucun twin non applicatif pour ce tenant.
              </p>
            )}
            {!twinsChargement && !twinsErreur && twinsNonApplicatifs.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1.5" data-testid="boucle-twins-liste">
                {twinsNonApplicatifs.map((twin, index) => {
                  const identifiant = idObjet(twin);
                  const type = texte(twin?.type).trim().toUpperCase();
                  return (
                    <li
                      key={identifiant || `${type}-${index}`}
                      className="flex max-w-full flex-wrap items-center gap-1.5 rounded border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-1.5 py-0.5"
                      data-testid={`boucle-twin-${identifiant || index}`}
                    >
                      <span className="min-w-0 truncate font-code text-[10px] text-[#D8E2EA]">{texte(twin?.nom) || identifiant || "Twin"}</span>
                      <span className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                        {LABELS_TWIN.get(type) || type}
                      </span>
                      {identifiant && (
                        <button
                          type="button"
                          onClick={() => navigate(`/atlas?focus=${encodeURIComponent(identifiant)}`)}
                          title={`Voir ${identifiant} dans l'Atlas`}
                          data-testid={`boucle-twin-atlas-${identifiant}`}
                          className="text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"
                        >
                          <ArrowUpRight size={10} />
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </section>

        <section
          className="rise mt-5 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-4"
          aria-labelledby="boucle-outcome-titre"
          data-testid="boucle-outcome-form"
        >
          <div className="flex items-start gap-2">
            <ChartLineUp size={14} className="mt-0.5 shrink-0 text-[#34D399]" />
            <div className="min-w-0">
              <h2 id="boucle-outcome-titre" className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]">
                Mesurer un outcome
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-[#7C93A8]">
                Un outcome relie une initiative à une mesure observée et à l'enseignement qu'elle produit.
              </p>
            </div>
          </div>

          <form onSubmit={creerOutcome} noValidate className="mt-3">
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label htmlFor="boucle-outcome-initiative" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Initiative liée
                </label>
                <input
                  id="boucle-outcome-initiative"
                  value={formulaireOutcome.initiative_id}
                  onChange={(evenement) => changerOutcome("initiative_id", evenement.target.value)}
                  required
                  autoComplete="off"
                  placeholder="ini-…"
                  data-testid="boucle-outcome-initiative"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 font-code text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div>
                <label htmlFor="boucle-outcome-metrique" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Métrique
                </label>
                <input
                  id="boucle-outcome-metrique"
                  value={formulaireOutcome.metrique}
                  onChange={(evenement) => changerOutcome("metrique", evenement.target.value)}
                  required
                  autoComplete="off"
                  placeholder="p95, délai moyen…"
                  data-testid="boucle-outcome-metrique"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label htmlFor="boucle-outcome-valeur" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                    Valeur mesurée
                  </label>
                  <input
                    id="boucle-outcome-valeur"
                    type="text"
                    inputMode="decimal"
                    value={formulaireOutcome.valeur}
                    onChange={(evenement) => changerOutcome("valeur", evenement.target.value)}
                    required
                    autoComplete="off"
                    placeholder="180"
                    data-testid="boucle-outcome-valeur"
                    className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                  />
                </div>
                <div>
                  <label htmlFor="boucle-outcome-unite" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                    Unité
                  </label>
                  <input
                    id="boucle-outcome-unite"
                    value={formulaireOutcome.unite}
                    onChange={(evenement) => changerOutcome("unite", evenement.target.value)}
                    autoComplete="off"
                    placeholder="ms, %, €…"
                    data-testid="boucle-outcome-unite"
                    className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label htmlFor="boucle-outcome-cible" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Cible (optionnel)
                </label>
                <input
                  id="boucle-outcome-cible"
                  type="text"
                  inputMode="decimal"
                  value={formulaireOutcome.cible}
                  onChange={(evenement) => changerOutcome("cible", evenement.target.value)}
                  autoComplete="off"
                  placeholder="200"
                  data-testid="boucle-outcome-cible"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div className="sm:col-span-2 lg:col-span-2">
                <label htmlFor="boucle-outcome-preuves" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Preuves (IDs séparés par une virgule, optionnel)
                </label>
                <input
                  id="boucle-outcome-preuves"
                  value={formulaireOutcome.preuves}
                  onChange={(evenement) => changerOutcome("preuves", evenement.target.value)}
                  autoComplete="off"
                  placeholder="preuve-1, preuve-2"
                  data-testid="boucle-outcome-preuves"
                  className="mt-1 h-8 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 font-code text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
              <div className="sm:col-span-2 lg:col-span-3">
                <label htmlFor="boucle-outcome-enseignement" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                  Enseignement
                </label>
                <textarea
                  id="boucle-outcome-enseignement"
                  value={formulaireOutcome.enseignement}
                  onChange={(evenement) => changerOutcome("enseignement", evenement.target.value)}
                  required
                  rows={2}
                  placeholder="Ce que la mesure apprend, formulé comme une leçon réutilisable…"
                  data-testid="boucle-outcome-enseignement"
                  className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 py-2 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                />
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button
                type="submit"
                disabled={outcomeEnCours}
                data-testid="boucle-outcome-enregistrer"
                className="flex h-8 items-center gap-1.5 rounded-md bg-[#34D399] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#6EE7B7] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {outcomeEnCours ? "Enregistrement…" : "Enregistrer l'outcome"}
              </button>
              {outcomeErreur && (
                <p id="boucle-outcome-erreur" role="alert" data-testid="boucle-outcome-erreur" className="text-xs text-[#FCA5A5]">
                  {outcomeErreur}
                </p>
              )}
              {outcomeSucces && (
                <p role="status" data-testid="boucle-outcome-succes" className="text-xs text-[#6EE7B7]">
                  {outcomeSucces}
                </p>
              )}
            </div>
          </form>
        </section>

        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6" data-testid="boucle-synthese">
          {STADES.map((stade) => {
            const compte = compteStade(stade);
            const Icone = stade.Icone;
            return (
              <div
                key={stade.type}
                data-testid="boucle-compteur"
                data-stade={stade.type.toLowerCase()}
                className="rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-3 py-2.5"
              >
                <div className="flex items-center gap-1.5 font-code text-[10px] uppercase tracking-[0.16em] text-[#7C93A8]">
                  <Icone size={12} style={{ color: stade.couleur }} /> {stade.court}
                </div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span
                    className="font-display text-lg font-black text-[#F2F6F8]"
                    data-testid={`boucle-compteur-${stade.type.toLowerCase()}`}
                  >
                    {compte}
                  </span>
                  <span className="text-[11px] text-[#7C93A8]">{stade.label.toLowerCase()}</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-code text-[10px] text-[#7C93A8]">
          <span data-testid="boucle-total">{total} objet{total > 1 ? "s" : ""} dans la boucle</span>
          {tenant && <span data-testid="boucle-tenant">· tenant {tenant}</span>}
          {syntheseErreur && (
            <span className="text-[#F2B84B]" data-testid="boucle-synthese-erreur">
              · synthèse indisponible, compteurs calculés sur les objets chargés
            </span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2" data-testid="boucle-filtres">
          <div className="relative min-w-[13rem] flex-1 sm:max-w-xs">
            <MagnifyingGlass size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#7C93A8]" />
            <input
              type="search"
              value={recherche}
              onChange={(evenement) => setRecherche(evenement.target.value)}
              placeholder="Rechercher un objet, un titre, un résumé…"
              aria-label="Rechercher dans la boucle"
              data-testid="boucle-recherche"
              className="h-9 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] pl-7 pr-3 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
            />
          </div>
          <select
            value={filtres.famille}
            onChange={(evenement) => changerFiltre("famille", evenement.target.value)}
            aria-label="Filtrer par famille"
            data-testid="boucle-filtre-famille"
            className="h-8 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs text-[#D8E2EA] focus:outline-none"
          >
            <option value="">Toutes les familles</option>
            {FAMILLES.map((famille) => (
              <option key={famille.value} value={famille.value}>{famille.label}</option>
            ))}
          </select>
          <select
            value={filtres.type}
            onChange={(evenement) => changerFiltre("type", evenement.target.value)}
            aria-label="Filtrer par type"
            data-testid="boucle-filtre-type"
            className="h-8 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs text-[#D8E2EA] focus:outline-none"
          >
            <option value="">Tous les types</option>
            {STADES.map((stade) => (
              <option key={stade.type} value={stade.type}>{stade.court}</option>
            ))}
          </select>
          <select
            value={filtres.mode}
            onChange={(evenement) => changerFiltre("mode", evenement.target.value)}
            aria-label="Filtrer par mode"
            data-testid="boucle-filtre-mode"
            className="h-8 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs text-[#D8E2EA] focus:outline-none"
          >
            <option value="">Tous les modes</option>
            {MODES.map(([valeur, libelle]) => (
              <option key={valeur} value={valeur}>{libelle}</option>
            ))}
          </select>
          {filtresActifs && (
            <button
              type="button"
              onClick={reinitialiser}
              data-testid="boucle-reinitialiser"
              className="h-8 rounded-full border border-[rgba(148,163,184,0.16)] px-3 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8]"
            >
              Réinitialiser
            </button>
          )}
          <span className="ml-auto font-code text-[10px] text-[#7C93A8]" data-testid="boucle-nb-resultats">
            {objetsFiltres.length} objet{objetsFiltres.length > 1 ? "s" : ""} affiché{objetsFiltres.length > 1 ? "s" : ""}
          </span>
        </div>

        {chargement && (
          <div className="mt-8 space-y-3" data-testid="boucle-chargement">
            {[0, 1, 2].map((rang) => (
              <div key={rang} className="animate-pulse rounded-xl border border-[rgba(148,163,184,0.12)] bg-[#0B1620] p-4">
                <div className="h-3 w-36 rounded bg-white/[0.06]" />
                <div className="mt-2 h-2 w-2/3 rounded bg-white/[0.04]" />
              </div>
            ))}
          </div>
        )}

        {!chargement && erreur && (
          <div className="mt-8 rounded-xl border border-[#F87171]/30 bg-[#F87171]/[0.06] p-5" data-testid="boucle-erreur">
            <p className="flex items-start gap-2 text-sm text-[#FCA5A5]">
              <WarningCircle size={17} className="mt-0.5 shrink-0" /> {erreur}
            </p>
            <button
              type="button"
              onClick={actualiser}
              data-testid="boucle-reessayer"
              className="mt-3 rounded-md border border-[#F87171]/40 px-3 py-1.5 text-xs font-semibold text-[#FCA5A5] transition-colors hover:bg-[#F87171]/10"
            >
              Réessayer
            </button>
          </div>
        )}

        {!chargement && !erreur && objetsFiltres.length === 0 && (
          <div className="mt-10 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-5 py-10 text-center" data-testid="boucle-vide">
            <p className="text-sm font-semibold text-[#D8E2EA]">
              {objets.length === 0 && !filtresActifs ? "Aucun objet dans la boucle." : "Aucun objet ne correspond à ces filtres."}
            </p>
            <p className="mt-1 text-xs text-[#7C93A8]">
              {objets.length === 0 && !filtresActifs
                ? "Les situations, investigations, décisions, initiatives, outcomes et learnings apparaîtront ici."
                : "Élargissez la recherche ou réinitialisez les filtres."}
            </p>
            {filtresActifs && (
              <button
                type="button"
                onClick={reinitialiser}
                className="mt-4 rounded-md border border-[rgba(148,163,184,0.2)] px-3 py-1.5 text-xs text-[#D8E2EA] transition-colors hover:border-[#60A5FA]/40"
              >
                Réinitialiser les filtres
              </button>
            )}
          </div>
        )}

        {!chargement && !erreur && objetsFiltres.length > 0 && (
          <div className="mt-6 space-y-6" data-testid="boucle-sections">
            {sections.map((stade) => (
              <section key={stade.type} data-testid={`boucle-section-${stade.type.toLowerCase()}`}>
                <div className="mb-2 flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: stade.couleur }} aria-hidden="true" />
                  <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#94A3B8]">{stade.label}</h2>
                  <span
                    className="rounded-full border border-[rgba(148,163,184,0.16)] px-1.5 font-code text-[10px] text-[#7C93A8]"
                    data-testid={`boucle-section-compte-${stade.type.toLowerCase()}`}
                  >
                    {stade.objets.length}
                  </span>
                </div>
                <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
                  {stade.objets.map((objet, index) => (
                    <CarteObjet
                      key={idObjet(objet) || `${stade.type}-${index}`}
                      objet={objet}
                      stade={stade}
                      actif={idObjet(objet) === idObjet(selection)}
                      onOuvrir={ouvrirObjet}
                    />
                  ))}
                </div>
              </section>
            ))}
            {autres.length > 0 && (
              <section data-testid="boucle-section-autres">
                <div className="mb-2 flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#7C93A8]" aria-hidden="true" />
                  <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#94A3B8]">Autres objets</h2>
                  <span className="rounded-full border border-[rgba(148,163,184,0.16)] px-1.5 font-code text-[10px] text-[#7C93A8]">
                    {autres.length}
                  </span>
                </div>
                <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
                  {autres.map((objet, index) => (
                    <CarteObjet
                      key={idObjet(objet) || `autre-${index}`}
                      objet={objet}
                      stade={{ couleur: "#7C93A8", court: typeObjet(objet) || "Objet" }}
                      actif={idObjet(objet) === idObjet(selection)}
                      onOuvrir={ouvrirObjet}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>

      {selection && (
        <PanneauDetail
          objet={objetDetail}
          etat={detail}
          chaine={chaineDetail}
          historique={historiqueDetail}
          onFermer={() => setSelection(null)}
          onReessayer={() => chargerDetail(idObjet(selection))}
          onNaviguer={navigate}
          onOuvrirId={ouvrirParId}
        />
      )}
    </div>
  );
}
