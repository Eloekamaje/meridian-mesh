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
