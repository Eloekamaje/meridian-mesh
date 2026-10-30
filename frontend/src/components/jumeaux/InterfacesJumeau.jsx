import { useEffect, useState } from "react";
import { ArrowClockwise, ArrowsLeftRight, FileCode, PlugsConnected, Pulse, WarningCircle } from "@phosphor-icons/react";
import api from "@/lib/api";

const BORDURE = "border-[rgba(148,163,184,0.16)]";
const FOCUS = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#60A5FA]";
const ETIQUETTE = "font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]";

const MODES = {
  declared: ["déclaré", "#60A5FA"],
  observed: ["observé", "#34D399"],
  inferred: ["inféré", "#F2B84B"],
};
const STATUTS_RUN = {
  ok: ["ok", "#34D399"],
  partial: ["partiel", "#F2B84B"],
  error: ["en erreur", "#F87171"],
};
const SEVERITES = {
  info: ["info", "#7C93A8"],
  warning: ["avertissement", "#F2B84B"],
  breaking: ["rupture", "#F87171"],
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
const METHODES = {
  GET: "#34D399",
  POST: "#60A5FA",
  PUT: "#F2B84B",
  PATCH: "#F2B84B",
  DELETE: "#F87171",
  HEAD: "#7C93A8",
  OPTIONS: "#7C93A8",
};

const CLES_SECRETES = new Set(["pwd", "pass", "auth", "apikey", "api_key", "api-key", "access_key", "private_key", "key"]);
const MARQUEURS_SECRETS = /password|passwd|secret|token|credential|authorization/i;

// Une assertion peut citer une URL : on retire ses identifiants et on masque les paramètres sensibles avant affichage.
function sansSecret(valeur) {
  if (typeof valeur !== "string" || !/^https?:\/\//i.test(valeur.trim())) return valeur;
  try {
    const url = new URL(valeur.trim());
    url.username = "";
    url.password = "";
    url.hash = "";
    for (const cle of [...url.searchParams.keys()]) {
      const norme = decodeURIComponent(cle).trim().toLowerCase();
      if (CLES_SECRETES.has(norme) || norme.endsWith("_key") || norme.endsWith("-key") || MARQUEURS_SECRETS.test(norme)) {
        url.searchParams.set(cle, "***");
      }
    }
    return url.toString();
  } catch {
    return valeur;
  }
}

// Valeur affichable sans jamais interpréter de HTML : les données du serveur restent du texte.
function texte(valeur, max = 160) {
  if (valeur == null || valeur === "") return "—";
  let brut;
  if (typeof valeur === "string") brut = sansSecret(valeur);
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
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? String(iso) : date.toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });
}

function confiance(valeur) {
  const nombre = Number(valeur);
  if (!Number.isFinite(nombre)) return "—";
  return `${Math.round((nombre <= 1 ? nombre : nombre / 100) * 100)} %`;
}

function Badge({ texte: libelle, couleur }) {
  return (
    <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase tracking-wider"
      style={{ color: couleur, borderColor: `${couleur}44`, backgroundColor: `${couleur}12` }}>
      {libelle}
    </span>
  );
}

function MessageVide({ children }) {
  return <p className="mt-1.5 text-xs text-[#7C93A8]">{children}</p>;
}

