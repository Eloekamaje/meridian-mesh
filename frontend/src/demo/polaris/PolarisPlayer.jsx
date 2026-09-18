// Lecteur kiosque Polaris (/demo/polaris/:profileId) : le scénario pilote la VRAIE
// application Méridian — Topbar, Atlas, Flore et Travail authentiques — alimentée
// localement par les fixtures via un adaptateur réseau simulé (§4.1).
// Aucune interface parallèle : choisir un rôle ouvre Méridian avec son contexte.
import { useEffect, useMemo, useRef, useState } from "react";
import { Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { Sparkle, WarningCircle } from "@phosphor-icons/react";
import api from "@/lib/api";
import { PerimetreProvider } from "@/lib/perimetre";
import { ContexteProvider, useContexte } from "@/lib/contexte";
import { MeshProvider, useMesh } from "@/lib/mesh";
import { DemoProvider } from "@/lib/demo";
import { PilotageProvider } from "@/lib/pilotage";
import Topbar from "@/components/Topbar";
import FlorePanel from "@/components/FlorePanel";
import DemoTour from "@/components/DemoTour";
import Atlas from "@/pages/Atlas";
import Accueil from "@/pages/Accueil";
import TravailDetail from "@/pages/TravailDetail";
import { PolarisSessionProvider, usePolaris } from "./PolarisSessionProvider";
import { SCENARIOS } from "./scenarios/gestionnaire";
import { FIXTURES_GESTIONNAIRE } from "./data/fixturesGestionnaire";
import { installerMockPolaris, definirSceneActive } from "./mockApi";
import PolarisControls from "./PolarisControls";
import PreuvePanneau from "./PreuvePanneau";

const FIXTURES_PAR_PROFIL = { gestionnaire: FIXTURES_GESTIONNAIRE };

// Messages du moteur → échanges du vrai panneau Flore (question persona, réponses Flore)
function construireEchanges(messages, fixtures) {
  const out = [];
  messages.forEach((m) => {
    if (m.speaker === "persona") {
      out.push({ id: m.id, question: m.text, data: null });
      return;
    }
    const data = {
      reponse: m.text,
      comportement: "expliquer",
      contributions: [],
      indicateurs: null,
      preuves: (m.evidenceIds || [])
        .map((pid) => {
          const p = fixtures.preuves[pid];
          return p ? { preuveId: pid, source: p.title, detail: p.supports } : null;
        })
        .filter(Boolean),
    };
    const dernier = out[out.length - 1];
    if (dernier && !dernier.data) out[out.length - 1] = { ...dernier, data };
    else out.push({ id: m.id, question: null, data });
  });
  return out;
}

// Orchestre les effets du scénario sur l'application réelle : scènes de l'Atlas
// (Mesh simulé filtré, cadrage + accentuation via les commandes carte existantes)
// et bascule de surface (le travail est une vraie page Travail).
function Orchestrateur({ profileId }) {
  const { etat, fixtures, acquitterScene } = usePolaris();
  const { recharger } = useMesh();
  const { commanderCarte } = useContexte();
  const navigate = useNavigate();
  const scene = etat.sceneId ? fixtures.scenes[etat.sceneId] : null;
  const commandId = etat.attente?.commandId || null;

  useEffect(() => {
    if (!scene || etat.surface !== "atlas") return undefined;
    let annule = false;
    let t = null;
    definirSceneActive(scene.id);
    recharger()
      .then(() => {
        if (annule) return;
        const ids = scene.noeuds.filter((n) => !n.masque).map((n) => n.id);
        const accents = scene.noeuds.filter((n) => n.accent).map((n) => n.id);
        commanderCarte({ type: "scene", ids, accents });
        t = setTimeout(() => {
          if (!annule && commandId) acquitterScene(commandId);
        }, 900);
      })
      .catch(() => {
        if (!annule && commandId) acquitterScene(commandId);
      });
    return () => {
      annule = true;
      if (t) clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etat.sceneVersion, etat.surface]);

  // Verrou kiosque : la route courante suit toujours la surface scriptée — un clic
  // sur un lien de navigation ne fait jamais quitter la démonstration
  const location = useLocation();
  useEffect(() => {
    let attendu = `/demo/polaris/${profileId}`;
    if (etat.surface === "nouveau") attendu = `/demo/polaris/${profileId}/nouveau`;
    if (etat.surface === "travail") {
      const rid = Object.keys(etat.resultats)[0];
      if (!rid) return;
      attendu = `/demo/polaris/${profileId}/travail/${rid}`;
    }
    if (location.pathname !== attendu) navigate(attendu, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etat.surface, location.pathname]);

  return null;
}

function Coquille({ scenario, fixtures }) {
  const { etat, pause, reprendre, suivant, lectureAuto, revoirDecouverte, onAccueil, preuveId, fermerPreuve, ouvrirPreuve, demarrerOuverture } = usePolaris();
  const [proposeInactivite, setProposeInactivite] = useState(false);
  const inactivite = useRef(null);

  // Inactivité : 90 s sans interaction dans un état arrêté → proposition ; +30 s → accueil
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

  const pilotage = useMemo(
    () => ({
      ouvert: etat.messages.length > 0 && etat.surface === "atlas",
      echanges: construireEchanges(etat.messages, fixtures),
      activite: etat.activite,
      enPause: etat.status === "paused",
      saisie: etat.saisie,
      ouvertureEnAttente: etat.status === "awaiting_opening",
      demarrerOuverture,
      ouvrirPreuve,
      baseUrl: `/demo/polaris/${scenario.profileId}`,
    }),
    [etat.messages, etat.surface, etat.activite, etat.status, etat.saisie, fixtures, scenario, demarrerOuverture, ouvrirPreuve]
  );

  return (
    <PilotageProvider value={pilotage}>
      <div className="flex h-screen w-full overflow-hidden bg-[rgba(148,163,184,0.07)] text-foreground" data-testid="polaris-player">
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <main className="relative flex-1 overflow-hidden">
            {etat.status === "error" ? (
              <div className="flex h-full items-center justify-center p-8">
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
              <Routes>
                <Route index element={<Atlas />} />
                <Route path="nouveau" element={<Accueil mode="creation" />} />
                <Route path="travail/:cid" element={<TravailDetail />} />
              </Routes>
            )}

            {etat.status === "completed" && (
              <div className="absolute inset-x-0 bottom-24 z-40 flex justify-center px-6">
                <div className="max-w-[620px] rounded-xl border border-[rgba(37,208,200,0.3)] bg-[#0F1D28]/95 p-5 shadow-2xl" data-testid="polaris-cloture">
                  <div className="font-code text-[9px] uppercase tracking-[0.25em] text-[#25D0C8]">Parcours terminé</div>
                  <p className="mt-2 text-sm leading-relaxed text-[#D8E2EA]">{scenario.closingText}</p>
                </div>
              </div>
            )}

            {/* Barre flottante du lecteur — discrète, superposée à l'application réelle
                (décalée à droite sur la page Nouveau travail pour dégager le composer) */}
            <div className={`pointer-events-none absolute inset-x-0 bottom-4 z-40 flex px-4 ${etat.surface === "nouveau" ? "justify-end" : "justify-center"}`}>
              <div className="pointer-events-auto flex max-w-full flex-wrap items-center gap-3 rounded-2xl border border-[rgba(148,163,184,0.18)] bg-[#0A1520]/95 px-4 py-2 shadow-2xl backdrop-blur-xl" data-testid="polaris-barre">
                <div className="flex items-center gap-2 pr-1">
                  <Sparkle size={14} weight="fill" className="text-[#9B87F5]" />
                  <div className="leading-tight">
                    <div className="font-code text-[9px] uppercase tracking-[0.2em] text-[#7C93A8]">Démonstration Polaris</div>
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
                    Accueil
                  </button>
                </div>
              </div>
            )}
          </main>
        </div>
        <FlorePanel />
      </div>
      <DemoTour />
      <PreuvePanneau preuve={preuveId ? fixtures.preuves[preuveId] : null} onFermer={fermerPreuve} />
    </PilotageProvider>
  );
}

// Session démonstration : installe l'adaptateur local AVANT le premier rendu des
// providers (aucune requête réseau ne part), aligne l'identité sur le rôle choisi,
// puis restaure tout à la sortie.
function SessionPolaris({ scenario, fixtures, onAccueil }) {
  const [installation] = useState(() => {
    const precedent = {
      persona: localStorage.getItem("meridian.persona"),
      cible: localStorage.getItem("meridian.perimetre"),
      espace: localStorage.getItem("meridian.perimetre.espace"),
    };
    localStorage.setItem("meridian.persona", scenario.profileId);
    localStorage.setItem("meridian.perimetre", "mesh-global");
    localStorage.setItem("meridian.perimetre.espace", "mesh-global");
    const desinstalle = installerMockPolaris(api, { fixtures, scenario });
    return { precedent, desinstalle };
  });

  useEffect(() => {
    const { precedent, desinstalle } = installation;
    return () => {
      desinstalle();
      const restaurer = (cle, valeur) => {
        if (valeur == null) localStorage.removeItem(cle);
        else localStorage.setItem(cle, valeur);
      };
      restaurer("meridian.persona", precedent.persona);
      restaurer("meridian.perimetre", precedent.cible);
      restaurer("meridian.perimetre.espace", precedent.espace);
    };
  }, [installation]);

  return (
    <PolarisSessionProvider scenario={scenario} fixtures={fixtures} onAccueil={onAccueil}>
      <PerimetreProvider>
        <DemoProvider>
          <ContexteProvider>
            <MeshProvider>
              <Orchestrateur profileId={scenario.profileId} />
              <Coquille scenario={scenario} fixtures={fixtures} />
            </MeshProvider>
          </ContexteProvider>
        </DemoProvider>
      </PerimetreProvider>
    </PolarisSessionProvider>
  );
}

export default function PolarisPlayer() {
  const { profileId } = useParams();
  const navigate = useNavigate();
  const scenario = SCENARIOS[profileId];
  const fixtures = FIXTURES_PAR_PROFIL[profileId];
  const accueil = () => navigate("/demo");

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

  return <SessionPolaris key={profileId} scenario={scenario} fixtures={fixtures} onAccueil={accueil} />;
}
