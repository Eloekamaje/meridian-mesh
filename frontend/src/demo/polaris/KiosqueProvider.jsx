// Mode démonstration Polaris — un MODE de la vraie application, pas une application parallèle.
// KiosqueProvider enveloppe les vraies routes ; quand un profil est choisi il installe un réseau
// local (mockApi), verrouille la route sur l'étape du scénario et pilote les vraies pages
// (Atlas, Nouveau travail, Travail) via le contexte de pilotage. Hors démonstration : null.
//
// Moteur de lecture : une seule horloge pilote messages, activité et résultats.
// - Pause/reprise avec délai restant conservé (§6.3) — beat en cours jamais redémarré
// - Suivant : termine la séquence courante jusqu'à son checkpoint, sans doublon (M02)
// - Revoir la découverte : restaure le checkpoint antérieur puis rejoue (M04)
// - Anti-course : generation incrémentée à chaque restauration ; ids déterministes (§6.4)
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PilotageProvider } from "@/lib/pilotage";
import { validerScenario } from "./scenarioSchema";
import { installerMockPolaris, lireTravailDemo as lireTravail, synchroniserTravauxDemo } from "./mockApi";
import { SCENARIOS } from "./scenarios";
import { FIXTURES_VP } from "./data/fixturesVP";
import { FIXTURES_DIRECTEUR } from "./data/fixturesDirecteur";
import { versEchanges, versMessageCase } from "./messages";

const FIXTURES_PAR_PROFIL = { vp: FIXTURES_VP, directeur: FIXTURES_DIRECTEUR };

export const RYTHME = {
  lectureMin: 2500,
  lectureParMot: 190,
  frappeMsParLot: 36, // 3 caractères par lot (~83 car/s, télétype de Flore — laisse la marge de lecture faire le reste)
  frappeHumaineMsParLot: 55, // 2 caractères par lot (~27 car/s) : une frappe humaine qu'on a le temps de lire en direct
  opMin: 800,
  opMax: 1100,
  transitionSurface: 400,
  ackMax: 5000,
  observe: 5000,
};

const Ctx = createContext(null);

const dureeMessage = (texte) => {
  const mots = (texte || "").split(/\s+/).filter(Boolean).length;
  const frappe = Math.ceil((texte || "").length / 3) * RYTHME.frappeMsParLot;
  return frappe + Math.max(RYTHME.lectureMin, mots * RYTHME.lectureParMot);
};

const dureeOp = (i) => RYTHME.opMin + ((i * 173) % (RYTHME.opMax - RYTHME.opMin));

// Ligne d'activité (une par traitement) : opérations jouées, sources consultées. Elle traverse les
// messages de découverte publiés en cours de route et se replie à la fin du traitement.
const appliquerEtape = (activites, beat) =>
  activites.map((a) => {
    if (a.id !== beat.activityId) return a;
    if (a.ops[a.ops.length - 1]?.label === beat.label) return a; // idempotent (reprise, « Suivant »)
    return { ...a, ops: [...a.ops.map((o) => ({ ...o, status: "done" })), { label: beat.label, sources: beat.sources || [], status: "running" }] };
  });
const terminerActivite = (activites, beat) =>
  activites.map((a) => (a.id === beat.activityId ? { ...a, status: "done", ops: a.ops.map((o) => ({ ...o, status: "done" })) } : a));
// Une activité en cours avance d'un cran à chaque réplique de narration (jamais sur celle qui la
// clôt) : elle reste ainsi toujours ancrée juste après la dernière chose dite AVANT sa conclusion —
// exactement là où elle doit rester une fois « terminée », sans jamais avoir à sauter par-dessus
// une réponse déjà affichée pour s'y replacer après coup.
const avancerAncrageActivites = (activites, messagesLength) =>
  activites.map((a) => (a.status === "running" ? { ...a, apres: messagesLength } : a));

