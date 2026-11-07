import { useEffect, useRef, useState } from "react";
import { ChartBar, CircleNotch, WarningCircle } from "@phosphor-icons/react";
import { boucleApi } from "@/lib/api";
import {
  idObjet,
  messageErreurTransition,
  texte,
  typeObjet,
} from "./boucleUi";

const METRIQUES = [
  ["valeur_estimee", "Valeur estimée"],
  ["cout_estime", "Coût estimé"],
  ["delai_jours", "Délai (jours)"],
  ["risque", "Risque"],
  ["complexite", "Complexité"],
];

function identifiantScenario(scenario) {
  return idObjet(scenario);
}

function titreScenario(scenario) {
  return texte(scenario?.titre).trim() || identifiantScenario(scenario) || "Scénario sans titre";
}

function formaterNombre(valeur) {
  if (valeur === null || valeur === undefined || valeur === "") return "—";
  const nombre = Number(valeur);
  if (!Number.isFinite(nombre)) return texte(valeur);
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 }).format(nombre);
}

function formaterEcart(ecart) {
  if (!ecart || ecart.delta === null || ecart.delta === undefined) return "écart inconnu";
  if (ecart.delta === 0) return "identique";
  const signe = ecart.delta > 0 ? "+" : "";
  const pourcentage = ecart.delta_pct === null || ecart.delta_pct === undefined
    ? ""
    : ` (${signe}${formaterNombre(ecart.delta_pct)} %)`;
  return `${signe}${formaterNombre(ecart.delta)}${pourcentage}`;
}

function CelluleMetrique({ scenario, nom, estReference }) {
  const ecart = scenario?.ecarts?.[nom];
  if (estReference || !ecart) {
    return <span>{formaterNombre(scenario?.[nom])}</span>;
  }
  return (
    <span className="flex flex-col">
      <span>{formaterNombre(scenario?.[nom])}</span>
      <span className="font-code text-[9px] text-[#7C93A8]">{formaterEcart(ecart)}</span>
    </span>
  );
}

