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

const sourcesPretes = [
  { id: "s1", nom: "Code", connecteur: "github", environnement: "production", statut: "prete" },
];

function commandeAvec(jumeau, sources = sourcesPretes) {
  return { jumeau, sources };
}

test("valide un Twin TEAM sans App ID et ne l'affiche jamais", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  const team = commandeAvec({
    type: "TEAM",
    twin_id: "team-paiements",
    nom: "Équipe Paiements",
    proprietaire: "L. Marchand",
    perimetre: "Paiements",
  });
  await act(async () => {
    racine.render(<Verification commande={team} catalogue={catalogue} onLancer={jest.fn()} lancement={false} />);
  });

  expect(hote.querySelector('[data-testid="verif-type"]').textContent).toBe("TEAM");
  expect(hote.querySelector('[data-testid="verif-twin-id"]')).toBeNull();
  expect(hote.querySelector('[data-testid="verif-app-id"]')).toBeNull();
  expect(hote.textContent).not.toContain("App ID");
  expect(hote.querySelector('[data-testid="lancer-btn"]').disabled).toBe(false);

  await act(async () => { racine.unmount(); });
});

test("refuse un Twin TEAM sans périmètre", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  const team = commandeAvec({
    type: "TEAM",
    twin_id: "team-paiements",
    nom: "Équipe Paiements",
    proprietaire: "L. Marchand",
  });
  await act(async () => {
    racine.render(<Verification commande={team} catalogue={catalogue} onLancer={jest.fn()} lancement={false} />);
  });

  expect(hote.querySelector('[data-testid="lancer-btn"]').disabled).toBe(true);
  expect(hote.textContent).toContain("périmètre");

  await act(async () => { racine.unmount(); });
});

test("valide une application candidate sans App ID", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  const candidate = commandeAvec({
    type: "APPLICATION",
    twin_id: "app-candidate",
    candidat: true,
    nom: "Application candidate",
    proprietaire: "Paiements",
  });
  await act(async () => {
    racine.render(<Verification commande={candidate} catalogue={catalogue} onLancer={jest.fn()} lancement={false} />);
  });

  expect(hote.querySelector('[data-testid="verif-type"]').textContent).toBe("APPLICATION");
  expect(hote.querySelector('[data-testid="verif-app-id"]').textContent).toContain("candidat");
  expect(hote.querySelector('[data-testid="lancer-btn"]').disabled).toBe(false);
  expect(hote.textContent).not.toContain("App ID à définir");

  await act(async () => { racine.unmount(); });
});

test.each(["RESOURCE", "SUPPLIER"])("valide un Twin %s avec twin_id généré", async (type) => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  const jumeau = {
    type,
    twin_id: `${type === "RESOURCE" ? "res" : "sup"}-abc123`,
    nom: `Twin ${type}`,
    proprietaire: "Paiements",
  };
  await act(async () => {
    racine.render(<Verification commande={commandeAvec(jumeau)} catalogue={catalogue} onLancer={jest.fn()} lancement={false} />);
  });

  expect(hote.querySelector('[data-testid="verif-type"]').textContent).toBe(type);
  expect(hote.querySelector('[data-testid="verif-app-id"]')).toBeNull();
  expect(hote.querySelector('[data-testid="lancer-btn"]').disabled).toBe(false);

  await act(async () => { racine.unmount(); });
});

test("refuse un Twin RESOURCE sans identifiant externe ni twin_id", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  const jumeau = { type: "RESOURCE", nom: "Ressource tierce", proprietaire: "Paiements" };
  await act(async () => {
    racine.render(<Verification commande={commandeAvec(jumeau)} catalogue={catalogue} onLancer={jest.fn()} lancement={false} />);
  });

  expect(hote.querySelector('[data-testid="lancer-btn"]').disabled).toBe(true);
  expect(hote.textContent).toContain("Resource ID");

  await act(async () => { racine.unmount(); });
});

test("valide un Twin ECOSYSTEM sans App ID avec son périmètre", async () => {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  const ecosysteme = commandeAvec({
    type: "ECOSYSTEM",
    twin_id: "eco-paiements",
    nom: "Écosystème Paiements",
    proprietaire: "L. Marchand",
    perimetre: "Paiements et fournisseurs",
  });
  await act(async () => {
    racine.render(<Verification commande={ecosysteme} catalogue={catalogue} onLancer={jest.fn()} lancement={false} />);
  });

  expect(hote.querySelector('[data-testid="verif-type"]').textContent).toBe("ECOSYSTEM");
  expect(hote.querySelector('[data-testid="verif-app-id"]')).toBeNull();
  expect(hote.textContent).not.toContain("App ID");
  expect(hote.querySelector('[data-testid="lancer-btn"]').disabled).toBe(false);

  await act(async () => { racine.unmount(); });
});
