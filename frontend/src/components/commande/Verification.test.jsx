import { act } from "react";
import { createRoot } from "react-dom/client";
import Verification from "./Verification";

global.IS_REACT_ACT_ENVIRONMENT = true;

const catalogue = { connecteurs: [{ id: "github", nom: "GitHub" }] };
const commande = {
  jumeau: { nom: "Remboursements", application_id: "remboursements", proprietaire: "Paiements" },
  sources: [
    { id: "s1", nom: "Code", connecteur: "github", environnement: "production", statut: "prete" },
    { id: "s2", nom: "Jira", connecteur: "jira", environnement: "production", statut: "configuration_incomplete", erreur: { detail: "Projet manquant", action: "Compléter" } },
    { id: "s3", nom: "Confluence", connecteur: "confluence", environnement: "production", statut: "prete_a_tester" },
  ],
};

test("liste les sources non prêtes et permet de corriger celle qui bloque", async () => {
  const onCorriger = jest.fn();
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(<Verification commande={commande} catalogue={catalogue} onLancer={jest.fn()} lancement={false} onCorriger={onCorriger} />);
  });

  expect(hote.querySelector('[data-testid="verif-pretes"]').textContent).toContain("1");
  expect(hote.querySelector('[data-testid="verif-reportees"]').textContent).toContain("1");
  expect(hote.querySelector('[data-testid="verif-erreurs"]').textContent).toContain("1");
  expect(hote.querySelector('[data-testid="verif-liste-non-pretes"]').textContent).toContain("Projet manquant");

  await act(async () => { hote.querySelector('[data-testid="verif-corriger-s2"]').click(); });
  expect(onCorriger).toHaveBeenCalledWith("s2");

  await act(async () => { racine.unmount(); });
});

test("bloque le lancement quand aucune source ne permet une naissance", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  const sansNaissance = {
    ...commande,
    sources: [{ id: "s1", nom: "Jira", connecteur: "jira", environnement: "production", statut: "prete" }],
  };
  await act(async () => {
    racine.render(<Verification commande={sansNaissance} catalogue={catalogue} onLancer={jest.fn()} lancement={false} />);
  });

  expect(hote.querySelector('[data-testid="lancer-btn"]').disabled).toBe(true);
  expect(hote.textContent).toContain("GitHub");

  await act(async () => { racine.unmount(); });
});