export default function ComparaisonScenarios({ objet }) {
  const identifiant = idObjet(objet);
  const type = typeObjet(objet);
  const pertinent = Boolean(identifiant) && ["INVESTIGATION", "DECISION"].includes(type);
  const monte = useRef(true);
  const [etat, setEtat] = useState({ chargement: false, erreur: "", scenarios: [] });
  const [selection, setSelection] = useState([]);
  const [reference, setReference] = useState("");
  const [comparaison, setComparaison] = useState(null);
  const [comparaisonErreur, setComparaisonErreur] = useState("");
  const [comparaisonEnCours, setComparaisonEnCours] = useState(false);

  useEffect(() => {
    monte.current = true;
    return () => { monte.current = false; };
  }, []);

  useEffect(() => {
    if (!pertinent) return undefined;
    let annule = false;
    setEtat({ chargement: true, erreur: "", scenarios: [] });
    setSelection([]);
    setReference("");
    setComparaison(null);
    setComparaisonErreur("");
    const params = type === "INVESTIGATION"
      ? { investigation_id: identifiant }
      : { decision_id: identifiant };

    Promise.resolve(boucleApi.listerScenarios(params))
      .then((reponse) => {
        if (annule) return;
        const scenarios = Array.isArray(reponse?.data?.scenarios)
          ? reponse.data.scenarios
          : [];
        setEtat({ chargement: false, erreur: "", scenarios });
        setSelection(scenarios.map(identifiantScenario).filter(Boolean));
        setReference(identifiantScenario(scenarios[0]) || "");
      })
      .catch((cause) => {
        if (annule) return;
        setEtat({
          chargement: false,
          erreur: messageErreurTransition(
            cause, "Les scénarios de cet objet sont momentanément indisponibles."),
          scenarios: [],
        });
      });
    return () => { annule = true; };
  }, [identifiant, pertinent, type]);

  if (!pertinent) return null;

  const referenceEffective = selection.includes(reference) ? reference : (selection[0] || "");
  const basculer = (scenarioId) => {
    setComparaison(null);
    setComparaisonErreur("");
    setSelection((avant) => (
      avant.includes(scenarioId)
        ? avant.filter((element) => element !== scenarioId)
        : [...avant, scenarioId]
    ));
  };

  const comparer = async () => {
    if (selection.length < 2 || comparaisonEnCours) return;
    setComparaisonEnCours(true);
    setComparaisonErreur("");
    try {
      const reponse = await boucleApi.comparerScenarios({
        scenario_ids: selection,
        ...(referenceEffective ? { reference_id: referenceEffective } : {}),
      });
      if (!monte.current) return;
      setComparaison(reponse?.data || null);
    } catch (cause) {
      if (!monte.current) return;
      setComparaisonErreur(messageErreurTransition(
        cause, "La comparaison des scénarios n'a pas pu être calculée."));
    } finally {
      if (monte.current) setComparaisonEnCours(false);
    }
  };

  const scenarios = etat.scenarios;
  const lignes = Array.isArray(comparaison?.scenarios) ? comparaison.scenarios : [];
  const referenceAffichee = comparaison?.reference?.id || referenceEffective;

  return (
    <section
      className="mt-5 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0B1620] p-3"
      aria-labelledby="boucle-comparaison-titre"
      data-testid="boucle-comparaison"
    >
      <div className="flex items-start gap-2">
        <ChartBar size={14} className="mt-0.5 shrink-0 text-[#60A5FA]" aria-hidden="true" />
        <div className="min-w-0">
          <h3
            id="boucle-comparaison-titre"
            className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]"
          >
            Comparer les scénarios
          </h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[#7C93A8]">
            Sélectionnez au moins deux scénarios liés à cet objet, puis choisissez la référence des écarts.
          </p>
        </div>
      </div>

      {etat.chargement && (
        <p
          role="status"
          data-testid="boucle-comparaison-chargement"
          className="mt-3 flex items-center gap-1.5 font-code text-[10px] text-[#7C93A8]"
        >
          <CircleNotch size={12} className="animate-spin" aria-hidden="true" /> Chargement des scénarios…
        </p>
      )}

      {!etat.chargement && etat.erreur && (
        <p
          role="alert"
          data-testid="boucle-comparaison-erreur"
          className="mt-3 rounded-md border border-[#F87171]/30 bg-[#F87171]/[0.06] px-2.5 py-1.5 text-[11px] text-[#FCA5A5]"
        >
          {etat.erreur}
        </p>
      )}

      {!etat.chargement && !etat.erreur && scenarios.length === 0 && (
        <p
          data-testid="boucle-comparaison-vide"
          className="mt-3 rounded-md border border-[rgba(148,163,184,0.16)] px-2.5 py-2 text-[11px] text-[#7C93A8]"
        >
          Aucun scénario lié à cet objet. Créez-en au moins deux pour lancer une comparaison.
        </p>
      )}

      {!etat.chargement && !etat.erreur && scenarios.length > 0 && (
        <>
          <fieldset className="mt-3">
            <legend className="font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
              Scénarios à comparer
            </legend>
            <div className="mt-1 space-y-1">
              {scenarios.map((scenario) => {
                const scenarioId = identifiantScenario(scenario);
                return (
                  <label
                    key={scenarioId}
                    className="flex items-start gap-2 rounded-md border border-[rgba(148,163,184,0.12)] px-2 py-1.5 text-[11px] text-[#D8E2EA]"
                  >
                    <input
                      type="checkbox"
                      checked={selection.includes(scenarioId)}
                      onChange={() => basculer(scenarioId)}
                      data-testid={`boucle-comparaison-scenario-${scenarioId}`}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[#60A5FA]"
                    />
                    <span className="min-w-0">
                      <span className="block truncate">{titreScenario(scenario)}</span>
                      <span className="block font-code text-[9px] text-[#7C93A8]">
                        {texte(scenario.statut) || "DRAFT"}
                        {scenario.valeur_estimee !== null && scenario.valeur_estimee !== undefined
                          ? ` · valeur ${formaterNombre(scenario.valeur_estimee)}`
                          : ""}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {scenarios.length === 1 && (
            <p className="mt-2 font-code text-[10px] text-[#7C93A8]" data-testid="boucle-comparaison-incomplet">
              Un second scénario est nécessaire pour comparer.
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-end gap-2">
            <div>
              <label
                htmlFor="boucle-comparaison-reference"
                className="block font-code text-[9px] uppercase tracking-wider text-[#7C93A8]"
              >
                Référence des écarts
              </label>
              <select
                id="boucle-comparaison-reference"
                value={referenceEffective}
                onChange={(evenement) => setReference(evenement.target.value)}
                disabled={selection.length === 0}
                data-testid="boucle-comparaison-reference"
                className="mt-1 h-8 rounded-md border border-[rgba(148,163,184,0.18)] bg-[#0B1620] px-2 text-xs text-[#F2F6F8] focus:border-[#60A5FA]/60 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
              >
                {scenarios
                  .filter((scenario) => selection.includes(identifiantScenario(scenario)))
                  .map((scenario) => (
                    <option key={identifiantScenario(scenario)} value={identifiantScenario(scenario)}>
                      {titreScenario(scenario)}
                    </option>
                  ))}
              </select>
            </div>
            <button
              type="button"
              onClick={comparer}
              disabled={selection.length < 2 || comparaisonEnCours}
              data-testid="boucle-comparaison-lancer"
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {comparaisonEnCours && <CircleNotch size={12} className="animate-spin" aria-hidden="true" />}
              {comparaisonEnCours ? "Comparaison…" : "Comparer"}
            </button>
          </div>
        </>
      )}

      {comparaisonErreur && (
        <p
          role="alert"
          data-testid="boucle-comparaison-erreur"
          className="mt-3 flex items-start gap-1.5 rounded-md border border-[#F87171]/30 bg-[#F87171]/[0.06] px-2.5 py-1.5 text-[11px] text-[#FCA5A5]"
        >
          <WarningCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{comparaisonErreur}</span>
        </p>
      )}

      {lignes.length > 0 && (
        <div className="mt-3 overflow-x-auto" data-testid="boucle-comparaison-resultat">
          <table className="w-full border-collapse text-left text-[11px] text-[#D8E2EA]">
            <caption className="sr-only">
              Comparaison de {lignes.length} scénarios, référence {referenceAffichee}.
            </caption>
            <thead>
              <tr className="border-b border-[rgba(148,163,184,0.18)] font-code text-[9px] uppercase tracking-wider text-[#7C93A8]">
                <th scope="col" className="py-1.5 pr-2">Scénario</th>
                <th scope="col" className="py-1.5 pr-2">Statut</th>
                {METRIQUES.map(([, libelle]) => (
                  <th key={libelle} scope="col" className="py-1.5 pr-2">{libelle}</th>
                ))}
                <th scope="col" className="py-1.5">Réversibilité</th>
              </tr>
            </thead>
            <tbody>
              {lignes.map((scenario) => {
                const estReference = identifiantScenario(scenario) === referenceAffichee;
                return (
                  <tr
                    key={identifiantScenario(scenario)}
                    data-testid={`boucle-comparaison-ligne-${identifiantScenario(scenario)}`}
                    className={estReference ? "bg-[#60A5FA]/[0.06]" : undefined}
                  >
                    <th scope="row" className="py-1.5 pr-2 font-semibold text-[#F2F6F8]">
                      <span className="block max-w-[12rem] truncate">{titreScenario(scenario)}</span>
                      {estReference && (
                        <span className="mt-0.5 inline-block rounded border border-[#60A5FA]/40 px-1 font-code text-[8px] uppercase tracking-wider text-[#BFDBFE]">
                          Référence
                        </span>
                      )}
                    </th>
                    <td className="py-1.5 pr-2">{texte(scenario.statut) || "—"}</td>
                    {METRIQUES.map(([nom]) => (
                      <td key={nom} className="py-1.5 pr-2">
                        <CelluleMetrique
                          scenario={scenario}
                          nom={nom}
                          estReference={estReference}
                        />
                      </td>
                    ))}
                    <td className="py-1.5">
                      <span>{texte(scenario.reversibilite) || "—"}</span>
                      {!estReference && scenario.ecarts?.reversibilite?.identique === false && (
                        <span className="ml-1 font-code text-[9px] text-[#F2B84B]">≠ référence</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
