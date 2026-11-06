// Le viewport du chat doit ajuster largeur et hauteur, sinon un diagramme vertical est coupé.
import { act } from "react";
import { createRoot } from "react-dom/client";
import DiagrammeCompile from "./DiagrammeCompile";

global.IS_REACT_ACT_ENVIRONMENT = true;

const DIAGRAMME = {
  largeur: 1000,
  hauteur: 1000,
  titre: "Test",
  svg: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000"><title>Test</title><desc>Test</desc></svg>',
};

test("Ajuster tient compte de la hauteur du viewport", async () => {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  await act(async () => { racine.render(<DiagrammeCompile diagramme={DIAGRAMME} />); });

  const viewport = hote.querySelector('[data-testid="diagramme-compile-viewport"]');
  Object.defineProperty(viewport, "clientWidth", { configurable: true, value: 800 });
  Object.defineProperty(viewport, "clientHeight", { configurable: true, value: 300 });
  const ajuster = [...hote.querySelectorAll("button")].find((bouton) => bouton.textContent === "Ajuster");
  await act(async () => { ajuster.click(); });

  expect(hote.textContent).toContain("30%");
  const plan = viewport.firstElementChild;
  expect(plan.style.transform).toContain("translate(250px");
  await act(async () => { racine.unmount(); });
});
