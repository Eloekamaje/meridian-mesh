import { useEffect, useState } from "react";
import { ArrowClockwise, ArrowsLeftRight, Crosshair, PlugsConnected, WarningCircle, X } from "@phosphor-icons/react";
import api from "@/lib/api";

const BORDURE = "border-[rgba(148,163,184,0.16)]";
const FOCUS = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]";
const ETIQUETTE = "font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]";

const SEVERITES = {
  info: ["info", "#7C93A8", 2],
  warning: ["avertissement", "#F2B84B", 1],
  breaking: ["rupture", "#F87171", 0],
};
const MODES = {
  declared: ["déclaré", "#60A5FA"],
  observed: ["observé", "#34D399"],
  inferred: ["inféré", "#F2B84B"],
};
const CHANGEMENTS = {
  contract_version: "Version de contrat",
  contract_digest: "Contrat modifié",
  operation_added: "Opération ajoutée",
  operation_removed: "Opération retirée",
  operation_changed: "Opération modifiée",
  binding_added: "Binding ajouté",
  binding_removed: "Binding retiré",
  assertion_added: "Assertion ajoutée",
  assertion_removed: "Assertion retirée",
  assertion_mode_changed: "Mode d'assertion changé",
};

function texte(valeur, max = 180) {
  if (valeur == null || valeur === "") return "—";
  let brut;
  if (typeof valeur === "string") brut = valeur;
  else if (typeof valeur === "number" || typeof valeur === "boolean") brut = String(valeur);
  else {
    try {
      brut = JSON.stringify(valeur);
    } catch {
      brut = String(valeur);
    }
  }
  return brut.length > max ? `${brut.slice(0, max)}…` : brut;
}

