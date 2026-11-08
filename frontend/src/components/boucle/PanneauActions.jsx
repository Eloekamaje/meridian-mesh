import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  ChartLineUp,
  CheckCircle,
  Lightbulb,
  MagnifyingGlass,
  RocketLaunch,
  Scales,
  WarningCircle,
} from "@phosphor-icons/react";
import { actionsPourObjet, idObjet, statutObjet, titreObjet, typeObjet } from "./boucleUi";

const ICONES = {
  investigation: MagnifyingGlass,
  decision: Scales,
  trancher: Scales,
  initiative: RocketLaunch,
  outcome: ChartLineUp,
  learning: BookOpen,
  situation: Lightbulb,
  expression: Lightbulb,
  scenario: Scales,
  opportunite: Lightbulb,
  risque: WarningCircle,
  statut: ArrowRight,
};

const COULEURS = {
  investigation: "#38BDF8",
  decision: "#F2B84B",
  trancher: "#F2B84B",
  initiative: "#FB923C",
  outcome: "#34D399",
  learning: "#A78BFA",
  situation: "#60A5FA",
  expression: "#22D3EE",
  scenario: "#F2B84B",
  opportunite: "#34D399",
  risque: "#F87171",
  statut: "#A78BFA",
};

const TYPES_FEMININS = new Set([
  "SITUATION", "INVESTIGATION", "DECISION", "INITIATIVE", "EXPRESSION", "OPPORTUNITY",
]);

function libelleObjet(objet) {
  const type = typeObjet(objet);
  const identifiant = idObjet(objet);
  return [type, identifiant].filter(Boolean).join(" ");
}

export default function PanneauActions({
  objet,
  succes,
  onAction,
  onOuvrir,
  verification = false,
  verificationErreur = "",
}) {
  if (!objet) return null;

  const actions = actionsPourObjet(objet);
  const type = typeObjet(objet);
  const identifiantCourant = idObjet(objet);
  const identifiantSucces = succes?.objet ? idObjet(succes.objet) : null;
  const nouvelObjet = Boolean(identifiantSucces && identifiantSucces !== identifiantCourant);
  const typeSucces = succes?.objet ? typeObjet(succes.objet) : "";
  const accord = TYPES_FEMININS.has(typeSucces) ? "e" : "";

  return (
    <section
      className="mt-5 rounded-xl border border-[rgba(148,163,184,0.16)] bg-[#0B1620] p-3"
      aria-labelledby="boucle-actions-titre"
      data-testid="boucle-actions"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3
            id="boucle-actions-titre"
            className="font-code text-[10px] uppercase tracking-[0.22em] text-[#94A3B8]"
          >
            Prochaine étape
          </h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[#7C93A8]">
            {actions.length > 0
              ? "La transition disponible dépend du type et du statut de cet objet."
              : "Aucune transition n'est disponible depuis cet objet."}
          </p>
        </div>
        {statutObjet(objet) && (
          <span className="shrink-0 rounded border border-[rgba(148,163,184,0.18)] px-1.5 py-px font-code text-[9px] uppercase tracking-wider text-[#94A3B8]">
            {statutObjet(objet)}
          </span>
        )}
      </div>

      {verification && (
        <p
          role="status"
          data-testid="boucle-verification-source"
          className="mt-3 rounded-md border border-[#60A5FA]/25 bg-[#60A5FA]/[0.06] px-2.5 py-1.5 text-[11px] text-[#BFDBFE]"
        >
          Vérification de la source…
        </p>
      )}

      {!verification && verificationErreur && (
        <p
          role="alert"
          data-testid="boucle-verification-erreur"
          className="mt-3 rounded-md border border-[#F87171]/30 bg-[#F87171]/[0.06] px-2.5 py-1.5 text-[11px] text-[#FCA5A5]"
        >
          {verificationErreur}
        </p>
      )}

      {succes && (
        <div
          role="status"
          data-testid="boucle-transition-succes"
          className="mt-3 rounded-lg border border-[#34D399]/30 bg-[#34D399]/[0.06] px-3 py-2"
        >
          <p className="flex items-start gap-1.5 text-[11px] text-[#6EE7B7]">
            <CheckCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              {nouvelObjet
                ? `${libelleObjet(succes.objet)} enregistré${accord}. ${titreObjet(succes.objet)}`
                : "Transition enregistrée."}
            </span>
          </p>
          {nouvelObjet && onOuvrir && (
            <button
              type="button"
              onClick={() => onOuvrir(succes.objet)}
              data-testid="boucle-transition-succes-ouvrir"
              className="mt-1.5 flex items-center gap-1 rounded-md border border-[#34D399]/40 px-2 py-1 text-[10px] font-semibold text-[#6EE7B7] transition-colors hover:bg-[#34D399]/10"
            >
              Ouvrir l'objet créé <ArrowRight size={10} aria-hidden="true" />
            </button>
          )}
        </div>
      )}

      {actions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {actions.map((action) => {
            const Icone = ICONES[action.icone] || ArrowUpRight;
            const couleur = COULEURS[action.icone] || "#60A5FA";
            return (
              <button
                key={action.id}
                type="button"
                onClick={() => onAction(action.id)}
                disabled={verification}
                aria-disabled={verification ? "true" : undefined}
                data-testid={action.testid}
                title={verification ? "Vérification de la source…" : action.description}
                className="flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-semibold transition-colors disabled:cursor-wait disabled:opacity-50"
                style={{
                  borderColor: `${couleur}55`,
                  backgroundColor: `${couleur}0F`,
                  color: couleur,
                }}
              >
                <Icone size={12} aria-hidden="true" /> {action.libelle}
              </button>
            );
          })}
        </div>
      )}

      {actions.length === 0 && type === "LEARNING" && (
        <p
          className="mt-3 flex items-center gap-1.5 font-code text-[10px] text-[#7C93A8]"
          data-testid="boucle-actions-termine"
        >
          <CheckCircle size={12} aria-hidden="true" /> Ce learning clôt la chaîne.
        </p>
      )}

      {actions.length === 0 && type !== "LEARNING" && (
        <p className="mt-3 font-code text-[10px] text-[#7C93A8]" data-testid="boucle-actions-termine">
          Aucune transition disponible pour ce type d'objet.
        </p>
      )}
    </section>
  );
}
