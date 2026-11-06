import { act } from "react";
import { createRoot } from "react-dom/client";
import { toast } from "sonner";
import api from "@/lib/api";
import RevuePublication from "./RevuePublication";

let mockActeur = "reviewer";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));
jest.mock("@/lib/perimetre", () => ({
  usePerimetre: () => ({ acteur: mockActeur, version: 0 }),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

const jumeaux = [
  { id: "paiements", nom: "Paiements", equipe: "Équipe Paiements", claims: 12 },
  { id: "comptes", nom: "Comptes", equipe: "Équipe Comptes", claims: 8 },
];

const partage = (id, extra = {}) => ({
  id,
  claim_id: 100 + id,
  objet: `Objet ${id}`,
  confidentialite: "CONFIDENTIAL",
  scope_type: "TENANT",
  scope_id: "acme",
  granted_by: "alice",
  ...extra,
});

let reponsesFile = [];

function installerApi() {
  api.get.mockImplementation((url) => {
    if (url === "/v2/jumeaux") return Promise.resolve({ data: jumeaux });
    if (url.endsWith("/carte/a-reviser")) return Promise.resolve({ data: reponsesFile.shift() ?? [] });
    return Promise.resolve({ data: {} });
  });
}

function saisir(input, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(input, valeur);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function choisir(select, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
  setter.call(select, valeur);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

async function rendre() {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => { racine.render(<RevuePublication />); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  return { hote, racine };
}

async function choisirJumeau(hote, id = "paiements") {
  await act(async () => { choisir(hote.querySelector('[data-testid="revue-publication-jumeau"]'), id); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockActeur = "reviewer";
  reponsesFile = [];
  installerApi();
  api.post.mockResolvedValue({ data: { ok: true } });
});

test("charge les jumeaux puis la file de revue du jumeau choisi", async () => {
  reponsesFile = [[partage(7), partage(8)]];
  const { hote, racine } = await rendre();

  expect(api.get).toHaveBeenCalledWith("/v2/jumeaux");
  expect(hote.textContent).toContain("Paiements");
  expect(hote.querySelector('[data-testid="revue-publication-attente"]')).not.toBeNull();

  await choisirJumeau(hote);

  expect(api.get).toHaveBeenCalledWith("/v2/jumeaux/paiements/carte/a-reviser");
  expect(hote.querySelector('[data-testid="revue-publication-attente"]')).toBeNull();
  const ligne = hote.querySelector('[data-testid="partage-7"]');
  expect(ligne).not.toBeNull();
  expect(ligne.textContent).toContain("Objet 7");
  expect(ligne.textContent).toContain("Confidentiel");
  expect(ligne.textContent).toContain("Tenant");
  expect(ligne.textContent).toContain("alice");
  expect(hote.querySelector('[data-testid="approuver-7"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="rejeter-7"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("approuve un partage avec sa raison puis recharge la file", async () => {
  reponsesFile = [[partage(7)]];
  const { hote, racine } = await rendre();
  await choisirJumeau(hote);

  await act(async () => {
    saisir(hote.querySelector('[data-testid="raison-7"]'), "Validé par le comité du 5 novembre");
  });
  await act(async () => { hote.querySelector('[data-testid="approuver-7"]').click(); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

  expect(api.post).toHaveBeenCalledWith("/v2/jumeaux/paiements/carte/revue", {
    share_id: 7,
    decision: "APPROVED",
    reason: "Validé par le comité du 5 novembre",
  });
  expect(hote.querySelector('[data-testid="revue-publication-retour"]').textContent).toContain("Partage #7 approuvé");
  expect(hote.querySelector('[data-testid="revue-publication-vide"]')).not.toBeNull();
  expect(toast.success).toHaveBeenCalledWith("Publication approuvée");

  await act(async () => { racine.unmount(); });
});

test("rejette un partage et affiche l'erreur du backend sans retirer la ligne", async () => {
  reponsesFile = [[partage(9, { granted_by: "bob" })]];
  api.post.mockRejectedValue({
    response: { data: { detail: "revue à quatre yeux : reviewer distinct de granted_by" } },
  });
  const { hote, racine } = await rendre();
  await choisirJumeau(hote);

  await act(async () => { hote.querySelector('[data-testid="rejeter-9"]').click(); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

  expect(api.post).toHaveBeenCalledWith("/v2/jumeaux/paiements/carte/revue", {
    share_id: 9,
    decision: "REJECTED",
    reason: null,
  });
  const retour = hote.querySelector('[data-testid="revue-publication-retour"]');
  expect(retour.getAttribute("role")).toBe("alert");
  expect(retour.textContent).toContain("revue à quatre yeux");
  expect(hote.querySelector('[data-testid="partage-9"]')).not.toBeNull();
  expect(toast.error).toHaveBeenCalledWith("revue à quatre yeux : reviewer distinct de granted_by");

  await act(async () => { racine.unmount(); });
});

test("désactive la décision quand le partage a été demandé par le reviewer", async () => {
  mockActeur = "alice";
  reponsesFile = [[partage(10, { granted_by: "alice" })]];
  const { hote, racine } = await rendre();
  await choisirJumeau(hote);

  expect(hote.querySelector('[data-testid="approuver-10"]').disabled).toBe(true);
  expect(hote.querySelector('[data-testid="rejeter-10"]').disabled).toBe(true);
  expect(hote.querySelector('[data-testid="quatre-yeux-10"]').textContent).toContain("Un autre reviewer doit décider");

  await act(async () => { racine.unmount(); });
});
