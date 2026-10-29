import { brouillonLisible } from "./fluxFlore";

test("le brouillon s'affiche sans citations ni schéma à la main", () => {
  expect(brouillonLisible("Elle publie (`app/routes.py#L64-L64`) un article `a.py#L3`.")).toBe("Elle publie un article.");
  expect(brouillonLisible("Voici\n```mermaid\nflowchart LR\na --> b")).toBe("Voici\n");
});

import { TextDecoder } from "util";
import { demanderEnFlux, estArret } from "./fluxFlore";

test("le signal est transmis à fetch et l'arrêt rejette une AbortError", async () => {
  global.TextDecoder = global.TextDecoder || TextDecoder;
  const ctrl = new AbortController();
  let signalVu;
  global.fetch = jest.fn((url, opts) => {
    signalVu = opts.signal;
    return Promise.resolve({
      ok: true,
      body: { getReader: () => ({ read: () => new Promise((_, rej) => {
        opts.signal.addEventListener("abort", () => rej(Object.assign(new Error("aborted"), { name: "AbortError" })));
      }) }) },
    });
  });
  const promesse = demanderEnFlux("/cases/x/messages/flux", { texte: "q" }, { signal: ctrl.signal });
  await Promise.resolve();
  ctrl.abort();
  const err = await promesse.catch((e) => e);
  expect(signalVu).toBe(ctrl.signal);
  expect(estArret(err)).toBe(true);
});

import { lecteurAgUi } from "./fluxFlore";

test("un tour AG-UI : étapes, outil (début, arguments, issue), brouillon, relecture, réponse", () => {
  const vus = { etapes: [], textes: [], outils: [], relu: 0 };
  const lire = lecteurAgUi({
    onEtape: (l) => vus.etapes.push(l), onTexte: (d) => vus.textes.push(d),
    onRelecture: () => { vus.relu += 1; }, onOutil: (o) => vus.outils.push(o),
  });
  const fin = [
    { type: "RUN_STARTED", threadId: "t1", runId: "r" },
    { type: "STEP_STARTED", stepName: "Je regarde Conduit…" },
    { type: "TOOL_CALL_START", toolCallId: "u1", toolCallName: "lire_code", metadata: { libelle: "Je lis le code concerné…" } },
    { type: "TOOL_CALL_ARGS", toolCallId: "u1", delta: '{"chemin":' },
    { type: "TOOL_CALL_ARGS", toolCallId: "u1", delta: '"a.py"}' },
    { type: "TOOL_CALL_END", toolCallId: "u1" },
    { type: "TOOL_CALL_RESULT", toolCallId: "u1", messageId: "m", content: "def f()", metadata: { etat: "fait", duree: 0.1 } },
    { type: "TEXT_MESSAGE_START", messageId: "m" }, { type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: "Bon" },
    { type: "TEXT_MESSAGE_END", messageId: "m" }, { type: "CUSTOM", name: "relecture" },
    { type: "STEP_FINISHED", stepName: "Je regarde Conduit…" },
    { type: "RUN_FINISHED", result: { reponse: "Bonjour" } },
  ].map(lire).find((r) => r?.fin);
  expect(fin.fin).toEqual({ reponse: "Bonjour" });
  expect(vus.etapes).toEqual(["Je regarde Conduit…"]); // avec onOutil, l'outil n'est pas aussi une étape
  expect(vus.textes).toEqual(["Bon"]);
  expect(vus.relu).toBe(1);
  expect(vus.outils.at(-1)).toEqual({ id: "u1", nom: "lire_code", libelle: "Je lis le code concerné…", etat: "fait",
    arguments: { chemin: "a.py" }, extrait: "def f()", duree: 0.1 });
  expect(vus.outils[0].etat).toBe("en_cours");
});

test("RUN_ERROR rejette une erreur annoncée", () => {
  const lire = lecteurAgUi({});
  expect(() => lire({ type: "RUN_ERROR", message: "Case introuvable" })).toThrow("Case introuvable");
  try { lire({ type: "RUN_ERROR", message: "x" }); } catch (e) { expect(e.annoncee).toBe(true); }
});

test("sans onOutil, un outil s'annonce comme une étape (appelants qui ne montrent que des libellés)", () => {
  const etapes = [];
  lecteurAgUi({ onEtape: (l) => etapes.push(l) })({ type: "TOOL_CALL_START", toolCallId: "u", toolCallName: "x", metadata: { libelle: "Je lis…" } });
  expect(etapes).toEqual(["Je lis…"]);
});

