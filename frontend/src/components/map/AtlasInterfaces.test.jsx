import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import AtlasInterfaces from "./AtlasInterfaces";

jest.mock("@/lib/api", () => ({ __esModule: true, default: { get: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

const jumeaux = {
  "app-crm": { id: "app-crm", nom: "CRM" },
  "app-facturation": { id: "app-facturation", nom: "Facturation" },
  "app-reporting": { id: "app-reporting", nom: "Reporting" },
};

const donnees = {
  applications: ["app-crm", "app-facturation", "app-reporting"],
  operations: [
    { id: "op-1", application_id: "app-crm", method: "GET", path: "/clients", protocol: "http", environment: "production", name: "clients" },
    { id: "op-2", application_id: "app-facturation", method: "POST", path: "/factures", protocol: "http", environment: "production", name: "factures" },
  ],
  edges: [
    { source: "app-facturation", target: "app-crm", operation_id: "op-2", operation: "POST /factures", mode: "declared", confidence: 0.9, evidence: [] },
    { source: "app-reporting", target: "app-crm", operation_id: "op-1", operation: "GET /clients", mode: "observed", confidence: 0.8, evidence: [] },
  ],
  impacts: [
    {
      application: "app-facturation", operation: "POST /factures", change_type: "operation_removed", severity: "warning",
      raison: "La facturation consomme POST /factures.", run_id: "run-1", at: "2026-10-30T06:00:00Z",
    },
    {
      application: "app-reporting", operation: "GET /clients", change_type: "operation_changed", severity: "breaking",
      raison: "Le reporting consomme GET /clients.", run_id: "run-2", at: "2026-10-30T07:00:00Z",
    },
  ],
  runs: [{ id: "run-2", application_id: "app-reporting", status: "ok", started_at: "2026-10-30T07:00:00Z", stats: {} }],
};

function monter() {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine };
}

function rendre(racine, props = {}) {
  return act(async () => {
    racine.render(
      <AtlasInterfaces
        version={1}
        jumeauPar={(id) => jumeaux[id] || null}
        setSelection={jest.fn()}
        centrerJumeau={jest.fn()}
        majUrl={jest.fn()}
        onFermer={jest.fn()}
        {...props}
      />
    );
  });
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("AtlasInterfaces affiche les comptes, les impacts breaking d'abord et les arêtes", async () => {
  let resoudre;
  api.get.mockReturnValue(new Promise((resolve) => { resoudre = resolve; }));
  const setSelection = jest.fn();
  const centrerJumeau = jest.fn();
  const majUrl = jest.fn();
  const { hote, racine } = monter();

  await rendre(racine, { setSelection, centrerJumeau, majUrl });

  expect(api.get).toHaveBeenCalledWith("/mesh/interfaces");
  expect(hote.querySelector('[data-testid="atlas-interfaces"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="atlas-interfaces-chargement"]')).not.toBeNull();

  await act(async () => { resoudre({ data: donnees }); });

  expect(hote.querySelector('[data-testid="atlas-interfaces-nb-operations"]').textContent).toContain("2 opérations");
  expect(hote.querySelector('[data-testid="atlas-interfaces-nb-aretes-declarees"]').textContent).toContain("1 arête déclarée");
  expect(hote.querySelector('[data-testid="atlas-interfaces-nb-aretes-observees"]').textContent).toContain("1 arête observée");
  expect(hote.querySelector('[data-testid="atlas-interfaces-nb-impacts"]').textContent).toContain("2 impacts");

  const impacts = [...hote.querySelectorAll('[data-testid="atlas-interface-impact"]')];
  expect(impacts).toHaveLength(2);
  expect(impacts[0].textContent).toContain("Reporting");
  expect(impacts[0].textContent).toContain("rupture");
  expect(impacts[0].textContent).toContain("Le reporting consomme GET /clients.");
  expect(impacts[1].textContent).toContain("Facturation");
  expect(impacts[1].textContent).toContain("avertissement");

  const aretes = [...hote.querySelectorAll('[data-testid="atlas-interface-edge"]')];
  expect(aretes).toHaveLength(2);
  expect(aretes[0].textContent).toContain("Facturation");
  expect(aretes[0].textContent).toContain("CRM");
  expect(aretes[0].textContent).toContain("POST /factures");
  expect(aretes[0].textContent).toContain("déclaré");

  await act(async () => {
    hote.querySelector('[data-testid="atlas-interface-edge-voir"]').click();
  });
  expect(setSelection).toHaveBeenCalledWith(["app-facturation", "app-crm"]);
  expect(centrerJumeau).toHaveBeenCalledWith(jumeaux["app-crm"]);
  expect(majUrl).not.toHaveBeenCalled();

  await act(async () => { racine.unmount(); });
});

test("AtlasInterfaces utilise les données du parent et bascule la couche sans refetch", async () => {
  const onBasculerCouche = jest.fn();
  const onRecharger = jest.fn();
  const { hote, racine } = monter();

  await rendre(racine, { donnees, chargement: false, erreur: null, onRecharger, coucheActive: false, onBasculerCouche });

  expect(api.get).not.toHaveBeenCalled();
  const interrupteur = hote.querySelector('[data-testid="atlas-interfaces-couche"]');
  expect(interrupteur).not.toBeNull();
  expect(interrupteur.getAttribute("aria-checked")).toBe("false");
  expect(interrupteur.textContent).toContain("Afficher sur la carte");
  expect(hote.querySelector('[data-testid="atlas-interfaces-nb-impacts"]').textContent).toContain("2 impacts");

  await act(async () => { interrupteur.click(); });
  expect(onBasculerCouche).toHaveBeenCalledTimes(1);
  expect(onRecharger).not.toHaveBeenCalled();

  await act(async () => { racine.unmount(); });
});

test("AtlasInterfaces reflète la couche active fournie par le parent", async () => {
  const { hote, racine } = monter();

  await rendre(racine, {
    donnees,
    chargement: false,
    erreur: null,
    onRecharger: jest.fn(),
    coucheActive: true,
    onBasculerCouche: jest.fn(),
  });

  expect(hote.querySelector('[data-testid="atlas-interfaces-couche"]').getAttribute("aria-checked")).toBe("true");

  await act(async () => { racine.unmount(); });
});

test("AtlasInterfaces affiche l'état vide", async () => {
  api.get.mockResolvedValue({ data: { applications: [], operations: [], edges: [], impacts: [], runs: [] } });
  const { hote, racine } = monter();

  await rendre(racine);

  expect(hote.querySelector('[data-testid="atlas-interfaces-vide"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("AtlasInterfaces affiche l'erreur puis recharge au clic sur Réessayer", async () => {
  api.get
    .mockRejectedValueOnce({ response: { data: { detail: "Couche cognitive indisponible" } } })
    .mockResolvedValueOnce({ data: donnees });
  const { hote, racine } = monter();

  await rendre(racine);

  expect(hote.querySelector('[data-testid="atlas-interfaces-erreur"]').textContent).toContain("Couche cognitive indisponible");

  await act(async () => {
    hote.querySelector('[data-testid="atlas-interfaces-reessayer"]').click();
  });

  expect(api.get).toHaveBeenCalledTimes(2);
  expect(hote.querySelector('[data-testid="atlas-interfaces-nb-impacts"]').textContent).toContain("2 impacts");

  await act(async () => { racine.unmount(); });
});
