import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import Jumeaux from "./Jumeaux";

const mockNaviguer = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNaviguer,
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), delete: jest.fn() },
}));
jest.mock("@/lib/perimetre", () => ({ usePerimetre: () => ({ version: 0 }) }));
jest.mock("@/lib/contexte", () => ({
  useContexte: () => ({
    selection: [], setSelection: jest.fn(), ajouterJumeau: jest.fn(),
    retirerJumeau: jest.fn(), demanderAFlore: jest.fn(),
  }),
}));
jest.mock("@/components/ComposerFlore", () => () => null);
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn(), info: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  jest.clearAllMocks();
  window.confirm = jest.fn(() => true);
  api.get.mockImplementation((url) => {
    if (url === "/jumeaux") return Promise.resolve({ data: [] });
    if (url === "/commandes") return Promise.resolve({
      data: [{ id: "cmd-1", etape: 1, jumeau: { nom: "Brouillon test" }, sources: [] }],
    });
    return Promise.resolve({ data: [] });
  });
  api.delete.mockResolvedValue({ data: { ok: true } });
});

test("affiche une naissance en cours au lieu de proposer l'admission", async () => {
  api.get.mockImplementation((url) => {
    if (url === "/jumeaux") return Promise.resolve({ data: [{
      id: "j1", nom: "Nouveau jumeau", statut: "observation", naissance_etat: "en_cours",
      couverture: 20, sources_detail: [], fraicheur_etat: "sync", domaine: "Non classé",
      proprietaire: "Équipe", autonomie: "aucune",
    }] });
    if (url === "/commandes") return Promise.resolve({ data: [] });
    return Promise.resolve({ data: [] });
  });
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => { racine.render(<Jumeaux />); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

  expect(hote.textContent).toContain("Naissance en cours");
  expect(hote.querySelector('[data-testid="naissance-en-cours-j1"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="revoir-admission-j1"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});


test("supprime un brouillon de commande depuis le registre", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => { racine.render(<Jumeaux />); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

  expect(hote.querySelector('[data-testid="brouillon-cmd-1"]')).not.toBeNull();
  await act(async () => { hote.querySelector('[data-testid="supprimer-cmd-1"]').click(); });
  await act(async () => { await Promise.resolve(); });

  expect(window.confirm).toHaveBeenCalled();
  expect(api.delete).toHaveBeenCalledWith("/commandes/cmd-1");
  expect(hote.querySelector('[data-testid="brouillon-cmd-1"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});
