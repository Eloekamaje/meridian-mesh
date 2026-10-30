// Tirage manuel des sources OTLP : bouton, appel sans corps, rechargement et nouvel état affiché.
import { act } from "react";
import { createRoot } from "react-dom/client";
import { toast } from "sonner";
import api from "@/lib/api";
import InterfacesJumeau from "./InterfacesJumeau";

jest.mock("@/lib/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  jest.clearAllMocks();
});

const avant = {
  jumeau_id: "app-1",
  application_id: "app-1",
  tenant: "local",
  interfaces: {
    contracts: [{ id: "ctr-1", format: "openapi", version: "1.2", environment: "production", locator: "openapi.yaml" }],
    operations: [{ id: "op-1", method: "GET", path: "/sante", name: "sante", environment: "production" }],
    bindings: [],
    assertions: [
      { subject: "app-1", predicate: "EXPOSE", object: "GET /sante", mode: "declared", source: "openapi", environment: "production", confidence: 0.95 },
    ],
  },
  runs: [{
    id: "run-1",
    status: "ok",
    source: "api",
    started_at: "2026-10-30T06:00:00Z",
    stats: { contracts: 1, operations: 1, assertions: 1 },
    changes: [],
    impacts: [],
  }],
};

const apres = {
  ...avant,
  runs: [{
    id: "run-2",
    status: "ok",
    source: "otlp-collecteur",
    started_at: "2026-10-30T07:00:00Z",
    stats: { contracts: 1, operations: 2, assertions: 2 },
    changes: [{ type: "binding_added", subject: "app-1", before: null, after: "https://paiements.test", severity: "info" }],
    impacts: [],
  }, avant.runs[0]],
};

function monter() {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine };
}

function cliquer(element) {
  element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
}

test("tire les observations, recharge les interfaces et affiche le nouveau run", async () => {
  api.get.mockResolvedValueOnce({ data: avant }).mockResolvedValueOnce({ data: apres });
  api.post.mockResolvedValue({ data: { runs: [{ id: "run-2", status: "ok", source: "otlp-collecteur" }] } });
  const { hote, racine } = monter();
  await act(async () => { racine.render(<InterfacesJumeau jid="app-1" />); });

  const bouton = hote.querySelector('[data-testid="interfaces-tirer"]');
  expect(bouton).not.toBeNull();
  expect(bouton.textContent).toContain("Tirer les observations");
  expect(bouton.disabled).toBe(false);

  await act(async () => { cliquer(bouton); });

  expect(api.post).toHaveBeenCalledWith("/jumeaux/app-1/interfaces/observer/pull-source");
  expect(api.post.mock.calls[0]).toHaveLength(1);
  expect(api.get).toHaveBeenCalledTimes(2);
  expect(api.get).toHaveBeenLastCalledWith("/jumeaux/app-1/interfaces");

  const succes = toast.success.mock.calls[0][0];
  expect(succes).toContain("Observations tirées");
  expect(succes).toContain("1 run");
  expect(succes).toContain("otlp-collecteur");

  const runAffiche = hote.querySelector('[data-testid="interfaces-run"]').textContent;
  expect(runAffiche).toContain("otlp-collecteur");
  expect(runAffiche).toContain("2 opérations");
  expect(hote.querySelector('[data-testid="interfaces-tirage-etat"]').textContent).toContain("Dernier tirage : 1 run");
  expect(bouton.disabled).toBe(false);

  await act(async () => { racine.unmount(); });
});

test("désactive le bouton pendant le tirage puis affiche l'absence de source OTLP", async () => {
  api.get.mockResolvedValue({ data: avant });
  let rejeter;
  api.post.mockImplementation(() => new Promise((_, reject) => { rejeter = reject; }));
  const { hote, racine } = monter();
  await act(async () => { racine.render(<InterfacesJumeau jid="app-1" />); });

  const bouton = hote.querySelector('[data-testid="interfaces-tirer"]');
  act(() => { cliquer(bouton); });

  expect(bouton.disabled).toBe(true);
  expect(hote.querySelector('[data-testid="interfaces-tirage-etat"]').textContent).toContain("Tirage des observations OTLP en cours");

  await act(async () => {
    rejeter({ response: { status: 503, data: { detail: "Aucune source OTLP configurée" } } });
  });

  expect(toast.error).toHaveBeenCalledWith("Aucune source OTLP configurée");
  expect(bouton.disabled).toBe(false);
  expect(hote.querySelector('[data-testid="interfaces-tirage-etat"]').textContent).toContain("Aucune source OTLP configurée");

  await act(async () => { racine.unmount(); });
});

test("conserve l'état vide existant tout en proposant le tirage", async () => {
  api.get.mockResolvedValue({
    data: { interfaces: { contracts: [], operations: [], bindings: [], assertions: [] }, runs: [] },
  });
  const { hote, racine } = monter();
  await act(async () => { racine.render(<InterfacesJumeau jid="app-1" />); });

  expect(hote.querySelector('[data-testid="interfaces-vide"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="interfaces-tirer"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="interfaces-tirage-etat"]').textContent).toContain("Aucun run de tirage OTLP");

  await act(async () => { racine.unmount(); });
});