function dateCourte(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? String(iso) : date.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

function libelleOperation(operation, operationsParId, identifiant) {
  if (operation && typeof operation === "object") {
    const methode = operation.method || operation.protocol;
    const chemin = operation.path || operation.name || operation.id;
    if (methode && chemin) return `${String(methode).toUpperCase()} ${chemin}`;
    if (chemin) return String(chemin);
  }
  const reference = operationsParId.get(String(identifiant || (typeof operation === "string" ? operation : "") || ""));
  if (reference) {
    const methode = reference.method || reference.protocol;
    const chemin = reference.path || reference.name || reference.id;
    if (methode && chemin) return `${String(methode).toUpperCase()} ${chemin}`;
    if (chemin) return String(chemin);
  }
  if (typeof operation === "string" && operation) return operation;
  return identifiant ? String(identifiant) : "—";
}

function nomApplication(identifiant, jumeauPar) {
  const jumeau = jumeauPar?.(identifiant);
  return jumeau?.nom || texte(identifiant, 60);
}

function Badge({ libelle, couleur }) {
  return (
    <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider"
      style={{ color: couleur, borderColor: `${couleur}44`, backgroundColor: `${couleur}12` }}>
      {libelle}
    </span>
  );
}

function Compte({ testid, valeur }) {
  return <span data-testid={testid} className="rounded border border-[rgba(148,163,184,0.16)] px-2 py-1 text-[#94A3B8]">{valeur}</span>;
}

export default function AtlasInterfaces({
  version = 0,
  jumeauPar,
  setSelection,
  centrerJumeau,
  majUrl,
  onFermer,
  coucheActive = false,
  onBasculerCouche,
  donnees: donneesParent,
  chargement: chargementParent,
  erreur: erreurParent,
  onRecharger,
}) {
  const [rechargement, setRechargement] = useState(0);
  const [etatLocal, setEtatLocal] = useState({ donnees: null, erreur: null, chargement: true });
  const piloteParParent = donneesParent !== undefined || chargementParent !== undefined || erreurParent !== undefined || typeof onRecharger === "function";

  useEffect(() => {
    if (piloteParParent) return undefined;
    let actif = true;
    setEtatLocal({ donnees: null, erreur: null, chargement: true });
    api.get("/mesh/interfaces")
      .then(({ data }) => actif && setEtatLocal({ donnees: data || {}, erreur: null, chargement: false }))
      .catch((e) => actif && setEtatLocal({
        donnees: null,
        erreur: e.response?.data?.detail || "Interfaces et impacts indisponibles.",
        chargement: false,
      }));
    return () => { actif = false; };
  }, [version, rechargement, piloteParParent]);

  const etat = piloteParParent
    ? { donnees: donneesParent ?? null, erreur: erreurParent ?? null, chargement: !!chargementParent }
    : etatLocal;
  const donnees = etat.donnees || {};
  const operations = Array.isArray(donnees.operations) ? donnees.operations : [];
  const edges = Array.isArray(donnees.edges) ? donnees.edges : [];
  const impacts = Array.isArray(donnees.impacts) ? donnees.impacts : [];
  const operationsParId = new Map(operations.map((operation) => [String(operation.id), operation]));
  const declarees = edges.filter((edge) => String(edge.mode || "").toLowerCase() === "declared").length;
  const observees = edges.filter((edge) => String(edge.mode || "").toLowerCase() === "observed").length;
  const impactsTries = [...impacts].sort((a, b) => (SEVERITES[a.severity]?.[2] ?? 3) - (SEVERITES[b.severity]?.[2] ?? 3));
  const vide = !operations.length && !edges.length && !impacts.length;

  const voirSurCarte = (edge) => {
    const ids = [...new Set([edge.source, edge.target].filter((id) => id != null && id !== "").map(String))];
    if (!ids.length) return;
    setSelection?.(ids);
    const cible = jumeauPar?.(edge.target) || jumeauPar?.(edge.source) || null;
    if (cible && centrerJumeau) centrerJumeau(cible);
    else majUrl?.({ sel: ids[ids.length - 1], domaine: null });
  };

  const relancer = () => {
    if (piloteParParent) onRecharger?.();
    else setRechargement((n) => n + 1);
  };

  return (
    <aside
      role="complementary"
      aria-label="Interfaces et impacts du Mesh"
      className="glass absolute bottom-40 right-4 top-16 z-20 flex w-[390px] max-w-[92vw] flex-col overflow-hidden rounded-xl"
      data-testid="atlas-interfaces"
    >
      <div className="flex items-center gap-2 border-b border-[rgba(148,163,184,0.16)] px-4 py-3">
        <PlugsConnected size={15} className="text-[#60A5FA]" aria-hidden />
        <h2 className="min-w-0 flex-1 font-display text-sm font-bold text-[#F2F6F8]">Interfaces &amp; impacts</h2>
        <button
          type="button"
          onClick={onFermer}
          title="Fermer le panneau Interfaces"
          aria-label="Fermer le panneau Interfaces"
          data-testid="atlas-interfaces-fermer"
          className={`rounded-md p-1 text-[#7C93A8] transition-colors hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8] ${FOCUS}`}
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4 text-xs leading-relaxed text-[#D8E2EA]">
        <button
          type="button"
          role="switch"
          aria-checked={!!coucheActive}
          aria-label="Afficher les interfaces sur la carte"
          onClick={onBasculerCouche}
          disabled={!onBasculerCouche}
          data-testid="atlas-interfaces-couche"
          className={`flex w-full items-center justify-between gap-2 rounded-lg border ${BORDURE} px-2.5 py-2 text-left transition-colors ${onBasculerCouche ? "hover:bg-[rgba(148,163,184,0.08)]" : "opacity-50"} ${FOCUS}`}
        >
          <span className="flex items-center gap-1.5 font-code text-[10px] uppercase tracking-[0.12em] text-[#94A3B8]">
            <ArrowsLeftRight size={12} className="text-[#60A5FA]" aria-hidden />
            Afficher sur la carte
          </span>
          <span
            aria-hidden="true"
            className={`relative inline-flex h-4 w-7 shrink-0 rounded-full border transition-colors ${
              coucheActive ? "border-[#60A5FA]/60 bg-[#60A5FA]/25" : "border-[rgba(148,163,184,0.30)] bg-[rgba(148,163,184,0.10)]"
            }`}
          >
            <span
              className={`absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full transition-all ${
                coucheActive ? "left-3.5 bg-[#60A5FA]" : "left-0.5 bg-[#94A3B8]"
              }`}
            />
          </span>
        </button>

        {etat.chargement && (
          <p className={ETIQUETTE} data-testid="atlas-interfaces-chargement">Lecture des interfaces et des impacts…</p>
        )}

        {!etat.chargement && etat.erreur && (
          <div className={`rounded-lg border border-[#F87171]/25 bg-[#F87171]/[0.05] p-3`} data-testid="atlas-interfaces-erreur">
            <div className="flex items-start gap-2">
              <WarningCircle size={15} className="mt-0.5 shrink-0 text-[#F87171]" aria-hidden />
              <div className="min-w-0">
                <p className="text-xs text-[#F87171]">{etat.erreur}</p>
                <button
                  type="button"
                  onClick={relancer}
                  data-testid="atlas-interfaces-reessayer"
                  className={`mt-2 flex items-center gap-1.5 rounded border ${BORDURE} px-2 py-1 text-[11px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8] ${FOCUS}`}
                >
                  <ArrowClockwise size={12} aria-hidden /> Réessayer
                </button>
              </div>
            </div>
          </div>
        )}

        {!etat.chargement && !etat.erreur && vide && (
          <p className="text-xs text-[#94A3B8]" data-testid="atlas-interfaces-vide">
            Aucune interface découverte pour l'instant. Lancez une découverte d'interfaces pour voir les opérations,
            les arêtes entre applications et les impacts des changements.
          </p>
        )}

        {!etat.chargement && !etat.erreur && !vide && (
          <>
            <div className="flex flex-wrap items-center gap-1.5 font-code text-[10px]" data-testid="atlas-interfaces-resume">
              <Compte testid="atlas-interfaces-nb-operations" valeur={`${operations.length} opération${operations.length > 1 ? "s" : ""}`} />
              <Compte testid="atlas-interfaces-nb-aretes-declarees" valeur={`${declarees} arête${declarees > 1 ? "s" : ""} déclarée${declarees > 1 ? "s" : ""}`} />
              <Compte testid="atlas-interfaces-nb-aretes-observees" valeur={`${observees} arête${observees > 1 ? "s" : ""} observée${observees > 1 ? "s" : ""}`} />
              <Compte testid="atlas-interfaces-nb-impacts" valeur={`${impacts.length} impact${impacts.length > 1 ? "s" : ""}`} />
            </div>

            <section aria-label="Impacts des changements d'interface">
              <div className={ETIQUETTE}><WarningCircle size={12} className="mr-1 inline" aria-hidden /> Impacts</div>
              {impactsTries.length === 0 && <p className="mt-1.5 text-xs text-[#7C93A8]">Aucun consommateur impacté détecté.</p>}
              <ul className="mt-1.5 space-y-1.5">
                {impactsTries.map((impact, i) => {
                  const severite = SEVERITES[impact.severity] || [impact.severity || "info", "#7C93A8"];
                  const preuves = Array.isArray(impact.evidence) ? impact.evidence.length : 0;
                  return (
                    <li key={`${impact.application || ""}:${impact.operation || ""}:${impact.run_id || ""}:${i}`}
                      className={`rounded border ${BORDURE} px-2.5 py-2`} data-testid="atlas-interface-impact">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span data-testid="atlas-interface-impact-severite"><Badge libelle={severite[0]} couleur={severite[1]} /></span>
                        <span className="font-code text-[10px] font-semibold text-[#F2F6F8]" data-testid="atlas-interface-impact-application">
                          {nomApplication(impact.application, jumeauPar)}
                        </span>
                        <span className="break-all font-code text-[10px] text-[#94A3B8]" data-testid="atlas-interface-impact-operation">
                          {libelleOperation(impact.operation, operationsParId)}
                        </span>
                        <span className="ml-auto font-code text-[9px] text-[#7C93A8]">
                          {CHANGEMENTS[impact.change_type] || impact.change_type || "changement"}
                        </span>
                      </div>
                      {impact.raison && (
                        <p className="mt-1 text-[11px] leading-snug text-[#94A3B8]" data-testid="atlas-interface-impact-raison">
                          {texte(impact.raison)}
                        </p>
                      )}
                      <div className="mt-1 flex flex-wrap items-center gap-x-2 font-code text-[9px] text-[#7C93A8]">
                        {dateCourte(impact.at) && <span>{dateCourte(impact.at)}</span>}
                        {impact.run_id && <span>run {texte(impact.run_id, 40)}</span>}
                        {preuves > 0 && <span>{preuves} preuve{preuves > 1 ? "s" : ""}</span>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>

            <section aria-label="Arêtes déclarées et observées entre applications">
              <div className={ETIQUETTE}><ArrowsLeftRight size={12} className="mr-1 inline" aria-hidden /> Arêtes</div>
              {edges.length === 0 && <p className="mt-1.5 text-xs text-[#7C93A8]">Aucune arête entre applications.</p>}
              <ul className="mt-1.5 max-h-72 space-y-1.5 overflow-y-auto pr-1">
                {edges.map((edge, i) => {
                  const mode = MODES[String(edge.mode || "").toLowerCase()] || [edge.mode || "mode inconnu", "#7C93A8"];
                  return (
                    <li key={`${edge.source || ""}:${edge.target || ""}:${edge.operation_id || ""}:${i}`}
                      className={`rounded border ${BORDURE} px-2.5 py-2`} data-testid="atlas-interface-edge">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-code text-[10px] font-semibold text-[#F2F6F8]" data-testid="atlas-interface-edge-source">
                          {nomApplication(edge.source, jumeauPar)}
                        </span>
                        <span className="font-code text-[10px] text-[#7C93A8]" aria-hidden>→</span>
                        <span className="font-code text-[10px] font-semibold text-[#F2F6F8]" data-testid="atlas-interface-edge-target">
                          {nomApplication(edge.target, jumeauPar)}
                        </span>
                        <span className="ml-auto" data-testid="atlas-interface-edge-mode"><Badge libelle={mode[0]} couleur={mode[1]} /></span>
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <span className="break-all font-code text-[10px] text-[#94A3B8]" data-testid="atlas-interface-edge-operation">
                          {libelleOperation(edge.operation, operationsParId, edge.operation_id)}
                        </span>
                        <button
                          type="button"
                          onClick={() => voirSurCarte(edge)}
                          data-testid="atlas-interface-edge-voir"
                          className={`ml-auto flex shrink-0 items-center gap-1 rounded border border-[#60A5FA]/40 px-1.5 py-0.5 font-code text-[9px] text-[#60A5FA] transition-colors hover:bg-[#60A5FA]/10 ${FOCUS}`}
                        >
                          <Crosshair size={10} aria-hidden /> Voir sur la carte
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          </>
        )}
      </div>
    </aside>
  );
}
