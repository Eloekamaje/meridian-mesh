// Moteur de lecture Polaris : une seule horloge pilote messages, activité et scènes.
// - Pause/reprise avec délai restant conservé (§6.3) — beat en cours jamais redémarré
// - Suivant : termine la séquence courante jusqu'à son checkpoint, sans doublon (M02)
// - Revoir la découverte : restaure le checkpoint antérieur puis rejoue (M04)
// - Anti-course : generation incrémentée à chaque restauration ; ids déterministes (§6.4)
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { validerScenario } from "./scenarioSchema";

export const RYTHME = {
  lectureMin: 2500,
  lectureParMot: 260,
  frappeMsParLot: 18, // 3 caractères par lot (télétype)
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

export function PolarisSessionProvider({ scenario, fixtures, onAccueil, children }) {
  const [erreursValidation] = useState(() => validerScenario(scenario, fixtures));
  const [etat, setEtat] = useState(() => ({
    status: erreursValidation.length ? "error" : "initializing",
    erreur: erreursValidation.length ? `Scénario invalide :\n${erreursValidation.join("\n")}` : null,
    playMode: "auto",
    stepIndex: 0,
    beatIndex: 0,
    messages: [],
    activite: null, // { label, ops: [{label, status}] }
    surface: "flore",
    sceneId: null,
    resultats: {},
    attente: null, // { commandId } pendant apply_scene
    sceneVersion: 0,
    frappeActive: false,
    motif: null,
  }));

  const horloge = useRef({ timer: null, finA: 0, action: null, restant: null });
  const ackTimer = useRef(null); // chien de garde d'acquittement : survit aux nettoyages d'effet
  const generation = useRef(0);
  const beatEnCours = useRef(null); // clé du beat démarré : pause/reprise ne le redémarre jamais
  const occupes = useRef(false);

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
    setEtat((e) => ({ ...e, beatIndex: e.beatIndex + 1, attente: null, activite: e.activite }));
  }, []);

  // Ajout idempotent par identifiant déterministe (jamais de doublon, M07)
  const ajouterMessage = useCallback(
    (step, idx, beat) => {
      setEtat((e) => {
        const id = `msg-${scenario.id}-${step.id}-${idx}`;
        if (e.messages.some((m) => m.id === id)) return e;
        return {
          ...e,
          activite: null,
          messages: [
            ...e.messages,
            {
              id,
              speaker: beat.speaker,
              speakerLabel: beat.speaker === "flore" ? "Flore" : scenario.roleLabel,
              text: beat.text,
              stepId: step.id,
              evidenceIds: beat.evidenceIds || [],
              anime: true,
            },
          ],
          frappeActive: beat.speaker === "flore",
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
        setEtat((e) => ({ ...e, status: "completed", activite: null }));
      } else if (etat.playMode === "auto") {
        setEtat((e) => ({ ...e, stepIndex: e.stepIndex + 1, beatIndex: 0, activite: null }));
      } else {
        setEtat((e) => ({ ...e, status: "awaiting_continue", activite: null }));
      }
      return;
    }

    switch (beat.type) {
      case "message": {
        ajouterMessage(step, etat.beatIndex, beat);
        planifier(dureeMessage(beat.text), () => {
          setEtat((e) => ({ ...e, frappeActive: false }));
          avancer();
        });
        break;
      }
      case "activity": {
        const ops = beat.ops.map((label) => ({ label, status: "pending" }));
        setEtat((e) => ({ ...e, activite: { label: beat.label, ops } }));
        const jouerOp = (i) => {
          if (i >= ops.length) {
            setEtat((e) =>
              e.activite ? { ...e, activite: { ...e.activite, ops: e.activite.ops.map((o) => ({ ...o, status: "done" })) } } : e
            );
            planifier(600, avancer);
            return;
          }
          setEtat((e) => {
            if (!e.activite) return e;
            const ops2 = e.activite.ops.map((o, k) => (k < i ? { ...o, status: "done" } : k === i ? { ...o, status: "running" } : o));
            return { ...e, activite: { ...e.activite, ops: ops2 } };
          });
          planifier(dureeOp(i), () => jouerOp(i + 1));
        };
        jouerOp(0);
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
          activite: null,
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
          e.resultats[beat.resultId]
            ? e
            : { ...e, resultats: { ...e.resultats, [beat.resultId]: structuredClone(fixtures.resultats[beat.resultId]) } }
        );
        planifier(300, avancer);
        break;
      }
      case "show_surface": {
        setEtat((e) => ({ ...e, activite: null, surface: beat.surface }));
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
  }, [etat.stepIndex, etat.beatIndex, etat.playMode, etat.sceneId, etat.surface, etat.attente, scenario, fixtures, ajouterMessage, planifier, avancer]);

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
    setEtat((e) => (e.status === "playing" ? { ...e, status: "paused", motif, frappeActive: false } : e));
  }, []);

  const reprendre = useCallback(() => {
    const { action, restant } = horloge.current;
    setEtat((e) => {
      if (e.status === "error") {
        beatEnCours.current = null; // Réessayer : rejoue le beat fautif
        return { ...e, status: "playing", erreur: null };
      }
      return e.status === "paused" ? { ...e, status: "playing", motif: null } : e;
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
      if (e.status !== "playing" && e.status !== "paused") { occupes.current = false; return e; }
      const step = scenario.steps[e.stepIndex];
      let messages = e.messages;
      let resultats = e.resultats;
      let sceneId = e.sceneId;
      let surface = e.surface;
      let sceneVersion = e.sceneVersion;
      for (let i = e.beatIndex; i < step.beats.length; i++) {
        const beat = step.beats[i];
        if (beat.type === "message") {
          const id = `msg-${scenario.id}-${step.id}-${i}`;
          if (!messages.some((m) => m.id === id)) {
            messages = [...messages, { id, speaker: beat.speaker, speakerLabel: beat.speaker === "flore" ? "Flore" : scenario.roleLabel, text: beat.text, stepId: step.id, evidenceIds: beat.evidenceIds || [], anime: false }];
          }
        } else if (beat.type === "apply_scene" && (sceneId !== beat.sceneId || surface !== "atlas")) {
          sceneId = beat.sceneId;
          surface = "atlas";
          sceneVersion += 1;
        } else if (beat.type === "upsert_result" && !resultats[beat.resultId]) {
          resultats = { ...resultats, [beat.resultId]: structuredClone(fixtures.resultats[beat.resultId]) };
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
        activite: null,
        attente: null,
        frappeActive: false,
        playMode: "manual",
        stepIndex: derniere ? e.stepIndex : e.stepIndex + 1,
        beatIndex: 0,
        status: derniere ? "completed" : "awaiting_continue",
      };
    });
  }, [scenario, fixtures]);

  const suivant = useCallback(() => {
    if (etat.status === "playing" || etat.status === "paused") {
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
      const sceneAvant = scenario.steps
        .slice(0, idx)
        .flatMap((s) => s.beats)
        .filter((b) => b.type === "apply_scene")
        .slice(-1)[0]?.sceneId;
      const resultatAvant = scenario.steps
        .slice(0, idx)
        .flatMap((s) => s.beats)
        .some((b) => b.type === "upsert_result");
      return {
        ...e,
        messages: gardes.map((m) => ({ ...m, anime: false })),
        resultats: resultatAvant ? e.resultats : {},
        sceneId: sceneAvant ?? null,
        surface: sceneAvant ? "atlas" : "flore",
        stepIndex: idx,
        beatIndex: 0,
        activite: null,
        attente: null,
        frappeActive: false,
        status: "playing",
        sceneVersion: e.sceneVersion + 1,
      };
    });
  }, [scenario]);

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
    () => ({ etat, scenario, fixtures, pause, reprendre, suivant, lectureAuto, revoirDecouverte, acquitterScene, onAccueil, preuveId, ouvrirPreuve, fermerPreuve }),
    [etat, scenario, fixtures, pause, reprendre, suivant, lectureAuto, revoirDecouverte, acquitterScene, onAccueil, preuveId, ouvrirPreuve, fermerPreuve]
  );

  return <Ctx.Provider value={valeur}>{children}</Ctx.Provider>;
}

export const usePolaris = () => useContext(Ctx);
