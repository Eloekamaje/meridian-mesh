// Rendu réel des deux sections, avec l'API simulée : les data-testid et les appels attendus sont vérifiés sans
// testing-library, comme le reste des tests de composants du projet.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { toast } from "sonner";
import api from "@/lib/api";
import InterfacesJumeau from "./InterfacesJumeau";
import PromotionJumeau from "./PromotionJumeau";

jest.mock("@/lib/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  jest.clearAllMocks();
});

const donnees = {
  jumeau_id: "app-1",
  application_id: "app-1",
  tenant: "local",
  interfaces: {
    contracts: [{ id: "ctr-1", format: "openapi", version: "1.2", environment: "production", locator: "openapi.yaml" }],
    operations: [{ id: "op-1", method: "GET", path: "/sante", name: "sante", environment: "production" }],
    bindings: [],
    assertions: [
      { subject: "app-1", predicate: "EXPOSE", object: "GET /sante", mode: "declared", source: "openapi", environment: "production", confidence: 0.95 },
      { subject: "app-1", predicate: "CONSOMME", object: "https://user:secret@exemple.test/api?token=abc&page=1", mode: "declared", source: "config", environment: "production", confidence: 0.4 },
    ],
  },
  runs: [{
    id: "run-1",
    status: "ok",
    started_at: "2026-10-30T06:00:00Z",
    stats: { contracts: 1, operations: 1, assertions: 1 },
    changes: [{ type: "operation_added", subject: "app-1", before: null, after: "GET /sante", severity: "info" }],
    impacts: [],
  }],
};

const jumeauProvisoire = {
  id: "app-1",
  nom: "Nouveau jumeau",
  mission: "dfggg",
  niveau: "complet",
  origine: "reel",
  sources_detail: [{ nom: "Dépôt gsf-mockup · main · abc123" }],
};

function monter(element) {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine };
}

function saisir(input, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(input, valeur);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

test("InterfacesJumeau affiche contrats, opérations, assertions et le dernier run", async () => {
  api.get.mockResolvedValue({ data: donnees });
  const { hote, racine } = monter();
  await act(async () => { racine.render(<InterfacesJumeau jid="app-1" />); });

  expect(api.get).toHaveBeenCalledWith("/jumeaux/app-1/interfaces");
  expect(hote.querySelector('[data-testid="interfaces-jumeau"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="interfaces-contrat"]').textContent).toContain("OPENAPI");
  expect(hote.querySelector('[data-testid="interfaces-operation"]').textContent).toContain("/sante");
  expect(hote.querySelector('[data-testid="interfaces-assertion"]').textContent).toContain("EXPOSE");
  expect(hote.querySelector('[data-testid="interfaces-assertion"]').textContent).toContain("95 %");
  const assertions = [...hote.querySelectorAll('[data-testid="interfaces-assertion"]')].map((n) => n.textContent).join(" ");
  expect(assertions).not.toContain("user:secret");
  expect(assertions).not.toContain("token=abc");
  expect(assertions).toContain("***");
  expect(hote.querySelector('[data-testid="interfaces-run"]').textContent).toContain("ok");
  expect(hote.querySelector('[data-testid="interfaces-run"]').textContent).toContain("Opération ajoutée");

  await act(async () => { racine.unmount(); });
});

test("PromotionJumeau préremplit le dépôt et poste nom, mission et motif puis recharge la revue", async () => {
  api.post.mockResolvedValue({ data: { jumeau_id: "app-1" } });
  const onPromu = jest.fn();
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(<PromotionJumeau jumeau={jumeauProvisoire} jid="app-1" onPromu={onPromu} />);
  });

  const nom = hote.querySelector('[data-testid="promotion-nom"]');
  const mission = hote.querySelector('[data-testid="promotion-mission"]');
  const motif = hote.querySelector('[data-testid="promotion-motif"]');
  expect(nom.value).toBe("gsf-mockup");
  expect(mission.value).toBe("");

  act(() => {
    saisir(nom, "Gestion des paiements");
    saisir(mission, "Traite les paiements des clients");
    saisir(motif, "Identité confirmée par l'équipe");
  });
  await act(async () => {
    hote.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });

  expect(api.post).toHaveBeenCalledWith("/jumeaux/app-1/promouvoir", {
    nom: "Gestion des paiements",
    mission: "Traite les paiements des clients",
    motif: "Identité confirmée par l'équipe",
  });
  expect(toast.success).toHaveBeenCalled();
  expect(onPromu).toHaveBeenCalled();

  await act(async () => { racine.unmount(); });
});

test("PromotionJumeau signale un 409 sans recharger la revue", async () => {
  api.post.mockRejectedValue({ response: { status: 409, data: { detail: "Ce jumeau est déjà une application canonique" } } });
  const onPromu = jest.fn();
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(<PromotionJumeau jumeau={jumeauProvisoire} jid="app-1" onPromu={onPromu} />);
  });
  act(() => {
    saisir(hote.querySelector('[data-testid="promotion-nom"]'), "Gestion des paiements");
    saisir(hote.querySelector('[data-testid="promotion-mission"]'), "Traite les paiements des clients");
  });
  await act(async () => {
    hote.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });

  expect(toast.error).toHaveBeenCalledWith("Ce jumeau est déjà une application canonique");
  expect(onPromu).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-testid="promotion-succes"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("PromotionJumeau reste absente pour un twin déjà canonique", async () => {
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(<PromotionJumeau jumeau={{ ...jumeauProvisoire, nom: "Paiements", mission: "Traite les paiements" }} jid="app-1" />);
  });
  expect(hote.querySelector('[data-testid="promotion-jumeau"]')).toBeNull();
  await act(async () => { racine.unmount(); });
});
