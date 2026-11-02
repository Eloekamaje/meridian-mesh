import { act } from "react";
import { createRoot } from "react-dom/client";
import CanvasDocument from "./CanvasDocument";

jest.mock("@/components/MarkdownFlore", () => () => <div data-testid="markdown" />);

global.IS_REACT_ACT_ENVIRONMENT = true;

test("le Canvas rend un artefact de pilotage, pas seulement un Markdown", async () => {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(<CanvasDocument titre="Capacité" artefact={{
      type: "planification.capacite", equipes: [{ equipe_id: "A", nom: "Équipe A",
        elements_actifs: 1, charges: [{ unite: "points", connue: 3, capacite: 5, marge: 2 }] }],
    }} />);
  });
  expect(hote.querySelector('[data-testid="canvas-document"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="artefact-capacite"]')).not.toBeNull();
  expect(hote.textContent).toContain("Équipe A");
  await act(async () => { racine.unmount(); });
});

test("le Canvas rend aussi un SVG compilé", async () => {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="red"/></svg>';
  await act(async () => { racine.render(<CanvasDocument titre="diagramme.svg" artefact={{ type: "svg", titre: "Diagramme", svg }} />); });
  const image = hote.querySelector('img[alt="Diagramme"]');
  expect(image).not.toBeNull();
  expect(image.src.startsWith("data:image/svg+xml;base64,")).toBe(true);
  await act(async () => { racine.unmount(); });
});
