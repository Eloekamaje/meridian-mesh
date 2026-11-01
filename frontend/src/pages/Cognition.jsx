import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowClockwise,
  Brain,
  Check,
  CheckCircle,
  DownloadSimple,
  Flask,
  ShieldCheck,
  Trash,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import api from "@/lib/api";

const SCOPES = [
  ["user", "Utilisateur"],
  ["session", "Session"],
  ["twin", "Jumeau"],
  ["situation", "Situation"],
];

const CLASSES = [
  ["session", "Session"],
  ["preference", "Préférence"],
  ["contexte", "Contexte"],
  ["decision", "Décision"],
  ["apprentissage", "Apprentissage"],
];

const LABELS_SCOPE = new Map(SCOPES);
const LABELS_CLASSE = new Map(CLASSES);
const LABELS_VERIFICATION = {
  preuves: "Preuves et citations",
  contexte: "Empreinte de contexte",
  autorite: "Autorité bornée",
  abstention: "Abstention explicite",
  outils: "Outils sans erreur",
};

const texte = (valeur) => (valeur == null ? "" : String(valeur));

function messageErreur(erreur, defaut) {
  const detail = erreur?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (typeof erreur?.message === "string" && erreur.message.trim() && !erreur.response) {
    return erreur.message;
  }
  return defaut;
}

