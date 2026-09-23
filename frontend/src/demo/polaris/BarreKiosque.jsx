// Éléments du lecteur rendus par la coquille réelle (Layout) pendant une démonstration :
// bande de contrôles en pied de la colonne centrale, carte de clôture, invitation « Toujours là ? »
// et panneau de preuve. Hors démonstration, rien n'est monté.
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Sparkle, WarningCircle, X } from "@phosphor-icons/react";
import { usePolaris } from "./KiosqueProvider";
import PolarisControls from "./PolarisControls";
import PreuvePanneau from "./PreuvePanneau";
import IndicateurClic from "@/components/IndicateurClic";

export function BarreKiosque() {
  const { etat, scenario, pause, reprendre, suivant, lectureAuto, revoirDecouverte, onAccueil } = usePolaris();
  return (
    <div className="flex shrink-0 items-center justify-center border-t border-white/[0.08] bg-[#0A1520] px-4 py-2" data-testid="polaris-barre">
      <div className="flex max-w-full flex-wrap items-center justify-center gap-3">
        <div className="flex items-center gap-2 pr-1">
          <Sparkle size={14} weight="fill" className="text-[#60A5FA]" />
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
  const { etat, scenario, fixtures, pause, reprendre, onAccueil, preuveId, fermerPreuve, declencherNotification } = usePolaris();
  const [proposeInactivite, setProposeInactivite] = useState(false);
  const [clotureMasquee, setClotureMasquee] = useState(false);
  const inactivite = useRef(null);
  const location = useLocation();

  // La clôture réapparaît si le visiteur rejoue la découverte puis termine à nouveau
  useEffect(() => {
    if (etat.status !== "completed") setClotureMasquee(false);
  }, [etat.status]);

  // Ouverture par notification : le visiteur a l'air de lire Actualités (défilement lent, progressif)
  // pendant quelques secondes, avant que le signal de Flore n'apparaisse soudainement — jamais avant.
  // Le signal interrompt la lecture EN COURS : il n'attend pas la fin du défilement (voir plus bas,
  // où le défilement dure volontairement plus longtemps que ce délai).
  const [notificationVisible, setNotificationVisible] = useState(false);
  useEffect(() => {
    if (etat.status !== "awaiting_notification") { setNotificationVisible(false); return undefined; }
    const t = setTimeout(() => setNotificationVisible(true), 5000);
    return () => clearTimeout(t);
  }, [etat.status]);

  useEffect(() => {
    if (etat.status !== "awaiting_notification" || location.pathname !== "/actualites") return undefined;
    let raf = null;
    let annule = false;
    // Laisse le fil se charger et s'afficher avant de commencer à défiler, comme une vraie lecture.
    // Dure volontairement plus longtemps que le délai d'apparition de la notification ci-dessus : le
    // signal interrompt une lecture en cours, il ne récompense jamais d'avoir fini de défiler.
    const demarrage = setTimeout(() => {
      const el = document.querySelector('[data-testid="actualites-page"]');
      if (!el || annule) return;
      const debut = performance.now();
      const duree = 16000;
      const anime = (t) => {
        if (annule) return;
        const p = Math.min(1, (t - debut) / duree);
        el.scrollTop = (el.scrollHeight - el.clientHeight) * p;
        if (p < 1) raf = requestAnimationFrame(anime);
      };
      raf = requestAnimationFrame(anime);
    }, 700);
    return () => {
      annule = true;
      clearTimeout(demarrage);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [etat.status, location.pathname]);

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
              <button onClick={reprendre} className="min-h-[44px] rounded-lg border border-[#60A5FA]/50 px-4 py-2 font-code text-[11px] text-[#60A5FA]" data-testid="polaris-reessayer-btn">
                Réessayer
              </button>
              <button onClick={onAccueil} className="min-h-[44px] rounded-lg border border-[rgba(148,163,184,0.2)] px-4 py-2 font-code text-[11px] text-[#7C93A8]" data-testid="polaris-erreur-accueil-btn">
                Revenir au choix du profil
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Notification soudaine (ouverture par notification) : apparaît en haut à droite, où que le
          visiteur navigue (ici, en train de lire Actualités) — un clic sur « Voir » ouvre le nouveau
          travail, où Flore commence alors à écrire. Rien ne joue tant que ce clic n'a pas eu lieu. */}
      {etat.status === "awaiting_notification" && notificationVisible && (
        <div className="pointer-events-none absolute right-4 top-4 z-50 sm:right-6 sm:top-6">
          <div
            className="pointer-events-auto flex max-w-[320px] items-start gap-3 rounded-xl border border-[#60A5FA]/40 bg-[#0F1D28] p-4 shadow-2xl animate-in slide-in-from-top-4 fade-in duration-500"
            data-testid="polaris-notification"
          >
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#60A5FA]/15 text-[#60A5FA]">
              <Sparkle size={16} weight="fill" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#60A5FA]">{scenario.notification?.titre || "Flore"}</div>
              <p className="mt-1 text-[13px] leading-snug text-[#D8E2EA]">{scenario.notification?.texte}</p>
              <span className="relative mt-2.5 inline-block">
                <button
                  onClick={declencherNotification}
                  data-testid="polaris-notification-voir"
                  className="rounded-lg border border-[#60A5FA]/50 bg-[#60A5FA]/10 px-3 py-1.5 font-code text-[11px] font-semibold text-[#60A5FA] transition-colors hover:bg-[#60A5FA]/20"
                >
                  Voir
                </button>
                <IndicateurClic texte="Nouveau signal" sousTexte="Cliquez sur « Voir »" testid="polaris-notification-indicateur" />
              </span>
            </div>
          </div>
        </div>
      )}

      {etat.status === "completed" && !clotureMasquee && (
        <div className="absolute inset-x-0 bottom-4 z-40 flex justify-center px-6">
          <div className="relative max-w-[620px] rounded-xl border border-[rgba(96,165,250,0.3)] bg-[#0F1D28]/95 p-5 pr-12 shadow-2xl" data-testid="polaris-cloture">
            <button
              onClick={() => setClotureMasquee(true)}
              aria-label="Fermer"
              data-testid="polaris-cloture-fermer"
              className="absolute right-2 top-2 flex h-9 w-9 items-center justify-center rounded-lg text-[#7C93A8] transition-colors hover:bg-white/[0.06] hover:text-white"
            >
              <X size={16} />
            </button>
            <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#60A5FA]">Parcours terminé</div>
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
              className="rounded-lg border border-[#60A5FA]/50 px-3 py-1.5 font-code text-[11px] text-[#60A5FA]"
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
