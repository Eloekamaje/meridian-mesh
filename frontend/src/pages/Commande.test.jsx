import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import Commande from "./Commande";

const mockNaviguer = jest.fn();

jest.mock("react-router-dom", () => ({
  useParams: () => ({ cid: "cmd-1" }),
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
  api.get.mockImplementation((url) => {
    if (url === "/commandes/cmd-1") return Promise.resolve({ data: { ...commande, jumeau: { ...commande.jumeau } } });
    if (url === "/connecteurs") return Promise.resolve({ data: catalogue });
    return Promise.resolve({ data: {} });
  });
  api.patch.mockResolvedValue({ data: { ok: true } });
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