export default function InterfacesJumeau({ jid }) {
  const [version, setVersion] = useState(0);
  const [etat, setEtat] = useState({ donnees: null, erreur: null, chargement: true });

  useEffect(() => {
    if (!jid) return undefined;
    let actif = true;
    setEtat({ donnees: null, erreur: null, chargement: true });
    api.get(`/jumeaux/${encodeURIComponent(jid)}/interfaces`)
      .then(({ data }) => actif && setEtat({ donnees: data, erreur: null, chargement: false }))
      .catch((e) => actif && setEtat({
        donnees: null,
        erreur: e.response?.data?.detail || "Interfaces indisponibles à ce niveau d'autorisation.",
        chargement: false,
      }));
    return () => { actif = false; };
  }, [jid, version]);

  if (etat.chargement) {
    return (
      <div className={ETIQUETTE} data-testid="interfaces-jumeau">
        <p data-testid="interfaces-chargement">Lecture des interfaces et du dernier run de découverte…</p>
      </div>
    );
  }

  if (etat.erreur) {
    return (
      <div className={`rounded-lg border border-[#F87171]/25 bg-[#F87171]/[0.05] p-4`} data-testid="interfaces-jumeau">
        <div className="flex items-start gap-2" data-testid="interfaces-erreur">
          <WarningCircle size={15} className="mt-0.5 shrink-0 text-[#F87171]" aria-hidden />
          <div>
            <p className="text-xs text-[#F87171]">{etat.erreur}</p>
            <button type="button" onClick={() => setVersion((v) => v + 1)} data-testid="interfaces-reessayer"
              className={`mt-2 flex items-center gap-1.5 rounded border ${BORDURE} px-2 py-1 text-[11px] text-[#94A3B8] transition-colors hover:text-[#F2F6F8] ${FOCUS}`}>
              <ArrowClockwise size={12} aria-hidden /> Réessayer
            </button>
          </div>
        </div>
      </div>
    );
  }

  const interfaces = etat.donnees?.interfaces || {};
  const contrats = Array.isArray(interfaces.contracts) ? interfaces.contracts : [];
  const operations = Array.isArray(interfaces.operations) ? interfaces.operations : [];
  const bindings = Array.isArray(interfaces.bindings) ? interfaces.bindings : [];
  const assertions = Array.isArray(interfaces.assertions) ? interfaces.assertions : [];
  const runs = Array.isArray(etat.donnees?.runs) ? etat.donnees.runs : [];
  const run = runs[0] || null;
  const stats = run?.stats && typeof run.stats === "object" && !Array.isArray(run.stats) ? run.stats : {};
  const changes = Array.isArray(run?.changes) ? run.changes : [];
  const impacts = Array.isArray(run?.impacts) ? run.impacts : [];
  const vide = !contrats.length && !operations.length && !bindings.length && !assertions.length && !runs.length;

  if (vide) {
    return (
      <div className={`rounded-lg border ${BORDURE} p-4`} data-testid="interfaces-jumeau">
        <p className="text-xs text-[#94A3B8]" data-testid="interfaces-vide">
          Aucune interface découverte pour l'instant. Lancez une découverte pour lire les contrats, opérations et
          assertions de cette application, et laisser un premier DiscoveryRun.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="interfaces-jumeau">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-code text-[10px] text-[#7C93A8]" data-testid="interfaces-resume">
        <span>{contrats.length} contrat{contrats.length > 1 ? "s" : ""}</span>
        <span>{operations.length} opération{operations.length > 1 ? "s" : ""}</span>
        <span>{assertions.length} assertion{assertions.length > 1 ? "s" : ""}</span>
        {bindings.length > 0 && <span>{bindings.length} binding{bindings.length > 1 ? "s" : ""}</span>}
        <span className="ml-auto">Application {etat.donnees?.application_id || jid}{etat.donnees?.tenant ? ` · tenant ${etat.donnees.tenant}` : ""}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-label="Contrats d'interface">
          <div className={ETIQUETTE}><FileCode size={12} className="mr-1 inline" aria-hidden /> Contrats</div>
          {contrats.length === 0 && <MessageVide>Aucun contrat découvert.</MessageVide>}
          <ul className="mt-1.5 space-y-1.5">
            {contrats.map((contrat, i) => (
              <li key={contrat.id || i} className={`rounded border ${BORDURE} px-3 py-2`} data-testid="interfaces-contrat">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-[#F2F6F8]">{String(contrat.format || "format inconnu").toUpperCase()}</span>
                  <span className="font-code text-[10px] text-[#94A3B8]">{contrat.version ? `v${contrat.version}` : "version non déclarée"}</span>
                  <span className="ml-auto"><Badge texte={contrat.environment || "environnement inconnu"} couleur="#60A5FA" /></span>
                </div>
                {contrat.locator && (
                  <div className="mt-1 break-all font-code text-[10px] text-[#7C93A8]" title={contrat.locator}>
                    {texte(contrat.locator, 120)}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="Opérations d'interface">
          <div className={ETIQUETTE}><PlugsConnected size={12} className="mr-1 inline" aria-hidden /> Opérations</div>
          {operations.length === 0 && <MessageVide>Aucune opération découverte.</MessageVide>}
          <ul className="mt-1.5 max-h-72 space-y-1 overflow-y-auto pr-1">
            {operations.map((operation, i) => {
              const methode = String(operation.method || operation.protocol || "?").toUpperCase();
              const couleur = METHODES[methode] || "#94A3B8";
              return (
                <li key={operation.id || i} className={`flex items-start gap-2 rounded border ${BORDURE} px-2.5 py-1.5`} data-testid="interfaces-operation">
                  <span className="w-14 shrink-0 rounded border px-1 py-0.5 text-center font-code text-[9px] font-semibold"
                    style={{ color: couleur, borderColor: `${couleur}44`, backgroundColor: `${couleur}12` }}>
                    {methode}
                  </span>
                  <div className="min-w-0">
                    <div className="break-all font-code text-[11px] text-[#F2F6F8]">{operation.path || "chemin non déclaré"}</div>
                    <div className="font-code text-[9px] text-[#7C93A8]">
                      {[operation.name, operation.protocol, operation.environment].filter(Boolean).join(" · ") || "—"}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      </div>

      <section aria-label="Assertions d'interface">
        <div className={ETIQUETTE}><ArrowsLeftRight size={12} className="mr-1 inline" aria-hidden /> Assertions</div>
        {assertions.length === 0 && <MessageVide>Aucune assertion découverte.</MessageVide>}
        <ul className="mt-1.5 max-h-72 space-y-1 overflow-y-auto pr-1">
          {assertions.map((assertion, i) => {
            const mode = MODES[assertion.mode] || [assertion.mode || "mode inconnu", "#7C93A8"];
            return (
              <li key={`${assertion.subject || ""}:${assertion.predicate || ""}:${i}`} className={`rounded border ${BORDURE} px-2.5 py-1.5`} data-testid="interfaces-assertion">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-code text-[10px] font-semibold text-[#F2F6F8]">{assertion.predicate || "prédicat inconnu"}</span>
                  <span className="break-all font-code text-[10px] text-[#94A3B8]">{texte(assertion.object, 100)}</span>
                  <Badge texte={mode[0]} couleur={mode[1]} />
                  <span className="ml-auto font-code text-[9px] text-[#7C93A8]">
                    {assertion.source || "source inconnue"} · {confiance(assertion.confidence)}
                  </span>
                </div>
                <div className="mt-0.5 break-all font-code text-[9px] text-[#7C93A8]">
                  sujet : {texte(assertion.subject, 80)}{assertion.environment ? ` · ${assertion.environment}` : ""}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className={`rounded-lg border ${BORDURE} p-3`} aria-label="Dernier DiscoveryRun" data-testid="interfaces-run">
        <div className="flex flex-wrap items-center gap-2">
          <Pulse size={13} className="text-[#7C93A8]" aria-hidden />
          <span className="text-xs font-semibold text-[#F2F6F8]">Dernier DiscoveryRun</span>
          {run ? <Badge texte={STATUTS_RUN[run.status]?.[0] || run.status || "inconnu"} couleur={STATUTS_RUN[run.status]?.[1] || "#7C93A8"} /> : <span className="font-code text-[9px] text-[#7C93A8]">aucun run</span>}
          {run && <span className="ml-auto font-code text-[10px] text-[#7C93A8]">{dateCourte(run.started_at)}</span>}
        </div>

        {!run && <MessageVide>Aucun DiscoveryRun enregistré pour ce jumeau.</MessageVide>}

        {run && (
          <>
            <p className="mt-2 font-code text-[10px] text-[#94A3B8]">
              {(stats.contracts ?? 0)} contrats · {(stats.operations ?? 0)} opérations · {(stats.assertions ?? 0)} assertions
              {run.source ? ` · source ${run.source}` : ""}{run.environment ? ` · ${run.environment}` : ""}
            </p>
            {run.status === "error" && (
              <p className="mt-1 text-xs text-[#F87171]">Le run s'est arrêté sur une erreur ; le graphe précédent reste la référence.</p>
            )}

            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <div className={ETIQUETTE}>Changements ({changes.length})</div>
                {changes.length === 0 && <MessageVide>Aucun changement détecté.</MessageVide>}
                <ul className="mt-1 max-h-56 space-y-1 overflow-y-auto pr-1">
                  {changes.map((change, i) => {
                    const severite = SEVERITES[change.severity] || [change.severity || "info", "#7C93A8"];
                    return (
                      <li key={i} className="flex flex-wrap items-center gap-1.5 text-[10px]" data-testid="interfaces-run-changement">
                        <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: severite[1] }} aria-hidden />
                        <span className="font-code text-[#F2F6F8]">{CHANGEMENTS[change.type] || change.type || "changement"}</span>
                        <span className="font-code text-[#7C93A8]">{texte(change.subject, 50)}</span>
                        {(change.before != null || change.after != null) && (
                          <span className="font-code text-[#7C93A8]">{texte(change.before, 40)} → {texte(change.after, 40)}</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div>
                <div className={ETIQUETTE}>Impacts ({impacts.length})</div>
                {impacts.length === 0 && <MessageVide>Aucun consommateur impacté détecté.</MessageVide>}
                <ul className="mt-1 max-h-56 space-y-1 overflow-y-auto pr-1">
                  {impacts.map((impact, i) => {
                    const severite = SEVERITES[impact.severity] || [impact.severity || "info", "#7C93A8"];
                    return (
                      <li key={i} className={`rounded border ${BORDURE} px-2 py-1 text-[10px]`} data-testid="interfaces-run-impact">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="font-code text-[#F2F6F8]">{texte(impact.application, 50)}</span>
                          <Badge texte={severite[0]} couleur={severite[1]} />
                          <span className="break-all font-code text-[#94A3B8]">{texte(impact.operation, 80)}</span>
                        </div>
                        {impact.raison && <div className="mt-0.5 text-[#7C93A8]">{texte(impact.raison, 160)}</div>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
