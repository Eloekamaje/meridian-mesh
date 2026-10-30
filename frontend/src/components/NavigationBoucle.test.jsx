import { act } from "react";
import { createRoot } from "react-dom/client";
import { TextDecoder, TextEncoder } from "util";
import api from "@/lib/api";

global.TextDecoder = TextDecoder;
global.TextEncoder = TextEncoder;
global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("react-router-dom", () => require("react-router"), { virtual: true });

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

jest.mock("@/lib/perimetre", () => ({
  usePerimetre: () => ({
    personas: [],
    persona: "architecte",
    changerPersona: () => {},
    espaces: [],
    vues: [],
    cible: "mesh-global",
    info: null,
    changerCible: () => {},
    authMode: "demo",
    version: 1,
  }),
}));

jest.mock("@/lib/contexte", () => ({
  useContexte: () => ({
    basculerFlore: () => {},
    repliAuto: false,
    floreOuverte: false,
    setSelection: () => {},
  }),
}));

jest.mock("@/lib/pilotage", () => ({ usePilotage: () => null }));
jest.mock("@/lib/identite", () => ({
  useIdentite: () => ({
    profil: { role: "Architecte" },
    initiales: "AB",
    nom: "Alice Bernard",
    sous: "Architecte",
  }),
}));
jest.mock("@/lib/evenements", () => ({ useEvenements: () => {} }));
jest.mock("@/lib/mesh", () => ({ useMesh: () => ({ mesh: null }) }));
jest.mock("@/lib/demo", () => ({ useDemo: () => ({ demarrer: () => {}, courant: -1 }) }));
jest.mock("@/lib/temps", () => ({ parseQuand: () => null }));
jest.mock("@/components/IndicateurClic", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/Notifications", () => ({ __esModule: true, default: () => null }));

const { MemoryRouter } = require("react-router");
const SidebarGauche = require("./SidebarGauche").default;
const Topbar = require("./Topbar").default;

function monter(element) {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine, element };
}

async function rendre({ hote, racine, element }) {
  await act(async () => {
    racine.render(<MemoryRouter>{element}</MemoryRouter>);
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  api.get.mockImplementation((url) => {
    if (url === "/cases") return Promise.resolve({ data: [] });
    if (url === "/tours/en-cours") return Promise.resolve({ data: { fils: [] } });
    if (url === "/notifications") return Promise.resolve({ data: { notifications: [], non_lues: 0 } });
    if (url === "/initiatives/compteurs") return Promise.resolve({ data: { a_traiter: 0 } });
    return Promise.resolve({ data: [] });
  });
});

test("la barre latérale expose l'entrée Boucle sans remplacer Actualités", async () => {
  const monte = monter(<SidebarGauche mode="bureau" />);
  await rendre(monte);

  const boucle = monte.hote.querySelector('[data-testid="nav-boucle"]');
  expect(boucle).not.toBeNull();
  expect(boucle.getAttribute("href")).toBe("/boucle");
  expect(boucle.textContent).toContain("Boucle");
  expect(monte.hote.querySelector('[data-testid="nav-actualites"]').getAttribute("href")).toBe("/actualites");

  await act(async () => { monte.racine.unmount(); });
});

test("la barre supérieure expose l'entrée Boucle", async () => {
  const monte = monter(<Topbar />);
  await rendre(monte);

  const boucle = monte.hote.querySelector('[data-testid="nav-boucle"]');
  expect(boucle).not.toBeNull();
  expect(boucle.getAttribute("href")).toBe("/boucle");
  expect(boucle.textContent).toContain("Boucle");

  await act(async () => { monte.racine.unmount(); });
});
