// Lecteur kiosque Polaris (/demo/polaris/:profileId) : compose les surfaces
// (Flore seule → Atlas + Flore latérale → Travail), les contrôles du lecteur,
// la suspension sur inactivité/onglet masqué et l'état d'erreur récupérable.
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Sparkle, WarningCircle } from "@phosphor-icons/react";
import { PolarisSessionProvider, usePolaris } from "./PolarisSessionProvider";
import { SCENARIOS } from "./scenarios/gestionnaire";
import { FIXTURES_GESTIONNAIRE } from "./data/fixturesGestionnaire";
import PolarisControls from "./PolarisControls";
import FloreKiosque from "./FloreKiosque";
import AtlasKiosque from "./AtlasKiosque";
import TravailKiosque from "./TravailKiosque";
import PreuvePanneau from "./PreuvePanneau";

const FIXTURES_PAR_PROFIL = { gestionnaire: FIXTURES_GESTIONNAIRE };

function Coquille() {
  const { etat, scenario, fixtures, pause, reprendre, suivant, lectureAuto, revoirDecouverte, acquitterScene, onAccueil } = usePolaris();
  const [preuveOuverte, setPreuveOuverte] = useState(null);
  const inactivite = useRef(null);
  const [proposeInactivite, setProposeInactivite] = useState(false);

  // Ouvrir une preuve suspend la lecture (§7.6)
  const ouvrirPreuve = useCallback(
    (pid) => {
      setPreuveOuverte(pid);
      pause("consultation d'une preuve");
    },
    [pause]
  );

  // Inactivité : 90 s sans interaction dans un état arrêté → proposition ; +30 s → accueil
  useEffect(() => {
    const arret = ["paused", "awaiting_continue", "completed"].includes(etat.status);
    if (!arret) { setProposeInactivite(false); return undefined; }
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

  const travail = Object.values(etat.resultats)[0] || null;
  const floreSeule = etat.surface === "flore";
  const lateral = etat.surface !== "flore";

  return (
    <div className="flex h-screen flex-col bg-[#071019] text-[#D8E2EA]" data-testid="polaris-player">
      <header className="flex items-center justify-between border-b border-[rgba(148,163,184,0.12)] px-5 py-3">
        <div className="flex items-center gap-3">
          <Sparkle size={16} weight="fill" className="text-[#9B87F5]" />
          <div>
            <div className="font-display text-sm font-bold text-[#F2F6F8]" data-testid="polaris-scenario-titre">{scenario.title}</div>
            <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#7C93A8]">
              Démonstration Polaris · {scenario.roleLabel}
            </div>
          </div>
        </div>
        <button onClick={onAccueil} className="font-code text-[10px] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]" data-testid="polaris-retour-accueil">
          ← Accueil de la démonstration
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        {etat.status === "error" ? (
          <div className="flex flex-1 items-center justify-center p-8">
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
                  Revenir à l'accueil
                </button>
              </div>
            </div>
          </div>
        ) : (
          <>
            {/* Surface principale */}
            <main className="relative min-w-0 flex-1" data-testid="polaris-surface">
              {floreSeule && (
                <div className="mx-auto flex h-full max-w-[760px] flex-col px-6 py-6">
                  <p className="mb-4 font-code text-[10px] uppercase tracking-[0.25em] text-[#7C93A8]">{scenario.roleContext}</p>
                  <FloreKiosque
                    messages={etat.messages}
                    activite={etat.activite}
                    frappeActive={etat.frappeActive}
                    enPause={etat.status === "paused"}
                    roleLabel={scenario.roleLabel}
                    onPreuve={ouvrirPreuve}
                  />
                </div>
              )}
              {etat.surface === "atlas" && (
                <AtlasKiosque
                  sceneId={etat.sceneId}
                  version={etat.sceneVersion}
                  fixtures={fixtures}
                  commandeAttente={etat.attente?.commandId || null}
                  onScenePrete={acquitterScene}
                  onInteraction={() => pause("exploration libre")}
                />
              )}
              {etat.surface === "travail" && travail && (
                <div className="h-full px-6 py-5">
                  <TravailKiosque travail={travail} messages={etat.messages} preuves={fixtures.preuves} onPreuve={ouvrirPreuve} />
                </div>
              )}
              {etat.status === "completed" && (
                <div className="absolute inset-x-0 bottom-16 flex justify-center px-6">
                  <div className="max-w-[620px] rounded-xl border border-[rgba(37,208,200,0.3)] bg-[#0F1D28]/95 p-5 shadow-2xl" data-testid="polaris-cloture">
                    <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#25D0C8]">Parcours terminé</div>
                    <p className="mt-2 text-sm leading-relaxed text-[#D8E2EA]">{scenario.closingText}</p>
                  </div>
                </div>
              )}
            </main>

            {/* Flore latérale : le même fil continue à droite de la surface */}
            {lateral && (
              <aside className="hidden w-[400px] shrink-0 border-l border-[rgba(148,163,184,0.12)] bg-[#0A1520] px-4 py-4 xl:block" data-testid="flore-laterale-kiosque">
                <FloreKiosque
                  messages={etat.messages}
                  activite={etat.activite}
                  frappeActive={etat.frappeActive}
                  enPause={etat.status === "paused"}
                  roleLabel={scenario.roleLabel}
                  onPreuve={ouvrirPreuve}
                  compact
                />
              </aside>
            )}
          </>
        )}
      </div>

      <footer className="flex items-center justify-between gap-4 border-t border-[rgba(148,163,184,0.12)] px-5 py-3">
        <PolarisControls
          etat={etat}
          onPause={() => pause()}
          onReprendre={reprendre}
          onSuivant={suivant}
          onRevoir={revoirDecouverte}
          onAccueil={onAccueil}
          onLectureAuto={lectureAuto}
        />
        <div className="hidden font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8] md:block">
          {etat.status === "playing" ? "Lecture en cours…" : etat.status === "completed" ? "Terminé" : ""}
        </div>
      </footer>

      {proposeInactivite && (
        <div className="fixed inset-x-0 bottom-24 z-40 flex justify-center">
          <div className="flex items-center gap-3 rounded-xl border border-[rgba(148,163,184,0.25)] bg-[#0F1D28] px-5 py-3 shadow-2xl" data-testid="polaris-inactivite">
            <span className="text-sm text-[#D8E2EA]">Toujours là ?</span>
            <button onClick={() => { inactivite.current?.(); reprendre(); }} className="rounded-lg border border-[#25D0C8]/50 px-3 py-1.5 font-code text-[11px] text-[#25D0C8]" data-testid="polaris-inactivite-continuer">
              Continuer
            </button>
            <button onClick={onAccueil} className="font-code text-[11px] text-[#7C93A8]" data-testid="polaris-inactivite-accueil">
              Accueil
            </button>
          </div>
        </div>
      )}

      <PreuvePanneau preuve={preuveOuverte ? fixtures.preuves[preuveOuverte] : null} onFermer={() => setPreuveOuverte(null)} />
    </div>
  );
}

export default function PolarisPlayer() {
  const { profileId } = useParams();
  const navigate = useNavigate();
  const scenario = SCENARIOS[profileId];
  const fixtures = FIXTURES_PAR_PROFIL[profileId];
  const accueil = useCallback(() => navigate("/demo"), [navigate]);

  if (!scenario || !fixtures) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#071019] p-6" data-testid="polaris-indisponible">
        <div className="w-full max-w-[440px] rounded-xl border border-[rgba(148,163,184,0.2)] bg-[#0F1D28] p-6 text-center">
          <h1 className="font-display text-lg font-bold text-[#F2F6F8]">Ce parcours n'est pas encore disponible.</h1>
          <p className="mt-2 text-sm text-[#7C93A8]">Le parcours Gestionnaire est jouable dès maintenant.</p>
          <button
            onClick={accueil}
            className="mt-4 min-h-[44px] rounded-lg border border-[#25D0C8]/50 px-4 py-2 font-code text-[11px] text-[#25D0C8]"
            data-testid="polaris-indisponible-accueil"
          >
            Revenir à l'accueil de la démonstration
          </button>
        </div>
      </div>
    );
  }

  return (
    <PolarisSessionProvider key={profileId} scenario={scenario} fixtures={fixtures} onAccueil={accueil}>
      <Coquille />
    </PolarisSessionProvider>
  );
}