function dateCourte(valeur) {
  if (!valeur) return "—";
  const date = new Date(valeur);
  if (Number.isNaN(date.getTime())) return texte(valeur);
  return date.toLocaleString("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function normaliserApprobations(donnees) {
  if (Array.isArray(donnees)) return donnees;
  for (const cle of ["approbations", "approvals", "items", "resultats"]) {
    if (Array.isArray(donnees?.[cle])) return donnees[cle];
  }
  return [];
}

function normaliserMemoires(donnees) {
  if (Array.isArray(donnees)) return donnees;
  if (Array.isArray(donnees?.memoires)) return donnees.memoires;
  return [];
}

function identifiantApproval(approbation) {
  return texte(
    approbation?.id
      ?? approbation?.approbation_id
      ?? `${texte(approbation?.run_id)}-${texte(approbation?.etape)}-${texte(approbation?.cible)}-${texte(approbation?.operation)}`,
  );
}

function telechargerJson(nom, contenu) {
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") return false;
  const blob = new Blob([contenu], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const lien = document.createElement("a");
  lien.href = url;
  lien.download = nom;
  document.body.appendChild(lien);
  lien.click();
  lien.remove();
  if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url);
  return true;
}

function EtatVide({ testid, children }) {
  return (
    <p className="rounded-lg border border-dashed border-[rgba(148,163,184,0.22)] px-3 py-4 text-xs text-[#7C93A8]" data-testid={testid}>
      {children}
    </p>
  );
}

function Badge({ children, ton = "neutre" }) {
  const couleurs = {
    neutre: "border-[rgba(148,163,184,0.24)] text-[#94A3B8]",
    info: "border-[#60A5FA]/40 bg-[#60A5FA]/[0.06] text-[#BFDBFE]",
    ok: "border-[#34D399]/40 bg-[#34D399]/[0.06] text-[#6EE7B7]",
    alerte: "border-[#F2B84B]/40 bg-[#F2B84B]/[0.06] text-[#FCD34D]",
    danger: "border-[#F87171]/40 bg-[#F87171]/[0.06] text-[#FCA5A5]",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider ${couleurs[ton]}`}>
      {children}
    </span>
  );
}

function EnteteSection({ icone: Icone, titre, description, actions }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">
          <Icone size={14} className="text-[#60A5FA]" /> {titre}
        </h2>
        <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[#7C93A8]">{description}</p>
      </div>
      {actions}
    </div>
  );
}

export default function Cognition() {
  const [approbations, setApprobations] = useState([]);
  const [chargementApprobations, setChargementApprobations] = useState(true);
  const [infoApprobations, setInfoApprobations] = useState("");
  const [approbationChoisie, setApprobationChoisie] = useState(null);
  const [motifDecision, setMotifDecision] = useState("");
  const [decisionEnCours, setDecisionEnCours] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState("");
  const [decisionErreur, setDecisionErreur] = useState("");

  const [memoires, setMemoires] = useState([]);
  const [chargementMemoire, setChargementMemoire] = useState(true);
  const [erreurMemoire, setErreurMemoire] = useState("");
  const [scope, setScope] = useState("");
  const [classe, setClasse] = useState("");
  const [rechargementMemoire, setRechargementMemoire] = useState(0);
  const [selectionMemoires, setSelectionMemoires] = useState(() => new Set());
  const [exportEnCours, setExportEnCours] = useState(false);
  const [exportMessage, setExportMessage] = useState("");
  const [exportErreur, setExportErreur] = useState("");
  const [purgeConfirmee, setPurgeConfirmee] = useState(false);
  const [purgeEnCours, setPurgeEnCours] = useState(false);
  const [purgeMessage, setPurgeMessage] = useState("");
  const [purgeErreur, setPurgeErreur] = useState("");
  const [proposition, setProposition] = useState(null);
  const [groupesChoisis, setGroupesChoisis] = useState(() => new Set());
  const [consolidationEnCours, setConsolidationEnCours] = useState(false);
  const [consolidationErreur, setConsolidationErreur] = useState("");
  const [consolidationMessage, setConsolidationMessage] = useState("");
  const [application, setApplication] = useState(null);
  const [applicationEnCours, setApplicationEnCours] = useState(false);
  const [applicationErreur, setApplicationErreur] = useState("");

  const [runId, setRunId] = useState("");
  const [evaluation, setEvaluation] = useState(null);
  const [replay, setReplay] = useState(null);
  const [evaluationEnCours, setEvaluationEnCours] = useState(false);
  const [evaluationErreur, setEvaluationErreur] = useState("");
  const [replayErreur, setReplayErreur] = useState("");

  const chargerApprobations = useCallback(async () => {
    setChargementApprobations(true);
    setInfoApprobations("");
    setDecisionMessage("");
    setDecisionErreur("");
    try {
      const reponse = await api.get("/runs/approvals");
      const liste = normaliserApprobations(reponse.data);
      setApprobations(liste);
      setApprobationChoisie((courante) => {
        if (!courante) return null;
        return liste.find((approbation) => identifiantApproval(approbation) === identifiantApproval(courante)) || null;
      });
      if (liste.length === 0) setInfoApprobations("Aucune approbation en attente.");
    } catch (erreur) {
      const statut = erreur?.response?.status;
      setApprobations([]);
      setApprobationChoisie(null);
      if (statut === 404 || statut === 503 || !erreur?.response) {
        setInfoApprobations("La liste des approbations n'est pas encore exposée par le backend ; aucune décision ne peut être prise ici.");
      } else {
        setInfoApprobations(messageErreur(erreur, "La liste des approbations est indisponible."));
      }
    } finally {
      setChargementApprobations(false);
    }
  }, []);

  useEffect(() => {
    chargerApprobations();
  }, [chargerApprobations]);

  useEffect(() => {
    let actif = true;
    const params = { limite: 200 };
    if (scope) params.scope = scope;
    if (classe) params.classe = classe;
    setChargementMemoire(true);
    setErreurMemoire("");
    api.get("/boucle/memoire/durable", { params })
      .then((reponse) => {
        if (!actif) return;
        setMemoires(normaliserMemoires(reponse.data));
      })
      .catch((erreur) => {
        if (!actif) return;
        setMemoires([]);
        setErreurMemoire(messageErreur(erreur, "La mémoire durable est indisponible."));
      })
      .finally(() => {
        if (actif) setChargementMemoire(false);
      });
    return () => { actif = false; };
  }, [scope, classe, rechargementMemoire]);

  const memoiresSelectionnees = useMemo(
    () => memoires.filter((memoire) => selectionMemoires.has(memoire.id)),
    [memoires, selectionMemoires],
  );

  const groupes = proposition?.groupes || [];
  const conflits = proposition?.conflits || [];
  const limitesProposition = proposition?.limites || [];

  const changerScope = (valeur) => {
    setScope(valeur);
    setSelectionMemoires(new Set());
    setProposition(null);
    setGroupesChoisis(new Set());
    setApplication(null);
    setConsolidationErreur("");
    setConsolidationMessage("");
  };

  const changerClasse = (valeur) => {
    setClasse(valeur);
    setSelectionMemoires(new Set());
    setProposition(null);
    setGroupesChoisis(new Set());
    setApplication(null);
    setConsolidationErreur("");
    setConsolidationMessage("");
  };

  const basculerMemoire = (id) => {
    setSelectionMemoires((avant) => {
      const suite = new Set(avant);
      if (suite.has(id)) suite.delete(id); else suite.add(id);
      return suite;
    });
    setProposition(null);
    setGroupesChoisis(new Set());
    setApplication(null);
    setConsolidationErreur("");
    setConsolidationMessage("");
    setApplicationErreur("");
  };

  const basculerGroupe = (keepId) => {
    setGroupesChoisis((avant) => {
      const suite = new Set(avant);
      if (suite.has(keepId)) suite.delete(keepId); else suite.add(keepId);
      return suite;
    });
  };

  const basculerTousLesGroupes = () => {
    setGroupesChoisis((avant) => {
      if (groupes.length && avant.size === groupes.length) return new Set();
      return new Set(groupes.map((groupe) => groupe.keep_id));
    });
  };

  const deciderApprobation = async (approuve) => {
    if (!approbationChoisie) return;
    const run = texte(approbationChoisie.run_id);
    if (!run) {
      setDecisionErreur("Cette approbation ne porte pas d'identifiant de run ; elle ne peut pas être tranchée ici.");
      return;
    }
    setDecisionEnCours(true);
    setDecisionErreur("");
    setDecisionMessage("");
    try {
      const corps = { approuve };
      if (motifDecision.trim()) corps.motif = motifDecision.trim();
      await api.post(`/runs/${encodeURIComponent(run)}/approval`, corps);
      setDecisionMessage(`Run ${run} : ${approuve ? "approuvé" : "rejeté"}.`);
      setApprobations((avant) => avant.filter((approbation) => identifiantApproval(approbation) !== identifiantApproval(approbationChoisie)));
      setApprobationChoisie(null);
      setMotifDecision("");
    } catch (erreur) {
      setDecisionErreur(messageErreur(erreur, "La décision n'a pas pu être enregistrée."));
    } finally {
      setDecisionEnCours(false);
    }
  };

  const exporterMemoire = async () => {
    setExportEnCours(true);
    setExportErreur("");
    setExportMessage("");
    try {
      const params = {};
      if (scope) params.scope = scope;
      if (classe) params.classe = classe;
      const reponse = await api.get("/boucle/memoire/durable/export", { params });
      const nom = `memoire-durable-${new Date().toISOString().slice(0, 10)}.json`;
      const nombre = normaliserMemoires(reponse.data).length;
      const telecharge = telechargerJson(nom, JSON.stringify(reponse.data, null, 2));
      setExportMessage(telecharge ? `${nombre} mémoire(s) exportée(s) dans ${nom}.` : `${nombre} mémoire(s) prêtes dans ${nom}.`);
    } catch (erreur) {
      setExportErreur(messageErreur(erreur, "L'export de la mémoire durable a échoué."));
    } finally {
      setExportEnCours(false);
    }
  };

  const purgerMemoire = async () => {
    setPurgeEnCours(true);
    setPurgeErreur("");
    setPurgeMessage("");
    try {
      const reponse = await api.post("/boucle/memoire/durable/purge");
      const nombre = Number(reponse.data?.supprimees ?? 0);
      setPurgeMessage(`${nombre} entrée(s) expirée(s) supprimée(s).`);
      setPurgeConfirmee(false);
      setSelectionMemoires(new Set());
      setProposition(null);
      setGroupesChoisis(new Set());
      setApplication(null);
      setApplicationErreur("");
      setConsolidationMessage("");
      setRechargementMemoire((valeur) => valeur + 1);
    } catch (erreur) {
      setPurgeErreur(messageErreur(erreur, "La purge des entrées expirées a échoué."));
    } finally {
      setPurgeEnCours(false);
    }
  };

  const proposerConsolidation = async () => {
    if (memoiresSelectionnees.length < 2) return;
    setConsolidationEnCours(true);
    setConsolidationErreur("");
    setConsolidationMessage("");
    setApplication(null);
    setApplicationErreur("");
    try {
      const reponse = await api.post("/boucle/memoire/consolidation", {
        memoires: memoiresSelectionnees,
        seuil_similarite: 0.9,
      });
      setProposition(reponse.data?.proposition || null);
      setGroupesChoisis(new Set());
      if (!reponse.data?.proposition) setConsolidationErreur("Le backend n'a pas renvoyé de proposition de consolidation.");
    } catch (erreur) {
      setProposition(null);
      setConsolidationErreur(messageErreur(erreur, "La proposition de consolidation a échoué."));
    } finally {
      setConsolidationEnCours(false);
    }
  };

  const appliquerConsolidation = async () => {
    const ids = [...groupesChoisis];
    if (!ids.length || memoiresSelectionnees.length < 2) return;
    setApplicationEnCours(true);
    setApplicationErreur("");
    setConsolidationMessage("");
    try {
      const reponse = await api.post("/boucle/memoire/consolidation", {
        memoires: memoiresSelectionnees,
        ids,
        acteur: "interface-cognition",
      });
      setProposition(reponse.data?.proposition || null);
      setApplication(reponse.data?.plan || null);
      setGroupesChoisis(new Set());
      setSelectionMemoires(new Set());
      setRechargementMemoire((valeur) => valeur + 1);
      const plan = reponse.data?.plan;
      if (plan?.groupes) {
        setConsolidationMessage(`${plan.groupes.length} groupe(s) appliqué(s), ${(plan.archivees || []).length} mémoire(s) archivée(s).`);
      } else {
        setConsolidationMessage("Aucun groupe n'a été appliqué.");
      }
    } catch (erreur) {
      setApplicationErreur(messageErreur(erreur, "L'application de la consolidation a échoué."));
    } finally {
      setApplicationEnCours(false);
    }
  };

  const chargerEvaluation = async (evenement) => {
    evenement?.preventDefault?.();
    const identifiant = runId.trim();
    setEvaluationErreur("");
    setReplayErreur("");
    if (!identifiant) {
      setEvaluationErreur("Saisissez l'identifiant d'un run à évaluer.");
      return;
    }
    setEvaluationEnCours(true);
    setEvaluation(null);
    setReplay(null);
    const chemin = encodeURIComponent(identifiant);
    const [resultatEvaluation, resultatReplay] = await Promise.allSettled([
      api.get(`/boucle/runs/${chemin}/evaluation`),
      api.get(`/boucle/runs/${chemin}/replay`),
    ]);
    if (resultatEvaluation.status === "fulfilled") {
      setEvaluation(resultatEvaluation.value.data?.evaluation || null);
      if (!resultatEvaluation.value.data?.evaluation) setEvaluationErreur("Le backend n'a pas renvoyé d'évaluation pour ce run.");
    } else {
      setEvaluation(null);
      setEvaluationErreur(messageErreur(resultatEvaluation.reason, "L'évaluation du run est indisponible."));
    }
    if (resultatReplay.status === "fulfilled") {
      setReplay(resultatReplay.value.data?.replay || null);
      if (!resultatReplay.value.data?.replay) setReplayErreur("Le backend n'a pas renvoyé de rejeu pour ce run.");
    } else {
      setReplay(null);
      setReplayErreur(messageErreur(resultatReplay.reason, "Le rejeu du run est indisponible."));
    }
    setEvaluationEnCours(false);
  };

  const score = typeof evaluation?.score === "number" ? Math.round(evaluation.score * 100) : null;
  const verifications = Object.entries(evaluation?.verifications || {});

  return (
    <div className="h-full overflow-y-auto px-4 py-5 pb-24 sm:px-8 sm:py-8 lg:px-12" data-testid="cognition-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#60A5FA]">Cognition</div>
        <h1 className="mt-1 font-display text-2xl font-black tracking-tight text-[#F2F6F8] sm:text-3xl">Les gestes humains de la cognition</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[#94A3B8]">
          Approuver ce qui attend une décision, administrer la mémoire durable et lire l'évaluation d'un run.
          Chaque action est explicite et bornée au périmètre actif.
        </p>
      </header>

      <div className="mt-6 grid grid-cols-12 gap-6">
        <section id="approbations" className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-7" style={{ animationDelay: "40ms" }} aria-labelledby="cognition-approbations-titre" data-testid="cognition-approbations">
          <EnteteSection
            icone={CheckCircle}
            titre={<span id="cognition-approbations-titre">Approbations en attente</span>}
            description="Une décision humaine libère ou rejette un run bloqué. Rien n'est approuvé sans votre geste."
            actions={(
              <button type="button" onClick={chargerApprobations} disabled={chargementApprobations}
                className="flex h-8 items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] px-2.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8] disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="cognition-approbations-actualiser">
                <ArrowClockwise size={13} /> Actualiser
              </button>
            )}
          />

          {chargementApprobations && <p className="mt-4 text-xs text-[#7C93A8]" role="status" data-testid="cognition-approbations-chargement">Chargement des approbations…</p>}

          {!chargementApprobations && infoApprobations && (
            <div className="mt-4" role="status" data-testid="cognition-approbations-vide">
              <EtatVide testid="cognition-approbations-vide-texte">{infoApprobations}</EtatVide>
            </div>
          )}

          {!chargementApprobations && approbations.length > 0 && (
            <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
              <ul className="space-y-1.5" aria-label="Approbations en attente">
                {approbations.map((approbation) => {
                  const cle = identifiantApproval(approbation);
                  const choisie = approbationChoisie === approbation;
                  return (
                    <li key={cle}>
                      <button type="button" onClick={() => { setApprobationChoisie(approbation); setDecisionErreur(""); setDecisionMessage(""); }}
                        aria-pressed={choisie}
                        className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors ${choisie ? "border-[#60A5FA]/60 bg-[#0B1620] ring-1 ring-[#60A5FA]/20" : "border-[rgba(148,163,184,0.16)] hover:border-[#41576D] hover:bg-[#0B1620]"}`}
                        data-testid={`cognition-approbation-${cle}`}>
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate font-code text-[11px] text-[#BFDBFE]">{texte(approbation.run_id) || "Run inconnu"}</span>
                          <Badge ton="alerte">En attente</Badge>
                        </span>
                        <span className="mt-1 block truncate text-xs text-[#D8E2EA]">
                          {texte(approbation.etape) || "Étape non précisée"}{approbation.outil ? ` · ${texte(approbation.outil)}` : ""}
                        </span>
                        <span className="mt-0.5 block truncate font-code text-[10px] text-[#7C93A8]">{texte(approbation.cible) || texte(approbation.operation) || dateCourte(approbation.cree_le)}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>

              {approbationChoisie ? (
                <div className="rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0B1620] p-4" data-testid="cognition-approbation-detail" aria-label="Détail de l'approbation">
                  <h3 className="text-xs font-semibold text-[#F2F6F8]">Détail de la demande</h3>
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
                    <div><dt className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Run</dt><dd className="mt-0.5 break-all text-[#D8E2EA]">{texte(approbationChoisie.run_id) || "—"}</dd></div>
                    <div><dt className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Demandeur</dt><dd className="mt-0.5 text-[#D8E2EA]">{texte(approbationChoisie.demandeur) || "—"}</dd></div>
                    <div><dt className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Étape</dt><dd className="mt-0.5 text-[#D8E2EA]">{texte(approbationChoisie.etape) || "—"}</dd></div>
                    <div><dt className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Outil</dt><dd className="mt-0.5 text-[#D8E2EA]">{texte(approbationChoisie.outil) || "—"}</dd></div>
                    <div><dt className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Cible</dt><dd className="mt-0.5 break-all text-[#D8E2EA]">{texte(approbationChoisie.cible) || "—"}</dd></div>
                    <div><dt className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Opération</dt><dd className="mt-0.5 break-all text-[#D8E2EA]">{texte(approbationChoisie.operation) || "—"}</dd></div>
                  </dl>
                  {approbationChoisie.payload && Object.keys(approbationChoisie.payload).length > 0 && (
                    <pre className="mt-3 max-h-40 overflow-auto rounded-md border border-[rgba(148,163,184,0.16)] bg-[#071019] p-2 font-code text-[10px] text-[#94A3B8]">{JSON.stringify(approbationChoisie.payload, null, 2)}</pre>
                  )}
                  <label htmlFor="cognition-approbation-motif" className="mt-3 block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Motif (optionnel)</label>
                  <textarea id="cognition-approbation-motif" value={motifDecision} onChange={(evenement) => setMotifDecision(evenement.target.value)} rows={2}
                    className="mt-1 w-full rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2.5 py-2 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none"
                    placeholder="Préciser la raison de la décision…" data-testid="cognition-approbation-motif" />
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" onClick={() => deciderApprobation(true)} disabled={decisionEnCours}
                      className="flex h-8 items-center gap-1.5 rounded-md bg-[#34D399] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#6EE7B7] disabled:cursor-not-allowed disabled:opacity-50"
                      data-testid="cognition-approbation-approuver">
                      <Check size={13} weight="bold" /> {decisionEnCours ? "Enregistrement…" : "Approuver"}
                    </button>
                    <button type="button" onClick={() => deciderApprobation(false)} disabled={decisionEnCours}
                      className="flex h-8 items-center gap-1.5 rounded-md border border-[#F87171]/40 px-3 text-xs font-semibold text-[#FCA5A5] transition-colors hover:bg-[#F87171]/10 disabled:cursor-not-allowed disabled:opacity-50"
                      data-testid="cognition-approbation-rejeter">
                      <XCircle size={13} /> Rejeter
                    </button>
                  </div>
                </div>
              ) : (
                <p className="rounded-lg border border-dashed border-[rgba(148,163,184,0.22)] px-3 py-4 text-xs text-[#7C93A8]">
                  Sélectionnez une approbation pour voir son détail et décider.
                </p>
              )}
            </div>
          )}
          {decisionMessage && <p className="mt-3 text-xs text-[#6EE7B7]" role="status" data-testid="cognition-approbation-succes">{decisionMessage}</p>}
          {decisionErreur && <p className="mt-3 text-xs text-[#FCA5A5]" role="alert" data-testid="cognition-approbation-erreur">{decisionErreur}</p>}
        </section>

        <section id="evaluation" className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5 lg:col-span-5" style={{ animationDelay: "80ms" }} aria-labelledby="cognition-evaluation-titre" data-testid="cognition-evaluation">
          <EnteteSection
            icone={Flask}
            titre={<span id="cognition-evaluation-titre">Évaluation d'un run</span>}
            description="Note déterministe d'un résultat déjà produit, puis rejeu des empreintes persistées."
          />

          <form onSubmit={chargerEvaluation} className="mt-4">
            <label htmlFor="cognition-run-id" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Identifiant du run</label>
            <div className="mt-1 flex gap-2">
              <input id="cognition-run-id" value={runId} onChange={(evenement) => setRunId(evenement.target.value)}
                placeholder="run-…" autoComplete="off" data-testid="cognition-run-id"
                className="h-9 min-w-0 flex-1 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2.5 font-code text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] focus:border-[#60A5FA]/60 focus:outline-none" />
              <button type="button" onClick={chargerEvaluation} disabled={evaluationEnCours || !runId.trim()}
                className="flex h-9 shrink-0 items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="cognition-evaluation-lancer">
                <Flask size={13} /> {evaluationEnCours ? "Lecture…" : "Évaluer"}
              </button>
            </div>
          </form>

          <p className="mt-3 rounded-md border border-[#60A5FA]/25 bg-[#60A5FA]/[0.05] px-2.5 py-2 text-[11px] leading-relaxed text-[#93C5FD]" data-testid="cognition-replay-limite">
            Le rejeu recalcule uniquement les empreintes à partir des traces enregistrées : le modèle n'est jamais rappelé.
          </p>

          {evaluationErreur && <p className="mt-3 text-xs text-[#FCA5A5]" role="alert" data-testid="cognition-evaluation-erreur">{evaluationErreur}</p>}
          {!evaluationErreur && !evaluation && !evaluationEnCours && (
            <EtatVide testid="cognition-evaluation-vide">Aucune évaluation chargée. Saisissez un run pour lire son évaluation.</EtatVide>
          )}

          {evaluation && (
            <div className="mt-4 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0B1620] p-4" data-testid="cognition-evaluation-resultat">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <span className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Score</span>
                  <div className="font-display text-3xl font-black text-[#F2F6F8]" data-testid="cognition-evaluation-score">{score == null ? "—" : `${score} %`}</div>
                </div>
                <span className="font-code text-[10px] text-[#7C93A8]">part des vérifications satisfaites</span>
              </div>
              <ul className="mt-3 space-y-1.5" aria-label="Vérifications de l'évaluation">
                {verifications.map(([cle, valeur]) => (
                  <li key={cle} className="flex items-center justify-between gap-3 text-[11px]">
                    <span className="text-[#94A3B8]">{LABELS_VERIFICATION[cle] || cle}</span>
                    <span className={`font-code text-[10px] ${valeur ? "text-[#6EE7B7]" : "text-[#FCA5A5]"}`}>{valeur ? "OK" : "KO"}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded-md border border-[rgba(148,163,184,0.12)] px-2 py-1.5">
                  <span className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Latence</span>
                  <span className="text-[#D8E2EA]">{evaluation.metriques?.latence_ms == null ? "non fournie" : `${evaluation.metriques.latence_ms} ms`}</span>
                </div>
                <div className="rounded-md border border-[rgba(148,163,184,0.12)] px-2 py-1.5">
                  <span className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Coût</span>
                  <span className="text-[#D8E2EA]">{evaluation.metriques?.cout == null ? "non fourni" : texte(evaluation.metriques.cout)}</span>
                </div>
              </div>
              {(evaluation.raisons || []).length > 0 && (
                <div className="mt-3">
                  <h4 className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-wider text-[#FCA5A5]"><WarningCircle size={12} /> Raisons d'échec</h4>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-[11px] text-[#94A3B8]">{(evaluation.raisons || []).map((raison) => <li key={raison}>{raison}</li>)}</ul>
                </div>
              )}
              {(evaluation.limites || []).length > 0 && (
                <div className="mt-3">
                  <h4 className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Limites</h4>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-[11px] text-[#7C93A8]">{(evaluation.limites || []).map((limite) => <li key={limite}>{limite}</li>)}</ul>
                </div>
              )}
            </div>
          )}

          {replayErreur && <p className="mt-3 text-xs text-[#FCA5A5]" role="alert" data-testid="cognition-replay-erreur">{replayErreur}</p>}
          {replay && (
            <div className="mt-3 rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0B1620] p-4" data-testid="cognition-replay-resultat">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-xs font-semibold text-[#F2F6F8]">Rejeu des empreintes</h3>
                <Badge ton={replay.reconstructible ? "ok" : "danger"}>{replay.reconstructible ? "Reconstructible" : "Non reconstructible"}</Badge>
              </div>
              <p className="mt-2 font-code text-[10px] text-[#7C93A8]" data-testid="cognition-replay-comptes">{texte(replay.etapes)} étape(s) · {texte(replay.evenements)} événement(s)</p>
              <dl className="mt-2 space-y-1.5 text-[11px]">
                <div className="flex items-center justify-between gap-3"><dt className="text-[#94A3B8]">Empreinte de contexte</dt><dd className="font-code text-[10px] text-[#D8E2EA]">{replay.empreintes?.contexte?.ok === true ? "vérifiée" : replay.empreintes?.contexte?.ok === false ? "non vérifiée" : "absente"}</dd></div>
                <div className="flex items-center justify-between gap-3"><dt className="text-[#94A3B8]">Empreinte de raisonnement</dt><dd className="font-code text-[10px] text-[#D8E2EA]">{replay.empreintes?.raisonnement?.ok === true ? "vérifiée" : replay.empreintes?.raisonnement?.ok === false ? "non vérifiée" : "absente"}</dd></div>
              </dl>
              {(replay.raisons || []).length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-[#FCA5A5]">{(replay.raisons || []).map((raison) => <li key={raison}>{raison}</li>)}</ul>
              )}
              {(replay.limites || []).length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-[#7C93A8]">{(replay.limites || []).map((limite) => <li key={limite}>{limite}</li>)}</ul>
              )}
            </div>
          )}
        </section>

        <section id="memoire" className="rise col-span-12 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] p-5" style={{ animationDelay: "120ms" }} aria-labelledby="cognition-memoire-titre" data-testid="cognition-memoire">
          <EnteteSection
            icone={ShieldCheck}
            titre={<span id="cognition-memoire-titre">Mémoire durable</span>}
            description="Les souvenirs opérationnels sont bornés au tenant et à leur expiration. Le consentement et la provenance restent visibles."
            actions={(
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={exporterMemoire} disabled={exportEnCours}
                  className="flex h-8 items-center gap-1.5 rounded-md border border-[rgba(148,163,184,0.16)] px-2.5 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8] disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="cognition-memoire-export">
                  <DownloadSimple size={13} /> {exportEnCours ? "Export…" : "Exporter"}
                </button>
                <button type="button" onClick={() => { setPurgeConfirmee(true); setPurgeMessage(""); setPurgeErreur(""); }} disabled={purgeEnCours}
                  className="flex h-8 items-center gap-1.5 rounded-md border border-[#F87171]/35 px-2.5 text-xs text-[#FCA5A5] transition-colors hover:bg-[#F87171]/10 disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="cognition-memoire-purge">
                  <Trash size={13} /> Purger
                </button>
              </div>
            )}
          />

          <div className="mt-4 flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="cognition-filtre-scope" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Portée</label>
              <select id="cognition-filtre-scope" value={scope} onChange={(evenement) => changerScope(evenement.target.value)} data-testid="cognition-memoire-filtre-scope"
                className="mt-1 h-8 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2 text-xs text-[#D8E2EA] focus:border-[#60A5FA]/60 focus:outline-none">
                <option value="">Toutes les portées</option>
                {SCOPES.map(([valeur, label]) => <option key={valeur} value={valeur}>{label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="cognition-filtre-classe" className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Classe</label>
              <select id="cognition-filtre-classe" value={classe} onChange={(evenement) => changerClasse(evenement.target.value)} data-testid="cognition-memoire-filtre-classe"
                className="mt-1 h-8 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0B1620] px-2 text-xs text-[#D8E2EA] focus:border-[#60A5FA]/60 focus:outline-none">
                <option value="">Toutes les classes</option>
                {CLASSES.map(([valeur, label]) => <option key={valeur} value={valeur}>{label}</option>)}
              </select>
            </div>
            <span className="font-code text-[10px] text-[#7C93A8]" data-testid="cognition-memoire-compteur">{memoires.length} mémoire(s) affichée(s)</span>
            <span className="font-code text-[10px] text-[#7C93A8]" data-testid="cognition-memoire-selection">{selectionMemoires.size} sélectionnée(s)</span>
          </div>

          {purgeConfirmee && (
            <div className="mt-3 rounded-lg border border-[#F87171]/35 bg-[#F87171]/[0.06] px-3 py-2.5" role="alert" aria-label="Confirmer la purge">
              <p className="text-xs text-[#FCA5A5]">La purge supprime immédiatement les entrées expirées du tenant actif. Confirmer ?</p>
              <div className="mt-2 flex gap-2">
                <button type="button" onClick={purgerMemoire} disabled={purgeEnCours}
                  className="h-7 rounded-md bg-[#F87171] px-2.5 text-[11px] font-semibold text-[#071019] transition-colors hover:bg-[#FCA5A5] disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="cognition-memoire-purge-confirmer">{purgeEnCours ? "Purge…" : "Confirmer la purge"}</button>
                <button type="button" onClick={() => setPurgeConfirmee(false)} disabled={purgeEnCours}
                  className="h-7 rounded-md border border-[rgba(148,163,184,0.2)] px-2.5 text-[11px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8] disabled:cursor-not-allowed disabled:opacity-50"
                  data-testid="cognition-memoire-purge-annuler">Annuler</button>
              </div>
            </div>
          )}

          {purgeMessage && <p className="mt-2 text-xs text-[#6EE7B7]" role="status" data-testid="cognition-memoire-purge-succes">{purgeMessage}</p>}
          {purgeErreur && <p className="mt-2 text-xs text-[#FCA5A5]" role="alert" data-testid="cognition-memoire-purge-erreur">{purgeErreur}</p>}
          {exportMessage && <p className="mt-2 text-xs text-[#93C5FD]" role="status" data-testid="cognition-memoire-export-succes">{exportMessage}</p>}
          {exportErreur && <p className="mt-2 text-xs text-[#FCA5A5]" role="alert" data-testid="cognition-memoire-export-erreur">{exportErreur}</p>}

          {chargementMemoire && <p className="mt-3 text-xs text-[#7C93A8]" role="status" data-testid="cognition-memoire-chargement">Chargement de la mémoire durable…</p>}
          {!chargementMemoire && erreurMemoire && (
            <div className="mt-3" data-testid="cognition-memoire-erreur">
              <p className="text-xs text-[#FCA5A5]" role="alert">{erreurMemoire}</p>
              <button type="button" onClick={() => setRechargementMemoire((valeur) => valeur + 1)} className="mt-2 h-7 rounded-md border border-[rgba(148,163,184,0.2)] px-2.5 text-[11px] text-[#94A3B8] hover:text-[#F2F6F8]" data-testid="cognition-memoire-reessayer">Réessayer</button>
            </div>
          )}
          {!chargementMemoire && !erreurMemoire && memoires.length === 0 && (
            <div className="mt-3"><EtatVide testid="cognition-memoire-vide">Aucune mémoire durable ne correspond à ce filtre.</EtatVide></div>
          )}

          {!chargementMemoire && !erreurMemoire && memoires.length > 0 && (
            <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
              <ul className="space-y-2" aria-label="Mémoires durables">
                {memoires.map((memoire) => {
                  const selectionnee = selectionMemoires.has(memoire.id);
                  return (
                    <li key={memoire.id} className={`rounded-lg border px-3 py-2.5 transition-colors ${selectionnee ? "border-[#60A5FA]/60 bg-[#0B1620]" : "border-[rgba(148,163,184,0.16)] bg-[#0B1620]"}`} data-testid={`cognition-memoire-${memoire.id}`}>
                      <div className="flex items-start gap-2.5">
                        <input type="checkbox" checked={selectionnee} onChange={() => basculerMemoire(memoire.id)}
                          aria-label={`Sélectionner la mémoire ${memoire.id}`} data-testid={`cognition-memoire-selectionner-${memoire.id}`}
                          className="mt-1 h-3.5 w-3.5 shrink-0 accent-[#60A5FA]" />
                        <div className="min-w-0 flex-1">
                          <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-[#D8E2EA]">{texte(memoire.contenu)}</p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                            <Badge ton="info">{LABELS_SCOPE.get(memoire.scope) || texte(memoire.scope)} · {texte(memoire.scope_id)}</Badge>
                            <Badge>{LABELS_CLASSE.get(memoire.classe) || texte(memoire.classe)}</Badge>
                            <Badge ton={memoire.consentement ? "ok" : "alerte"}>{memoire.consentement ? "Consentement explicite" : "Sans consentement"}</Badge>
                          </div>
                          <p className="mt-1.5 break-all font-code text-[10px] text-[#7C93A8]">
                            {texte(memoire.id)} · provenance : {texte(memoire.provenance) || "—"}
                          </p>
                          <p className="mt-0.5 font-code text-[10px] text-[#7C93A8]">
                            Confiance : {typeof memoire.confiance === "number" ? Math.round(memoire.confiance * 100) : "—"} % · expire le {dateCourte(memoire.expire_le)} · créée le {dateCourte(memoire.cree_le)}
                          </p>
                          {memoire.consenti_le && <p className="mt-0.5 font-code text-[10px] text-[#6EE7B7]">Consenti le {dateCourte(memoire.consenti_le)}</p>}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>

              <div className="space-y-4">
                <div className="rounded-lg border border-[rgba(148,163,184,0.16)] bg-[#0B1620] p-4" data-testid="cognition-consolidation">
                  <h3 className="text-xs font-semibold text-[#F2F6F8]">Consolidation</h3>
                  <p className="mt-1 text-[11px] leading-relaxed text-[#7C93A8]">Seules les mémoires cochées sont comparées. Les doublons et conflits sont proposés ; aucune écriture n'a lieu avant votre validation.</p>
                  <button type="button" onClick={proposerConsolidation} disabled={consolidationEnCours || memoiresSelectionnees.length < 2}
                    className="mt-3 flex h-8 items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:cursor-not-allowed disabled:opacity-50"
                    data-testid="cognition-consolidation-proposer">
                    <Flask size={13} /> {consolidationEnCours ? "Analyse…" : "Proposer la consolidation"}
                  </button>
                  {memoiresSelectionnees.length < 2 && <p className="mt-1.5 text-[10px] text-[#7C93A8]">Sélectionnez au moins deux mémoires.</p>}
                  {consolidationErreur && <p className="mt-2 text-xs text-[#FCA5A5]" role="alert" data-testid="cognition-consolidation-erreur">{consolidationErreur}</p>}
                  {consolidationMessage && <p className="mt-2 text-xs text-[#6EE7B7]" role="status" data-testid="cognition-consolidation-succes">{consolidationMessage}</p>}

                  {proposition && (
                    <div className="mt-3 space-y-3" data-testid="cognition-consolidation-proposition">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Doublons proposés</h4>
                        <Badge ton={groupes.length ? "alerte" : "neutre"}>{groupes.length}</Badge>
                        {groupes.length > 0 && (
                          <button type="button" onClick={basculerTousLesGroupes} className="ml-auto font-code text-[10px] text-[#7C93A8] underline-offset-2 hover:text-[#F2F6F8] hover:underline" data-testid="cognition-consolidation-tout">
                            {groupesChoisis.size === groupes.length ? "Tout désélectionner" : "Tout sélectionner"}
                          </button>
                        )}
                      </div>
                      {groupes.length === 0 && <p className="text-[11px] text-[#7C93A8]">Aucun doublon détecté dans la sélection.</p>}
                      <ul className="space-y-2" aria-label="Groupes de fusion proposés">
                        {groupes.map((groupe) => (
                          <li key={groupe.keep_id} className="rounded-md border border-[rgba(148,163,184,0.14)] px-2.5 py-2" data-testid={`cognition-groupe-${groupe.keep_id}`}>
                            <label className="flex items-start gap-2 text-[11px] text-[#D8E2EA]">
                              <input type="checkbox" checked={groupesChoisis.has(groupe.keep_id)} onChange={() => basculerGroupe(groupe.keep_id)}
                                aria-label={`Appliquer le groupe qui garde ${groupe.keep_id}`} className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[#60A5FA]"
                                data-testid={`cognition-groupe-appliquer-${groupe.keep_id}`} />
                              <span className="min-w-0">
                                <span className="block break-all font-code text-[10px] text-[#BFDBFE]">Garder {groupe.keep_id}</span>
                                <span className="mt-0.5 block break-all font-code text-[10px] text-[#7C93A8]">Retirer {(groupe.remove_ids || []).join(", ") || "—"}</span>
                                <span className="mt-1 block text-[11px] text-[#94A3B8]">{groupe.raison || "Doublon détecté."}</span>
                                <span className="mt-1 block font-code text-[10px] text-[#7C93A8]">Confiance : {typeof groupe.confiance === "number" ? Math.round(groupe.confiance * 100) : "—"} %</span>
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>

                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">Conflits signalés</h4>
                        <Badge ton={conflits.length ? "danger" : "neutre"}>{conflits.length}</Badge>
                      </div>
                      {conflits.length === 0 && <p className="text-[11px] text-[#7C93A8]">Aucun conflit détecté dans la sélection.</p>}
                      <ul className="space-y-2" aria-label="Conflits de consolidation">
                        {conflits.map((conflit, index) => (
                          <li key={`${conflit.type}-${index}`} className="rounded-md border border-[#F87171]/25 bg-[#F87171]/[0.04] px-2.5 py-2" data-testid={`cognition-conflit-${index}`}>
                            <div className="flex flex-wrap items-center gap-1.5">
                              <Badge ton="danger">{texte(conflit.gravite) || "moyenne"}</Badge>
                              <span className="font-code text-[10px] text-[#FCA5A5]">{texte(conflit.type)}</span>
                            </div>
                            <p className="mt-1 break-all font-code text-[10px] text-[#7C93A8]">{(conflit.ids || []).join(" · ") || "—"}</p>
                            <p className="mt-1 text-[11px] text-[#94A3B8]">{texte(conflit.raison)}</p>
                          </li>
                        ))}
                      </ul>

                      {limitesProposition.length > 0 && (
                        <ul className="list-disc space-y-1 pl-4 text-[11px] text-[#7C93A8]">{[...new Set(limitesProposition)].map((limite) => <li key={limite}>{limite}</li>)}</ul>
                      )}

                      <button type="button" onClick={appliquerConsolidation} disabled={applicationEnCours || groupesChoisis.size === 0}
                        className="flex h-8 items-center gap-1.5 rounded-md bg-[#F2B84B] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#FCD34D] disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="cognition-consolidation-appliquer">
                        <Check size={13} weight="bold" /> {applicationEnCours ? "Application…" : "Appliquer les groupes sélectionnés"}
                      </button>
                      {applicationErreur && <p className="text-xs text-[#FCA5A5]" role="alert" data-testid="cognition-consolidation-application-erreur">{applicationErreur}</p>}
                      {application && (
                        <div className="rounded-md border border-[#34D399]/30 bg-[#34D399]/[0.05] px-2.5 py-2 text-[11px] text-[#6EE7B7]" role="status" data-testid="cognition-consolidation-plan">
                          <p>Application explicite enregistrée.</p>
                          <p className="mt-1 font-code text-[10px]">Gardées : {(application.gardees || []).length} · Archivées : {(application.archivees || []).length} · Ignorées : {(application.ignorees || []).length}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
