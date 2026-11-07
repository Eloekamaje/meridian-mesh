import { useEffect, useRef, useState } from "react";
import { CircleNotch, WarningCircle, X } from "@phosphor-icons/react";
const texte = (valeur) => (valeur == null ? "" : String(valeur));

function valeursInitiales(action) {
  const valeurs = {};
  for (const champ of action.champs) {
    valeurs[champ.nom] = "";
  }
  return valeurs;
}

function Champ({ champ, valeur, onChange, desactive }) {
  const id = `boucle-transition-${champ.nom}`;
  const communs = {
    id,
    name: champ.nom,
    value: valeur,
    onChange: (evenement) => onChange(champ.nom, evenement.target.value),
    disabled: desactive,
    required: champ.requis,
    "aria-required": champ.requis ? "true" : undefined,
    "data-testid": id,
    className:
      "mt-1 w-full rounded-md border border-[rgba(148,163,184,0.18)] bg-[#0B1620] px-2.5 text-xs text-[#F2F6F8] placeholder:text-[#7C93A8] transition-colors focus:border-[#60A5FA]/60 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60",
  };

  if (champ.type === "textarea") {
    return (
      <textarea
        {...communs}
        rows={champ.rows || 3}
        maxLength={champ.maxLength}
        placeholder={champ.placeholder}
        className={`${communs.className} py-2`}
      />
    );
  }

  if (champ.type === "select") {
    return (
      <select {...communs} className={`${communs.className} h-9`}>
        <option value="">Sélectionner…</option>
        {(champ.options || []).map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    );
  }

  return (
    <input
      {...communs}
      type="text"
      inputMode={champ.inputMode}
      maxLength={champ.maxLength}
      placeholder={champ.placeholder}
      autoComplete="off"
      className={`${communs.className} h-9`}
    />
  );
}

export default function ModaleTransition({
  action,
  enCours = false,
  erreur = "",
  onFermer,
  onSoumettre,
}) {
  const [valeurs, setValeurs] = useState(() => valeursInitiales(action));
  const dialogue = useRef(null);

  useEffect(() => {
    const champ = dialogue.current?.querySelector("input, textarea, select");
    if (champ) champ.focus();
  }, []);

  useEffect(() => {
    const surTouche = (evenement) => {
      if (evenement.key === "Escape" && !enCours) {
        evenement.preventDefault();
        onFermer();
        return;
      }
      if (evenement.key !== "Tab" || !dialogue.current) return;
      const focusables = [...dialogue.current.querySelectorAll(
        "input:not(:disabled), textarea:not(:disabled), select:not(:disabled), button:not(:disabled)",
      )];
      if (focusables.length === 0) return;
      const premier = focusables[0];
      const dernier = focusables[focusables.length - 1];
      if (evenement.shiftKey && document.activeElement === premier) {
        evenement.preventDefault();
        dernier.focus();
      } else if (!evenement.shiftKey && document.activeElement === dernier) {
        evenement.preventDefault();
        premier.focus();
      }
    };
    document.addEventListener("keydown", surTouche);
    return () => document.removeEventListener("keydown", surTouche);
  }, [enCours, onFermer]);

  const changer = (nom, valeur) => {
    setValeurs((avant) => ({ ...avant, [nom]: valeur }));
  };

  const soumettre = (evenement) => {
    evenement.preventDefault();
    if (enCours) return;
    onSoumettre(valeurs);
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center p-0 sm:items-center sm:p-4">
      <button
        type="button"
        aria-label="Fermer le formulaire"
        onClick={() => { if (!enCours) onFermer(); }}
        data-testid="boucle-transition-fond"
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
        tabIndex={-1}
      />
      <div
        ref={dialogue}
        role="dialog"
        aria-modal="true"
        aria-labelledby="boucle-transition-titre"
        aria-describedby="boucle-transition-description"
        data-testid="boucle-transition-modale"
        className="relative flex max-h-[92vh] w-full max-w-xl flex-col overflow-y-auto rounded-t-2xl border border-[rgba(148,163,184,0.2)] bg-[#091420] px-5 py-5 shadow-2xl sm:rounded-2xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="font-code text-[10px] uppercase tracking-[0.22em] text-[#60A5FA]">
              Transition de boucle
            </div>
            <h2
              id="boucle-transition-titre"
              className="mt-1 font-display text-lg font-black leading-tight text-[#F2F6F8]"
            >
              {action.titre}
            </h2>
            <p id="boucle-transition-description" className="mt-1 text-xs leading-relaxed text-[#94A3B8]">
              {action.description}
            </p>
          </div>
          <button
            type="button"
            onClick={onFermer}
            disabled={enCours}
            aria-label="Fermer le formulaire"
            data-testid="boucle-transition-fermer"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[rgba(148,163,184,0.18)] text-[#94A3B8] transition-colors hover:text-[#F2F6F8] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X size={15} />
          </button>
        </div>

        <form onSubmit={soumettre} noValidate aria-busy={enCours} className="mt-4">
          <div className="space-y-3">
            {action.champs.map((champ) => (
              <div key={champ.nom}>
                <label
                  htmlFor={`boucle-transition-${champ.nom}`}
                  className="block font-code text-[9px] uppercase tracking-wider text-[#94A3B8]"
                >
                  {champ.label}
                  {champ.requis && <span className="ml-1 text-[#F2B84B]" aria-hidden="true">*</span>}
                </label>
                <Champ
                  champ={champ}
                  valeur={valeurs[champ.nom] || ""}
                  onChange={changer}
                  desactive={enCours}
                />
                {champ.aide && (
                  <p className="mt-1 text-[10px] leading-relaxed text-[#7C93A8]">{champ.aide}</p>
                )}
              </div>
            ))}
          </div>

          {erreur && (
            <p
              id="boucle-transition-erreur"
              role="alert"
              data-testid="boucle-transition-erreur"
              className="mt-3 flex items-start gap-1.5 rounded-md border border-[#F87171]/30 bg-[#F87171]/[0.06] px-2.5 py-2 text-xs text-[#FCA5A5]"
            >
              <WarningCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span>{erreur}</span>
            </p>
          )}

          <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
            <button
              type="button"
              onClick={onFermer}
              disabled={enCours}
              data-testid="boucle-transition-annuler"
              className="h-8 rounded-md border border-[rgba(148,163,184,0.18)] px-3 text-xs text-[#94A3B8] transition-colors hover:text-[#F2F6F8] disabled:cursor-not-allowed disabled:opacity-50"
            >
              Annuler
            </button>
            <button
              type="submit"
              disabled={enCours}
              data-testid="boucle-transition-enregistrer"
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#60A5FA] px-3 text-xs font-semibold text-[#071019] transition-colors hover:bg-[#93C5FD] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {enCours && <CircleNotch size={12} className="animate-spin" aria-hidden="true" />}
              {enCours ? "Enregistrement…" : "Enregistrer"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
