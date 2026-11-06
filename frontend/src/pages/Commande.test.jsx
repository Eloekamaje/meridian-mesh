import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import Commande from "./Commande";

const mockNaviguer = jest.fn();
let mockParametre = { cid: "cmd-1" };

jest.mock("react-router-dom", () => ({
  useParams: () => mockParametre,
  useNavigate: () => mockNaviguer,
}), { virtual: true });
jest.mock("@/components/commande/InspecteurSource", () => () => null);
jest.mock("@/lib/mesh", () => ({ useMesh: () => ({ recharger: jest.fn() }) }));
jest.mock("@/lib/contexte", () => ({ useContexte: () => ({ setLot: jest.fn() }) }));
jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() },
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

const commande = {
  id: "cmd-1",
  etape: 1,
  jumeau: { application_id: "", nom: "Remboursements", proprietaire: "Équipe Paiements" },
  sources: [],
};

const catalogue = { connecteurs: [], contributions: {}, profils: [] };

function monter() {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine };
}

function saisir(input, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(input, valeur);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function rendreCommande(racine) {
  await act(async () => { racine.render(<Commande />); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockParametre = { cid: "cmd-1" };
  api.get.mockImplementation((url) => {
    if (url === "/commandes/cmd-1") return Promise.resolve({ data: { ...commande, jumeau: { ...commande.jumeau } } });
    if (url === "/connecteurs") return Promise.resolve({ data: catalogue });
    return Promise.resolve({ data: {} });
  });
  api.patch.mockResolvedValue({ data: { ok: true } });
});

test("n'ouvre aucun brouillon au simple clic sur Commander", async () => {
  mockParametre = { cid: "nouvelle" };
  const { hote, racine } = monter();
  await rendreCommande(racine);

  expect(api.post).not.toHaveBeenCalled();
  await act(async () => { hote.querySelector('[data-testid="commande-quitter-btn"]').click(); });
  await act(async () => { await Promise.resolve(); });

  expect(api.post).not.toHaveBeenCalled();
  expect(mockNaviguer).toHaveBeenCalledWith("/jumeaux");

  await act(async () => { racine.unmount(); });
});

test("n'ouvre le brouillon qu'à la première identité saisie", async () => {
  mockParametre = { cid: "nouvelle" };
  api.post.mockResolvedValue({ data: { id: "cmd-new" } });
  const { hote, racine } = monter();
  await rendreCommande(racine);

  await act(async () => { saisir(hote.querySelector('[data-testid="identite-nom"]'), "Remboursements"); });
  await act(async () => { hote.querySelector('[data-testid="commande-quitter-btn"]').click(); });
  await act(async () => { await Promise.resolve(); });

  expect(api.post).toHaveBeenCalledWith("/commandes", {});
  expect(api.patch).toHaveBeenCalledWith("/commandes/cmd-new", expect.objectContaining({
    jumeau: expect.objectContaining({ nom: "Remboursements" }),
  }));

  await act(async () => { racine.unmount(); });
});

test("enregistre la dernière saisie avant de quitter", async () => {
  const { hote, racine } = monter();
  await rendreCommande(racine);

  await act(async () => {
    saisir(hote.querySelector('[data-testid="identite-application_id"]'), "remboursements");
  });
  await act(async () => { await Promise.resolve(); });
  await act(async () => { hote.querySelector('[data-testid="commande-quitter-btn"]').click(); });
  await act(async () => { await Promise.resolve(); });

  expect(api.patch).toHaveBeenCalledWith("/commandes/cmd-1", expect.objectContaining({
    jumeau: expect.objectContaining({ application_id: "remboursements" }),
  }));
  expect(mockNaviguer).toHaveBeenCalledWith("/jumeaux");

  await act(async () => { racine.unmount(); });
});

test("valide l'application_id en direct et bloque la suite tant qu'il est invalide", async () => {
  const { hote, racine } = monter();
  await rendreCommande(racine);

  const appId = hote.querySelector('[data-testid="identite-application_id"]');
  expect(hote.querySelectorAll('[data-testid="identite-application_id"]').length).toBe(1);
  const suivant = hote.querySelector('[data-testid="etape-suivante-btn"]');
  expect(suivant.disabled).toBe(true);
  expect(hote.querySelector('[data-testid="commande-titre"]').textContent).toContain("Remboursements");
  expect(hote.querySelector('[data-testid="commande-entete"]').textContent).toContain("App ID à définir");

  await act(async () => { saisir(appId, "Remboursements"); });
  expect(hote.querySelector('[data-testid="identite-application_id-aide"]').textContent).toContain("Identifiant invalide");
  expect(suivant.disabled).toBe(true);

  await act(async () => { saisir(appId, "remboursements"); });
  expect(hote.querySelector('[data-testid="identite-application_id-aide"]').textContent).toContain("Identifiant stable");
  expect(suivant.disabled).toBe(false);
  expect(hote.querySelector('[data-testid="commande-entete"]').textContent).toContain("App ID remboursements");

  await act(async () => { suivant.click(); });
  expect(hote.querySelector('[data-testid="etape-atelier"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

function choisir(select, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value").set;
  setter.call(select, valeur);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

function saisirZone(textarea, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  setter.call(textarea, valeur);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

test("propose les cinq types de Twin", async () => {
  const { hote, racine } = monter();
  await rendreCommande(racine);

  const options = [...hote.querySelectorAll('[data-testid="identite-type"] option')].map((o) => o.value);
  expect(options).toEqual(["APPLICATION", "TEAM", "RESOURCE", "SUPPLIER", "ECOSYSTEM"]);

  await act(async () => { racine.unmount(); });
});

test("un Twin TEAM se crée sans App ID, avec nom, propriétaire et périmètre", async () => {
  const { hote, racine } = monter();
  await rendreCommande(racine);

  await act(async () => { choisir(hote.querySelector('[data-testid="identite-type"]'), "TEAM"); });
  expect(hote.querySelector('[data-testid="identite-application_id"]')).toBeNull();
  expect(hote.querySelector('[data-testid="identite-team_id"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="identite-perimetre"]')).not.toBeNull();

  const suivant = hote.querySelector('[data-testid="etape-suivante-btn"]');
  expect(suivant.disabled).toBe(true);

  await act(async () => { saisir(hote.querySelector('[data-testid="identite-perimetre"]'), "Équipe Paiements"); });
  expect(suivant.disabled).toBe(false);

  const entete = hote.querySelector('[data-testid="commande-entete"]');
  expect(entete.textContent).toContain("TEAM");
  expect(entete.textContent).not.toContain("Twin ID");
  expect(entete.textContent).not.toContain("App ID");
  expect(hote.querySelector('[data-testid="identite-twin_id"]').value).toMatch(/^team-/);
  expect(hote.querySelector('[data-testid="identite-avance"]').open).toBe(false);

  await act(async () => { racine.unmount(); });
});

test.each(["RESOURCE", "SUPPLIER"])("un Twin %s peut reposer sur un twin_id généré", async (type) => {
  const { hote, racine } = monter();
  await rendreCommande(racine);

  await act(async () => { choisir(hote.querySelector('[data-testid="identite-type"]'), type); });
  const cle = type === "RESOURCE" ? "resource_id" : "supplier_id";
  expect(hote.querySelector('[data-testid="identite-application_id"]')).toBeNull();
  expect(hote.querySelector(`[data-testid="identite-${cle}"]`)).not.toBeNull();
  expect(hote.querySelector('[data-testid="identite-twin_id"]').value).toMatch(new RegExp(`^${type === "RESOURCE" ? "res" : "sup"}-`));
  expect(hote.querySelector('[data-testid="etape-suivante-btn"]').disabled).toBe(false);
  expect(hote.querySelector('[data-testid="commande-entete"]').textContent).not.toContain("App ID");

  await act(async () => { racine.unmount(); });
});

test("une application candidate est valide sans App ID et l'en-tête reste applicatif", async () => {
  const { hote, racine } = monter();
  await rendreCommande(racine);

  const suivant = hote.querySelector('[data-testid="etape-suivante-btn"]');
  expect(suivant.disabled).toBe(true);

  await act(async () => { hote.querySelector('[data-testid="identite-candidat"]').click(); });
  expect(suivant.disabled).toBe(false);
  expect(hote.querySelector('[data-testid="commande-entete"]').textContent).toContain("APPLICATION");
  expect(hote.querySelector('[data-testid="commande-entete"]').textContent).toContain("App ID candidat");

  await act(async () => { hote.querySelector('[data-testid="identite-candidat"]').click(); });
  expect(suivant.disabled).toBe(true);

  await act(async () => { racine.unmount(); });
});

test("accepte un objet d'identifiants externes valide", async () => {
  const { hote, racine } = monter();
  await rendreCommande(racine);

  await act(async () => { choisir(hote.querySelector('[data-testid="identite-type"]'), "RESOURCE"); });
  await act(async () => {
    saisirZone(hote.querySelector('[data-testid="identite-identifiants"]'), '{"ci_servicenow":"CI-123","contrat":"CTR-42"}');
  });
  expect(hote.querySelector('[data-testid="identite-identifiants-aide"]').textContent).not.toContain("invalide");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="identite-resource_id"]'), "CI-123");
  });
  await act(async () => { hote.querySelector('[data-testid="etape-suivante-btn"]').click(); });
  expect(hote.querySelector('[data-testid="etape-atelier"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});
