// Éléments du lecteur rendus par la coquille réelle (Layout) pendant une démonstration :
// bande de contrôles en pied de la colonne centrale, carte de clôture, invitation « Toujours là ? »
// et panneau de preuve. Hors démonstration, rien n'est monté.
import { useEffect, useRef, useState } from "react";
import { Sparkle, WarningCircle, X } from "@phosphor-icons/react";
import { usePolaris } from "./KiosqueProvider";
import PolarisControls from "./PolarisControls";
import PreuvePanneau from "./PreuvePanneau";

export function BarreKiosque() {
  const { etat, scenario, pause, reprendre, suivant, lectureAuto, revoirDecouverte, onAccueil } = usePolaris();
  return (
    <div className="flex shrink-0 items-center justify-center border-t border-white/[0.08] bg-[#0A1520] px-4 py-2" data-testid="polaris-barre">
      <div className="flex max-w-full flex-wrap items-center justify-center gap-3">
        <div className="flex items-center gap-2 pr-1">
          <Sparkle size={14} weight="fill" className="text-[#9B87F5]" />
          <div className="leading-tight">
            <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Démonstration Polaris · données fictives</div>
            <div className="text-[11px] font-semibold text-[#F2F6F8]" data-testid="polaris-scenario-titre">{scenario.roleLabel}</div>
          </div>
        </div>
        <PolarisControls
          etat={etat}
          onPause={() => pause()}
          onReprendre={reprendre}
          onSuivant={suivant}
          onRevoir={revoirDecouverte}
          onAccueil={onAccueil}
          onLectureAuto={lectureAuto}
        />
      </div>
    </div>
  );
}

export function SurcouchesKiosque() {
  const { etat, scenario, fixtures, pause, reprendre, onAccueil, preuveId, fermerPreuve } = usePolaris();
  const [proposeInactivite, setProposeInactivite] = useState(false);
  const [clotureMasquee, setClotureMasquee] = useState(false);
  const inactivite = useRef(null);

  // La clôture réapparaît si le visiteur rejoue la découverte puis termine à nouveau
  useEffect(() => {
    if (etat.status !== "completed") setClotureMasquee(false);
  }, [etat.status]);

  // Inactivité : 90 s sans interaction dans un état arrêté → proposition ; +30 s → retour au choix du profil
  useEffect(() => {
    const arret = ["paused", "awaiting_continue", "completed"].includes(etat.status);
    if (!arret) {
      setProposeInactivite(false);
      return undefined;
    }
    let t2 = null;
    const t1 = setTimeout(() => {
      setProposeInactivite(true);
      t2 = setTimeout(() => onAccueil(), 30000);
    }, 90000);
    const reset = () => {
      clearTimeout(t1);
      if (t2) clearTimeout(t2);
      setProposeInactivite(false);
    };
    window.addEventListener("pointerdown", reset);
    window.addEventListener("keydown", reset);
    inactivite.current = reset;
    return () => {
      clearTimeout(t1);
      if (t2) clearTimeout(t2);
      window.removeEventListener("pointerdown", reset);
      window.removeEventListener("keydown", reset);
    };
  }, [etat.status, onAccueil]);

  // Onglet masqué → pause ; retour → reprise proposée (§6.3)
  useEffect(() => {
    const onVis = () => {
      if (document.hidden && etat.status === "playing") pause("onglet masqué");
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [etat.status, pause]);

  return (
    <>
      {etat.status === "error" && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-[#071019]/85 p-8">
          <div className="w-full max-w-[480px] rounded-xl border border-[#F87171]/30 bg-[#0F1D28] p-6" data-testid="polaris-erreur">
            <div className="flex items-center gap-2 font-display text-lg font-bold text-[#F87171]">
              <WarningCircle size={20} /> Un élément de la démonstration n'a pas pu s'afficher
            </div>
            <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-[#071019] p-3 font-code text-[11px] text-[#7C93A8]">{etat.erreur}</pre>
            <div className="mt-4 flex gap-2">
              <button onClick={reprendre} className="min-h-[44px] rounded-lg border border-[#25D0C8]/50 px-4 py-2 font-code text-[11px] text-[#25D0C8]" data-testid="polaris-reessayer-btn">
                Réessayer
              </button>
              <button onClick={onAccueil} className="min-h-[44px] rounded-lg border border-[rgba(148,163,184,0.2)] px-4 py-2 font-code text-[11px] text-[#7C93A8]" data-testid="polaris-erreur-accueil-btn">
                Revenir au choix du profil
              </button>
            </div>
          </div>
        </div>
      )}

      {etat.status === "completed" && !clotureMasquee && (
        <div className="absolute inset-x-0 bottom-4 z-40 flex justify-center px-6">
          <div className="relative max-w-[620px] rounded-xl border border-[rgba(37,208,200,0.3)] bg-[#0F1D28]/95 p-5 pr-12 shadow-2xl" data-testid="polaris-cloture">
            <button
              onClick={() => setClotureMasquee(true)}
              aria-label="Fermer"
              data-testid="polaris-cloture-fermer"
              className="absolute right-2 top-2 flex h-9 w-9 items-center justify-center rounded-lg text-[#7C93A8] transition-colors hover:bg-white/[0.06] hover:text-white"
            >
              <X size={16} />
            </button>
            <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#25D0C8]">Parcours terminé</div>
            <p className="mt-2 text-sm leading-relaxed text-[#D8E2EA]">{scenario.closingText}</p>
          </div>
        </div>
      )}

      {proposeInactivite && (
        <div className="absolute inset-x-0 bottom-24 z-40 flex justify-center">
          <div className="flex items-center gap-3 rounded-xl border border-[rgba(148,163,184,0.25)] bg-[#0F1D28] px-5 py-3 shadow-2xl" data-testid="polaris-inactivite">
            <span className="text-sm text-[#D8E2EA]">Toujours là ?</span>
            <button
              onClick={() => {
                inactivite.current?.();
                reprendre();
              }}
              className="rounded-lg border border-[#25D0C8]/50 px-3 py-1.5 font-code text-[11px] text-[#25D0C8]"
              data-testid="polaris-inactivite-continuer"
            >
              Continuer
            </button>
            <button onClick={onAccueil} className="font-code text-[11px] text-[#7C93A8]" data-testid="polaris-inactivite-accueil">
              Choix du profil
            </button>
          </div>
        </div>
      )}

      <PreuvePanneau preuve={preuveId ? fixtures.preuves[preuveId] : null} onFermer={fermerPreuve} />
    </>
  );
}
