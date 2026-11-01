import { act } from "react";
import { createRoot } from "react-dom/client";
import { TextDecoder, TextEncoder } from "util";

// jsdom (Jest 27) ne fournit pas TextEncoder, requis par react-router 7.
global.TextDecoder = TextDecoder;
global.TextEncoder = TextEncoder;

// react-router-dom 7 n'expose pas de « main » résolvable par Jest 27 : le cœur react-router fournit
// les mêmes composants (BrowserRouter, Routes, Route, Navigate, Outlet, useLocation…).
jest.mock("react-router-dom", () => require("react-router"), { virtual: true });

const { MemoryRouter, useLocation } = require("react-router");
const { RoutesProduit } = require("./App");

function mockPage(testid) {
  const React = require("react");
  return { __esModule: true, default: () => React.createElement("div", { "data-testid": testid }) };
}

jest.mock("@/components/Layout", () => {
  const React = require("react");
  const { Outlet } = require("react-router");
  const Layout = () => React.createElement("div", { "data-testid": "layout" }, React.createElement(Outlet));
  return { __esModule: true, default: Layout };
});

jest.mock("@/pages/Actualites", () => mockPage("page-actualites"));
jest.mock("@/pages/Boucle", () => mockPage("page-boucle"));
jest.mock("@/pages/Cognition", () => mockPage("page-cognition"));
jest.mock("@/pages/Atlas", () => mockPage("page-atlas"));
jest.mock("@/pages/Comprendre", () => mockPage("page-comprendre"));
jest.mock("@/pages/LaboAtlas", () => mockPage("page-labo-atlas"));
jest.mock("@/pages/LaboEchelle", () => mockPage("page-labo-echelle"));
jest.mock("@/pages/LaboSemantique", () => mockPage("page-labo-semantique"));
jest.mock("@/pages/LaboServeur", () => mockPage("page-labo-serveur"));
jest.mock("@/pages/LaboAtlasEtendu", () => mockPage("page-labo-atlas-etendu"));
jest.mock("@/pages/Commande", () => mockPage("page-commande"));
jest.mock("@/pages/Travaux", () => mockPage("page-travaux"));
jest.mock("@/pages/TravailDetail", () => mockPage("page-travail-detail"));
jest.mock("@/pages/Jumeaux", () => mockPage("page-jumeaux"));
jest.mock("@/pages/RevueJumeau", () => mockPage("page-revue-jumeau"));
jest.mock("@/pages/Administration", () => mockPage("page-administration"));

global.IS_REACT_ACT_ENVIRONMENT = true;

function SondeChemin() {
  const { pathname } = useLocation();
  return <div data-testid="chemin">{pathname}</div>;
}

async function ouvrir(chemin) {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(
      <MemoryRouter initialEntries={[chemin]}>
        <RoutesProduit />
        <SondeChemin />
      </MemoryRouter>
    );
  });
  return { hote, racine };
}

async function fermer(racine) {
  await act(async () => { racine.unmount(); });
}

test("/ ouvre Aujourd'hui (Actualités) et ne redirige plus vers l'Atlas", async () => {
  const { hote, racine } = await ouvrir("/");
  expect(hote.querySelector('[data-testid="chemin"]').textContent).toBe("/actualites");
  expect(hote.querySelector('[data-testid="page-actualites"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="page-atlas"]')).toBeNull();
  await fermer(racine);
});

test("/aujourdhui affiche Aujourd'hui sans redirection vers l'Atlas", async () => {
  const { hote, racine } = await ouvrir("/aujourdhui");
  expect(hote.querySelector('[data-testid="chemin"]').textContent).toBe("/aujourdhui");
  expect(hote.querySelector('[data-testid="page-actualites"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="page-atlas"]')).toBeNull();
  await fermer(racine);
});

test("/actualites reste un lien profond vers Aujourd'hui", async () => {
  const { hote, racine } = await ouvrir("/actualites");
  expect(hote.querySelector('[data-testid="chemin"]').textContent).toBe("/actualites");
  expect(hote.querySelector('[data-testid="page-actualites"]')).not.toBeNull();
  await fermer(racine);
});

test("/boucle affiche la page Boucle sans changer l'accueil", async () => {
  const { hote, racine } = await ouvrir("/boucle");
  expect(hote.querySelector('[data-testid="chemin"]').textContent).toBe("/boucle");
  expect(hote.querySelector('[data-testid="page-boucle"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="page-actualites"]')).toBeNull();
  await fermer(racine);
});

test("/cognition affiche la page Cognition", async () => {
  const { hote, racine } = await ouvrir("/cognition");
  expect(hote.querySelector('[data-testid="chemin"]').textContent).toBe("/cognition");
  expect(hote.querySelector('[data-testid="page-cognition"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="page-actualites"]')).toBeNull();
  await fermer(racine);
});

test("/atlas reste accessible comme route d'exploration", async () => {
  const { hote, racine } = await ouvrir("/atlas");
  expect(hote.querySelector('[data-testid="chemin"]').textContent).toBe("/atlas");
  expect(hote.querySelector('[data-testid="page-atlas"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="page-actualites"]')).toBeNull();
  await fermer(racine);
});

test("/carte redirige toujours vers l'Atlas", async () => {
  const { hote, racine } = await ouvrir("/carte");
  expect(hote.querySelector('[data-testid="chemin"]').textContent).toBe("/atlas");
  expect(hote.querySelector('[data-testid="page-atlas"]')).not.toBeNull();
  await fermer(racine);
});
