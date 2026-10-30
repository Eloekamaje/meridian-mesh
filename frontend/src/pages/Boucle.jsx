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

function PanneauDetail({ objet, etat, chaine, historique, onFermer, onReessayer, onNaviguer }) {
  if (!objet) return null;

  const stade = STADES_PAR_TYPE.get(typeObjet(objet));
  const identifiant = idObjet(objet);
  const amont = chaine.filter((etape) => idObjet(etape) !== identifiant);
  const travail = idTravail(objet);
  const atlas = idsAtlas(objet);
  const mode = texte(valeurDe(objet, "mode")).toUpperCase();
  const resume = resumeObjet(objet);
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

        <section className="mt-6" aria-labelledby="boucle-chaine-titre">
          <h3 id="boucle-chaine-titre" className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]">
            Chaîne amont
          </h3>
          {etat.chargement && (
            <p className="mt-2 flex items-center gap-2 text-xs text-[#7C93A8]" data-testid="boucle-detail-chargement">
              <CircleNotch size={14} className="animate-spin" /> Chargement du détail…
            </p>
          )}
          {!etat.chargement && etat.erreur && (
            <div className="mt-2 rounded-lg border border-[#F87171]/30 bg-[#F87171]/[0.06] p-3" data-testid="boucle-detail-erreur">
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
            <p className="mt-2 text-xs text-[#7C93A8]" data-testid="boucle-chaine-vide">
              Aucune chaîne amont enregistrée.
            </p>
          )}
          {!etat.chargement && !etat.erreur && amont.length > 0 && (
            <ol className="mt-2" data-testid="boucle-chaine">
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
        </section>

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
        />
      )}
    </div>
  );
}