import { journalActivite, activiteDuTour } from "./fluxFlore";

test("le journal d'activité garde l'ordre : étapes et outils, un outil mis à jour à sa place", () => {
  const vus = [];
  const j = journalActivite((ops) => vus.push(ops));
  j.onEtape("Je regarde Conduit…");
  j.onOutil({ id: "u1", nom: "lire_code", libelle: "Je lis le code…", etat: "en_cours" });
  j.onEtape("Je corrige après relecture…");
  j.onOutil({ id: "u1", nom: "lire_code", libelle: "Je lis le code…", etat: "fait", duree: 0.2 });
  expect(vus.at(-1).map((o) => o.label)).toEqual(["Je regarde Conduit…", "Je lis le code…", "Je corrige après relecture…"]);
  expect(vus.at(-1)[1].outil.etat).toBe("fait");
  expect(vus[0]).not.toBe(vus[1]); // une nouvelle liste à chaque changement (rendu React)
  const fin = activiteDuTour(j.ops, "x");
  expect(fin.status).toBe("done");
  expect(fin.ops.every((o) => o.status === "done")).toBe(true);
  expect(activiteDuTour([], "x")).toBeNull();
});

// Un faux corps de réponse : des événements AG-UI, puis éventuellement une coupure de réseau.
const corpsSSE = (evts, coupure = false) => {
  const morceaux = evts.map((e) => new TextEncoder().encode(`data: ${JSON.stringify(e)}\n\n`));
  return { getReader: () => ({ read: async () => {
    if (morceaux.length) return { value: morceaux.shift(), done: false };
    if (coupure) throw new TypeError("network error");
    return { value: undefined, done: true };
  } }) };
};

test("une coupure se reprend depuis le dernier événement lu, et la réponse arrive", async () => {
  global.TextDecoder = global.TextDecoder || TextDecoder;
  global.TextEncoder = global.TextEncoder || require("util").TextEncoder;
  const appels = [];
  global.fetch = jest.fn((url) => {
    appels.push(url);
    if (appels.length === 1) {
      return Promise.resolve({ ok: true, body: corpsSSE([{ type: "RUN_STARTED", threadId: "t", runId: "R1" },
        { type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: "Bon" }], true) });
    }
    return Promise.resolve({ ok: true, body: corpsSSE([{ type: "TEXT_MESSAGE_CONTENT", messageId: "m", delta: "jour" },
      { type: "RUN_FINISHED", result: { reponse: "Bonjour" } }]) });
  });
  const textes = [];
  const coupures = [];
  const promesse = demanderEnFlux("/cases/t/messages/flux", { texte: "q" },
    { onTexte: (d) => textes.push(d), onCoupure: (c) => coupures.push(c) });
  expect(await promesse).toEqual({ reponse: "Bonjour" });
  expect(appels[1]).toMatch(/\/api\/tours\/R1\/flux\?depuis=2$/);
  expect(textes).toEqual(["Bon", "jour"]);
  expect(coupures).toEqual([true, false]);
}, 10000);

test("« Arrêter » demande l'arrêt du tour au serveur avant de rendre la main", async () => {
  global.TextDecoder = global.TextDecoder || TextDecoder;
  global.TextEncoder = global.TextEncoder || require("util").TextEncoder;
  const ctrl = new AbortController();
  const appels = [];
  global.fetch = jest.fn((url, opts) => {
    appels.push([url, opts?.method]);
    if (appels.length > 1) return Promise.resolve({ ok: true, json: async () => ({ arrete: true }) });
    let envoye = false;
    return Promise.resolve({ ok: true, body: { getReader: () => ({ read: () => {
      if (!envoye) {
        envoye = true;
        return Promise.resolve({ value: new TextEncoder().encode(`data: ${JSON.stringify({ type: "RUN_STARTED", threadId: "t", runId: "R2" })}\n\n`), done: false });
      }
      return new Promise((_, rej) => opts.signal.addEventListener("abort", () => rej(Object.assign(new Error("a"), { name: "AbortError" }))));
    } }) } });
  });
  const promesse = demanderEnFlux("/cases/t/messages/flux", { texte: "q" }, { signal: ctrl.signal });
  await new Promise((r) => setTimeout(r, 0));
  ctrl.abort();
  const err = await promesse.catch((e) => e);
  expect(estArret(err)).toBe(true);
  expect(appels[1]).toEqual([expect.stringMatching(/\/api\/tours\/R2\/arreter$/), "POST"]);
});