function MoteurSession({ scenario, fixtures, onAccueil, children }) {
  const [erreursValidation] = useState(() => validerScenario(scenario, fixtures));
  const ouvertureInteractive = scenario.openingMode === "user_request";
  const [etat, setEtat] = useState(() => ({
    status: erreursValidation.length ? "error" : ouvertureInteractive ? "awaiting_opening" : "initializing",
    erreur: erreursValidation.length ? `Scénario invalide :\n${erreursValidation.join("\n")}` : null,
    playMode: "auto",
    stepIndex: 0,
    beatIndex: 0,
    messages: [],
    activites: [], // lignes d'activité de Flore : { id, stepId, status, ops:[{label, sources, status}], apres }
    preparation: null, // { surface, titre } : la surface annoncée se prépare, l'ancien contenu reste stable
    surface: ouvertureInteractive ? "atlas" : "flore",
    saisie: null, // { texte, enFrappe } — frappe simulée dans le composer réel (ouverture user_request)
    statutAvantPause: null,
    sceneId: null,
    resultats: {},
    attente: null, // { commandId } pendant apply_scene
    sceneVersion: 0,
    frappeActive: false,
    motif: null,
    documentGenere: false, // le dossier de Flore existe (Résultats du Travail)
    canvasOuvert: false, // le canvas du document est ouvert à droite du fil
  }));

  const horloge = useRef({ timer: null, finA: 0, action: null, restant: null });
  const ackTimer = useRef(null); // chien de garde d'acquittement : survit aux nettoyages d'effet
  const generation = useRef(0);
  const beatEnCours = useRef(null); // clé du beat démarré : pause/reprise ne le redémarre jamais
  const occupes = useRef(false);
  const ouvertureFaite = useRef(false); // frappe d'ouverture achevée : le 1er message devient un battement d'envoi

  const effacerTimer = () => {
    if (horloge.current.timer) clearTimeout(horloge.current.timer);
    horloge.current.timer = null;
  };

  const planifier = useCallback((ms, action) => {
    effacerTimer();
    const gen = generation.current;
    horloge.current.finA = Date.now() + ms;
    horloge.current.action = action;
    horloge.current.timer = setTimeout(() => {
      horloge.current.timer = null;
      horloge.current.action = null;
      if (gen !== generation.current) return; // retour périmé ignoré (§6.4)
      action();
    }, ms);
  }, []);

  const avancer = useCallback(() => {
    setEtat((e) => ({ ...e, beatIndex: e.beatIndex + 1, attente: null }));
  }, []);

  // Ajout idempotent par identifiant déterministe (jamais de doublon, M07)
  const ajouterMessage = useCallback(
    (step, idx, beat) => {
      setEtat((e) => {
        const id = `msg-${scenario.id}-${step.id}-${idx}`;
        if (e.messages.some((m) => m.id === id)) return e;
        const messages = [
          ...e.messages,
          {
            id,
            speaker: beat.speaker,
            speakerLabel: beat.speaker === "flore" ? "Flore" : scenario.roleLabel,
            text: beat.text,
            stepId: step.id,
            evidenceIds: beat.evidenceIds || [],
            contenu: beat.contenu || null,
            // Une simple annonce (« Je vais… », « Je vérifie… ») n'est pas encore LA réponse : le
            // traitement continue après elle (activité, autre message). Seul le message qui clôt
            // vraiment l'activité (`terminer`) mérite copier/pouce/régénérer.
            termine: beat.speaker !== "flore" || !!beat.terminer,
            quand: new Date().toISOString(),
            anime: true,
          },
        ];
        return {
          ...e,
          messages,
          frappeActive: beat.speaker === "flore",
          // Sauf sur le message qui clôt une activité : celui-là ne doit JAMAIS repousser son
          // ancrage plus loin — sinon la ligne se retrouverait à sauter par-dessus la réponse
          // qu'elle est censée précéder, pile au moment de sa clôture.
          activites: beat.terminer ? e.activites : avancerAncrageActivites(e.activites, messages.length),
        };
      });
    },
    [scenario]
  );

  // Exécution du beat courant — une seule horloge, effets idempotents
  const jouerBeatCourant = useCallback(() => {
    const cle = `${generation.current}:${etat.stepIndex}:${etat.beatIndex}`;
    if (beatEnCours.current === cle) return; // déjà démarré (pause/reprise)
    beatEnCours.current = cle;

    const step = scenario.steps[etat.stepIndex];
    if (!step) return;
    const beat = step.beats[etat.beatIndex];

    if (!beat) {
      const derniere = etat.stepIndex >= scenario.steps.length - 1;
      if (derniere) {
        setEtat((e) => ({ ...e, status: "completed" }));
      } else if (etat.playMode === "auto") {
        setEtat((e) => ({ ...e, stepIndex: e.stepIndex + 1, beatIndex: 0 }));
      } else {
        setEtat((e) => ({ ...e, status: "awaiting_continue" }));
      }
      return;
    }

    switch (beat.type) {
      case "message": {
        const premiereDemande = ouvertureFaite.current && etat.stepIndex === 0 && etat.beatIndex === 0;
        if (beat.speaker === "persona" && !premiereDemande) {
          // Frappe simulée dans le composer réel (rythme humain, lisible en direct) ; une fois
          // tapé, le message reste EN ATTENTE — c'est le clic du visiteur (envoyerSaisie) qui
          // l'envoie, jamais un timer (interactif : chaque réplique du profil démo se mérite un clic).
          const tape = (i) => {
            if (i > beat.text.length) {
              setEtat((e) => ({ ...e, saisie: { texte: beat.text, enFrappe: false } }));
              return;
            }
            setEtat((e) => ({ ...e, saisie: { texte: beat.text.slice(0, i), enFrappe: true } }));
            planifier(RYTHME.frappeHumaineMsParLot, () => tape(i + 2));
          };
          tape(2);
          break;
        }
        ajouterMessage(step, etat.beatIndex, beat);
        // La demande d'ouverture a déjà été lue pendant sa frappe dans le composer :
        // simple battement d'« envoi » au lieu du temps de lecture complet
        // Envoi de la demande : un battement, puis on est dans la conversation
        const duree = premiereDemande ? 700 : dureeMessage(beat.text);
        const suite = () => {
          setEtat((e) => ({ ...e, frappeActive: false }));
          avancer();
        };
        const doc = !!beat.contenu?.documentCanvas;
        if (beat.speaker === "flore" && (beat.terminer || doc)) {
          // La réponse se déroule (durée de frappe), PUIS le traitement s'arrête et le document s'ouvre ;
          // le temps de lecture ne commence qu'ensuite
          const frappe = Math.ceil(beat.text.length / 3) * RYTHME.frappeMsParLot;
          planifier(frappe, () => {
            setEtat((e) => ({
              ...e,
              activites: beat.terminer ? terminerActivite(e.activites, { activityId: beat.terminer }) : e.activites,
              documentGenere: e.documentGenere || doc,
              canvasOuvert: e.canvasOuvert || doc,
            }));
            planifier(Math.max(0, duree - frappe), suite);
          });
        } else {
          planifier(duree, suite);
        }
        break;
      }
      case "activity_start": {
        setEtat((e) =>
          e.activites.some((a) => a.id === beat.id)
            ? e
            : { ...e, activites: [...e.activites, { id: beat.id, stepId: step.id, status: "running", ops: [], apres: e.messages.length }] }
        );
        planifier(250, avancer);
        break;
      }
      case "activity_step": {
        // Le libellé remplace le précédent, au même endroit
        setEtat((e) => ({ ...e, activites: appliquerEtape(e.activites, beat) }));
        planifier(beat.duree ?? 1500, avancer);
        break;
      }
      case "activity_end": {
        setEtat((e) => ({ ...e, activites: terminerActivite(e.activites, beat) }));
        planifier(300, avancer);
        break;
      }
      case "prepare": {
        setEtat((e) => ({ ...e, preparation: { surface: beat.surface, titre: beat.titre } }));
        planifier(beat.duree ?? 1600, avancer);
        break;
      }
      case "prepare_end": {
        setEtat((e) => ({ ...e, preparation: null }));
        planifier(RYTHME.transitionSurface, avancer);
        break;
      }
      case "apply_scene": {
        if (etat.sceneId === beat.sceneId && etat.surface === "atlas" && !etat.attente) {
          avancer(); // scène déjà affichée : acquittement immédiat, sans rejouer
          break;
        }
        const commandId = `cmd-${generation.current}-${etat.stepIndex}-${etat.beatIndex}`;
        setEtat((e) => ({
          ...e,
          surface: "atlas",
          sceneId: beat.sceneId,
          sceneVersion: e.sceneVersion + 1,
          attente: { commandId },
        }));
        if (ackTimer.current) clearTimeout(ackTimer.current);
        const gen = generation.current;
        ackTimer.current = setTimeout(() => {
          if (gen !== generation.current) return;
          setEtat((e) =>
            e.attente?.commandId === commandId
              ? { ...e, status: "error", erreur: "La vue n'a pas pu s'afficher à temps.", attente: null }
              : e
          );
        }, RYTHME.ackMax);
        break;
      }
      case "upsert_result": {
        setEtat((e) =>
          e.resultats[beat.resultId]?.phase === beat.phase
            ? e
            : { ...e, resultats: { ...e.resultats, [beat.resultId]: { phase: beat.phase } } }
        );
        planifier(300, avancer);
        break;
      }
      case "show_surface": {
        setEtat((e) => ({ ...e, surface: beat.surface }));
        planifier(RYTHME.transitionSurface, avancer);
        break;
      }
      case "observe": {
        planifier(beat.duree ?? RYTHME.observe, avancer);
        break;
      }
      default:
        avancer();
    }
  }, [etat.stepIndex, etat.beatIndex, etat.playMode, etat.sceneId, etat.surface, etat.attente, scenario, ajouterMessage, planifier, avancer]);

  const jouerRef = useRef(jouerBeatCourant);
  jouerRef.current = jouerBeatCourant;

  useEffect(() => {
    if (etat.status !== "playing" || etat.attente) return undefined;
    jouerRef.current();
    return () => effacerTimer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etat.status, etat.stepIndex, etat.beatIndex, etat.attente]);

  // Démarrage
  useEffect(() => {
    if (etat.status === "initializing") {
      const t = setTimeout(() => setEtat((e) => ({ ...e, status: "playing" })), 400);
      return () => clearTimeout(t);
    }
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Ouverture interactive (user_request) : le parcours ne démarre que par le clic du
  // visiteur sur « Nouveau travail » — la demande se tape alors dans le composer réel
  const texteOuverture = useMemo(() => {
    for (const s of scenario.steps || []) {
      for (const b of s.beats || []) {
        if (b.type === "message" && b.speaker === "persona") return b.text;
      }
    }
    return "";
  }, [scenario]);

  const demarrerOuverture = useCallback(() => {
    setEtat((e) =>
      e.status === "awaiting_opening"
        ? { ...e, status: "opening_typing", surface: "nouveau", saisie: { texte: "", enFrappe: true } }
        : e
    );
  }, []);

  const frappeOuverture = useRef(false);
  useEffect(() => {
    if (etat.status !== "opening_typing" || frappeOuverture.current || !texteOuverture) return undefined;
    frappeOuverture.current = true;
    const tape = (i) => {
      if (i > texteOuverture.length) {
        // Tapé en entier : on attend le clic du visiteur (envoyerSaisie), jamais un envoi automatique.
        frappeOuverture.current = false;
        setEtat((e) => (e.saisie ? { ...e, saisie: { texte: texteOuverture, enFrappe: false } } : e));
        return;
      }
      setEtat((e) => (e.saisie ? { ...e, saisie: { texte: texteOuverture.slice(0, i), enFrappe: true } } : e));
      planifier(RYTHME.frappeHumaineMsParLot, () => tape(i + 2));
    };
    tape(2);
    return () => effacerTimer();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etat.status, texteOuverture]);

  // Envoi humain forcé : le visiteur clique le bouton d'envoi du composer réel une fois la
  // frappe (simulée) terminée — aucune réplique du profil démo ne part toute seule sur un timer.
  const envoyerSaisie = useCallback(() => {
    if (!etat.saisie || etat.saisie.enFrappe) return;
    if (etat.status === "opening_typing") {
      ouvertureFaite.current = true;
      setEtat((e) => ({ ...e, saisie: null, status: "playing" }));
      return;
    }
    if (etat.status !== "playing") return;
    const step = scenario.steps[etat.stepIndex];
    const beat = step.beats[etat.beatIndex];
    ajouterMessage(step, etat.beatIndex, beat);
    setEtat((e) => ({ ...e, saisie: null }));
    planifier(1200, avancer);
  }, [etat.saisie, etat.status, etat.stepIndex, etat.beatIndex, scenario, ajouterMessage, planifier, avancer]);

  useEffect(
    () => () => {
      effacerTimer();
      if (ackTimer.current) clearTimeout(ackTimer.current);
    },
    []
  );

  // Acquittement d'une scène par la surface Atlas (§7.3) — périmé → ignoré
  const acquitterScene = useCallback((commandId) => {
    setEtat((e) => {
      if (e.attente?.commandId !== commandId) return e;
      if (ackTimer.current) clearTimeout(ackTimer.current);
      beatEnCours.current = null;
      return { ...e, attente: null, beatIndex: e.beatIndex + 1 };
    });
  }, []);

  // --- Contrôles du lecteur (§6.3) ---
  const pause = useCallback((motif = null) => {
    if (horloge.current.timer) {
      clearTimeout(horloge.current.timer);
      horloge.current.timer = null;
      horloge.current.restant = Math.max(0, horloge.current.finA - Date.now()); // délai conservé
    }
    setEtat((e) =>
      e.status === "playing" || e.status === "opening_typing"
        ? { ...e, status: "paused", statutAvantPause: e.status, motif, frappeActive: false }
        : e
    );
  }, []);

  const reprendre = useCallback(() => {
    const { action, restant } = horloge.current;
    setEtat((e) => {
      if (e.status === "error") {
        beatEnCours.current = null; // Réessayer : rejoue le beat fautif
        return { ...e, status: "playing", erreur: null };
      }
      return e.status === "paused"
        ? { ...e, status: e.statutAvantPause === "opening_typing" ? "opening_typing" : "playing", statutAvantPause: null, motif: null }
        : e;
    });
    if (action != null && restant != null) planifier(restant, action);
  }, [planifier]);

  const completerSequence = useCallback(() => {
    if (occupes.current) return; // double clic : une seule exécution (M02)
    occupes.current = true;
    effacerTimer();
    horloge.current.action = null;
    horloge.current.restant = null;
    beatEnCours.current = null;
    if (ackTimer.current) clearTimeout(ackTimer.current);
    setEtat((e) => {
      if (e.status !== "playing" && e.status !== "paused" && e.status !== "opening_typing") { occupes.current = false; return e; }
      const step = scenario.steps[e.stepIndex];
      let messages = e.messages;
      let resultats = e.resultats;
      let sceneId = e.sceneId;
      let surface = e.surface;
      let sceneVersion = e.sceneVersion;
      let documentGenere = e.documentGenere;
      let canvasOuvert = e.canvasOuvert;
      let activites = e.activites;
      let preparation = e.preparation;
      for (let i = e.beatIndex; i < step.beats.length; i++) {
        const beat = step.beats[i];
        if (beat.type === "message") {
          const id = `msg-${scenario.id}-${step.id}-${i}`;
          if (!messages.some((m) => m.id === id)) {
            messages = [...messages, { id, speaker: beat.speaker, speakerLabel: beat.speaker === "flore" ? "Flore" : scenario.roleLabel, text: beat.text, stepId: step.id, evidenceIds: beat.evidenceIds || [], contenu: beat.contenu || null, termine: beat.speaker !== "flore" || !!beat.terminer, quand: new Date().toISOString(), anime: false }];
            if (beat.contenu?.documentCanvas) {
              documentGenere = true;
              canvasOuvert = true;
            }
            activites = beat.terminer ? terminerActivite(activites, { activityId: beat.terminer }) : avancerAncrageActivites(activites, messages.length);
          }
        } else if (beat.type === "activity_start" && !activites.some((a) => a.id === beat.id)) {
          activites = [...activites, { id: beat.id, stepId: step.id, status: "running", ops: [], apres: messages.length }];
        } else if (beat.type === "activity_step") {
          activites = appliquerEtape(activites, beat);
        } else if (beat.type === "activity_end") {
          activites = terminerActivite(activites, beat);
        } else if (beat.type === "prepare") {
          preparation = { surface: beat.surface, titre: beat.titre };
        } else if (beat.type === "prepare_end") {
          preparation = null;
        } else if (beat.type === "apply_scene" && (sceneId !== beat.sceneId || surface !== "atlas")) {
          sceneId = beat.sceneId;
          surface = "atlas";
          sceneVersion += 1;
        } else if (beat.type === "upsert_result" && resultats[beat.resultId]?.phase !== beat.phase) {
          resultats = { ...resultats, [beat.resultId]: { phase: beat.phase } };
        } else if (beat.type === "show_surface") {
          surface = beat.surface;
        }
      }
      const derniere = e.stepIndex >= scenario.steps.length - 1;
      occupes.current = false;
      return {
        ...e,
        messages,
        resultats,
        sceneId,
        surface,
        sceneVersion,
        documentGenere,
        canvasOuvert,
        activites,
        preparation,
        attente: null,
        saisie: null,
        frappeActive: false,
        playMode: "manual",
        stepIndex: derniere ? e.stepIndex : e.stepIndex + 1,
        beatIndex: 0,
        status: derniere ? "completed" : "awaiting_continue",
      };
    });
  }, [scenario]);

  const suivant = useCallback(() => {
    if (etat.status === "playing" || etat.status === "paused" || etat.status === "opening_typing") {
      completerSequence();
    } else if (etat.status === "awaiting_continue") {
      beatEnCours.current = null;
      setEtat((e) => ({ ...e, status: "playing" }));
    }
  }, [etat.status, completerSequence]);

  const lectureAuto = useCallback(() => {
    beatEnCours.current = null;
    setEtat((e) => ({ ...e, playMode: "auto", status: "playing" }));
  }, []);

  const revoirDecouverte = useCallback(() => {
    const idx = scenario.steps.findIndex((s) => s.id === scenario.discoveryStepId);
    if (idx < 0) return;
    generation.current += 1; // invalide tout retour asynchrone en vol (§6.4)
    effacerTimer();
    horloge.current.action = null;
    horloge.current.restant = null;
    beatEnCours.current = null;
    if (ackTimer.current) clearTimeout(ackTimer.current);
    setEtat((e) => {
      const gardes = e.messages.filter((m) => {
        const idxMsg = scenario.steps.findIndex((s) => s.id === m.stepId);
        return idxMsg >= 0 && idxMsg < idx; // fil coupé au début de la séquence de découverte
      });
      const surfaceAvant = scenario.steps
        .slice(0, idx)
        .flatMap((s) => s.beats)
        .filter((b) => b.type === "show_surface")
        .slice(-1)[0]?.surface;
      const upsertAvant = scenario.steps
        .slice(0, idx)
        .flatMap((s) => s.beats)
        .filter((b) => b.type === "upsert_result")
        .slice(-1)[0];
      return {
        ...e,
        messages: gardes.map((m) => ({ ...m, anime: false })),
        resultats: upsertAvant ? { [upsertAvant.resultId]: { phase: upsertAvant.phase } } : {},
        sceneId: null,
        surface: surfaceAvant || "nouveau",
        documentGenere: false,
        canvasOuvert: false,
        saisie: null,
        preparation: null,
        activites: e.activites.filter((a) => scenario.steps.findIndex((st) => st.id === a.stepId) < idx),
        stepIndex: idx,
        beatIndex: 0,
        attente: null,
        frappeActive: false,
        status: "playing",
        sceneVersion: e.sceneVersion + 1,
      };
    });
  }, [scenario]);

  // Le travail de démonstration suit le moteur : il naît, s'enrichit, puis se fige à la fin.
  // Le magasin est en mémoire seulement ; `versionTravaux` déclenche le rechargement des Récentes.
  const [versionTravaux, setVersionTravaux] = useState(0);
  useEffect(() => {
    const change = synchroniserTravauxDemo({
      fixtures,
      scenario,
      resultats: etat.resultats,
      messages: etat.messages,
      fige: etat.status === "completed",
    });
    if (change) setVersionTravaux((v) => v + 1);
  }, [etat.resultats, etat.messages, etat.status, fixtures, scenario]);

  // Consultation d'une preuve : suspend la lecture sans la casser (§7.6)
  const [preuveId, setPreuveId] = useState(null);
  const ouvrirPreuve = useCallback(
    (pid) => {
      setPreuveId(pid);
      pause("consultation d'une preuve");
    },
    [pause]
  );
  const fermerPreuve = useCallback(() => setPreuveId(null), []);

  const valeur = useMemo(
    () => ({ etat, versionTravaux, scenario, fixtures, pause, reprendre, suivant, lectureAuto, revoirDecouverte, acquitterScene, onAccueil, preuveId, ouvrirPreuve, fermerPreuve, demarrerOuverture }),
    [etat, versionTravaux, scenario, fixtures, pause, reprendre, suivant, lectureAuto, revoirDecouverte, acquitterScene, onAccueil, preuveId, ouvrirPreuve, fermerPreuve, demarrerOuverture]
  );

  // Contexte de pilotage lu par les VRAIES pages (Atlas, Nouveau travail, Travail, sidebar)
  const pilotage = useMemo(
    () => ({
      ouvert: false, // Flore latérale : la conversation vit dans la page Nouveau travail puis dans le Travail
      echanges: versEchanges(etat.messages, fixtures),
      conversation: etat.messages.map((m) => versMessageCase(m, fixtures)),
      // Ligne en cours (compatibilité) et toutes les lignes, ancrées dans le fil par `apres` —
      // avancée uniquement par `ajouterMessage`/`avancerAncrageActivites` (jamais recalculée ici,
      // à chaque rendu, sur « le dernier message actuel » : ça la ferait suivre n'importe quel
      // message, y compris celui qui la clôt, et donc parfois sauter par-dessus la réponse qu'elle
      // devrait précéder).
      activite: [...etat.activites].reverse().find((a) => a.status === "running") || null,
      activites: etat.activites,
      preparation: etat.preparation,
      enPause: etat.status === "paused",
      saisie: etat.saisie,
      ouvertureEnAttente: etat.status === "awaiting_opening",
      demarrerOuverture,
      envoyerSaisie,
      ouvrirPreuve,
      scenario,
      versionTravaux,
      lireTravail,
      travailOuvrable: etat.status === "completed",
      documentGenere: etat.documentGenere,
      canvasOuvert: etat.canvasOuvert,
    }),
    [etat.messages, etat.activites, etat.preparation, etat.status, etat.saisie, etat.documentGenere, etat.canvasOuvert, fixtures, scenario, versionTravaux, demarrerOuverture, envoyerSaisie, ouvrirPreuve]
  );

  return (
    <Ctx.Provider value={valeur}>
      <PilotageProvider value={pilotage}>
        <VerrouRoute etat={etat} />
        {children}
      </PilotageProvider>
    </Ctx.Provider>
  );
}

// Verrou de navigation : la route réelle suit l'étape du scénario — un clic hors parcours ne
// fait jamais quitter la démonstration. Ce sont les routes du produit, sans préfixe « démo ».
function VerrouRoute({ etat }) {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    const rid = Object.keys(etat.resultats)[0];
    const travail = rid ? `/travaux/${rid}` : "/atlas";
    if (etat.status === "completed") {
      // Parcours terminé : le travail figé et l'Atlas restent consultables
      if (location.pathname !== "/atlas" && location.pathname !== travail) navigate(travail, { replace: true });
      return;
    }
    let attendu = "/atlas";
    if (etat.surface === "nouveau" || etat.status === "opening_typing") attendu = "/travaux/nouveau";
    if (etat.surface === "travail") attendu = travail;
    // Du « Nouveau travail » au travail né : même page, le fil continue en place (state.continuite)
    if (location.pathname !== attendu) navigate(attendu, { replace: true, state: location.pathname === "/travaux/nouveau" && attendu === travail ? { continuite: true } : undefined });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etat.surface, etat.status, etat.resultats, location.pathname]);
  return null;
}

