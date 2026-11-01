import { act } from "react";
import { createRoot } from "react-dom/client";
import { toast } from "sonner";
import api from "@/lib/api";
import ImportIdentite from "./ImportIdentite";

jest.mock("@/lib/api", () => ({ __esModule: true, default: { post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

global.IS_REACT_ACT_ENVIRONMENT = true;

const apercu = {
  mode: "cmdb",
  detectees: 1,
  identite: { application_id: "remboursements", nom: "Remboursements", proprietaire: "Équipe Paiements" },
  nouvelles: [{ connecteur: "github", nom: "remboursements", environnement: "production", config: {} }],
  ignorees: [],
};

function monter() {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine };
}

function saisir(textarea, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  setter.call(textarea, valeur);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("analyse un export CMDB et remonte l'aperçu à la commande", async () => {
  api.post.mockResolvedValue({ data: apercu });
  const onImporte = jest.fn();
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(<ImportIdentite commandeId="cmd-1" mode="cmdb" onImporte={onImporte} />);
  });

  await act(async () => {
    saisir(hote.querySelector('[data-testid="import-contenu"]'),
      "application_id,nom,proprietaire\nremboursements,Remboursements,Équipe Paiements\n");
  });
  await act(async () => { hote.querySelector('[data-testid="import-analyser-btn"]').click(); });

  expect(api.post).toHaveBeenCalledWith("/commandes/cmd-1/import/apercu", {
    mode: "cmdb",
    contenu: "application_id,nom,proprietaire\nremboursements,Remboursements,Équipe Paiements\n",
  });
  const rendu = hote.querySelector('[data-testid="import-apercu"]');
  expect(rendu).not.toBeNull();
  expect(rendu.textContent).toContain("Remboursements");
  expect(rendu.textContent).toContain("1 nouvelle(s)");
  expect(hote.querySelector('[data-testid="import-nouvelles"]').textContent).toContain("github");

  await act(async () => { hote.querySelector('[data-testid="import-confirmer-btn"]').click(); });
  expect(onImporte).toHaveBeenCalledWith(apercu);

  await act(async () => { racine.unmount(); });
});

test("signale les sources déjà présentes et n'importe que les nouvelles", async () => {
  api.post.mockResolvedValue({
    data: {
      ...apercu,
      nouvelles: [],
      ignorees: [{ connecteur: "github", nom: "remboursements", environnement: "production" }],
    },
  });
  const onImporte = jest.fn();
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(<ImportIdentite commandeId="cmd-1" mode="manifeste" onImporte={onImporte} />);
  });

  await act(async () => {
    saisir(hote.querySelector('[data-testid="import-contenu"]'), '{"jumeau":{}}');
  });
  await act(async () => { hote.querySelector('[data-testid="import-analyser-btn"]').click(); });

  expect(hote.querySelector('[data-testid="import-ignorees"]').textContent).toContain("1 source(s) déjà");
  expect(hote.querySelector('[data-testid="import-nouvelles"]')).toBeNull();
  expect(hote.textContent).toContain("seule l'identité sera mise à jour");

  await act(async () => { hote.querySelector('[data-testid="import-confirmer-btn"]').click(); });
  expect(onImporte).toHaveBeenCalledWith(expect.objectContaining({ nouvelles: [] }));

  await act(async () => { racine.unmount(); });
});

test("refuse un contenu vide et affiche l'erreur du serveur", async () => {
  const onImporte = jest.fn();
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(<ImportIdentite commandeId="cmd-1" mode="manifeste" onImporte={onImporte} />);
  });

  await act(async () => { hote.querySelector('[data-testid="import-analyser-btn"]').click(); });
  expect(toast.error).toHaveBeenCalledWith("Ajoutez un contenu JSON ou CSV.");
  expect(api.post).not.toHaveBeenCalled();

  api.post.mockRejectedValue({ response: { data: { detail: "mode d'import inconnu : manifeste" } } });
  await act(async () => {
    saisir(hote.querySelector('[data-testid="import-contenu"]'), "{");
  });
  await act(async () => { hote.querySelector('[data-testid="import-analyser-btn"]').click(); });
  expect(toast.error).toHaveBeenCalledWith("mode d'import inconnu : manifeste");
  expect(hote.querySelector('[data-testid="import-apercu"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});