// Réseau local et identité du rôle : installés AVANT le premier rendu des pages (aucune requête
// ne part au backend), restaurés à la sortie.
function SessionKiosque({ profileId, onAccueil, children }) {
  const scenario = SCENARIOS[profileId];
  const fixtures = FIXTURES_PAR_PROFIL[profileId];
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
    <MoteurSession scenario={scenario} fixtures={fixtures} onAccueil={onAccueil}>
      {children}
    </MoteurSession>
  );
}

const KiosqueCtx = createContext({ actif: false, profils: [], demarrer: () => {}, quitter: () => {} });
export const useKiosque = () => useContext(KiosqueCtx);
export const usePolaris = () => useContext(Ctx);

// Enveloppe de l'application : sans profil choisi elle est transparente (pilotage = null,
// comportement produit inchangé). Choisir un profil monte la session autour des mêmes routes ;
// les providers de données se remontent alors sur le réseau local.
export function KiosqueProvider({ children }) {
  const navigate = useNavigate();
  const [profileId, setProfileId] = useState(null);

  const demarrer = useCallback(
    (id) => {
      if (!SCENARIOS[id]) return;
      setProfileId(id);
      navigate("/atlas"); // l'Atlas réel, accueil du produit — avec la main sur « Nouveau travail »
    },
    [navigate]
  );
  const quitter = useCallback(() => {
    setProfileId(null);
    navigate("/demo"); // retour au choix du profil, dans la zone de contenu de l'application
  }, [navigate]);

  const valeur = useMemo(() => ({ actif: !!profileId, demarrer, quitter }), [profileId, demarrer, quitter]);

  return (
    <KiosqueCtx.Provider value={valeur}>
      {profileId ? (
        <SessionKiosque key={profileId} profileId={profileId} onAccueil={quitter}>
          {children}
        </SessionKiosque>
      ) : (
        <PilotageProvider value={null}>{children}</PilotageProvider>
      )}
    </KiosqueCtx.Provider>
  );
}
