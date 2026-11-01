import { act } from "react";
import { createRoot } from "react-dom/client";
import CatalogueTiroir from "./CatalogueTiroir";

global.IS_REACT_ACT_ENVIRONMENT = true;

const catalogue = {
  connecteurs: [
    { id: "github", nom: "GitHub", categorie: "Code source", capacites: "Dépôts", branche: true, champs: [] },
    { id: "postgresql", nom: "PostgreSQL", categorie: "Bases de données", capacites: "Schémas", branche: false, champs: [] },
  ],
  profils: [],
};

test("un connecteur non branché ne peut pas être ajouté à la commande", async () => {
  const onAjoute = jest.fn();
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(<CatalogueTiroir catalogue={catalogue} sources={[]} onAjoute={onAjoute} onFermer={jest.fn()} />);
  });

  const nonBranche = hote.querySelector('[data-testid="connecteur-postgresql"]');
  expect(nonBranche.disabled).toBe(true);
  expect(nonBranche.textContent).toContain("Non branché");
  await act(async () => { nonBranche.click(); });
  expect(hote.querySelector('[data-testid="catalogue-modes"]')).toBeNull();
  expect(onAjoute).not.toHaveBeenCalled();

  await act(async () => { hote.querySelector('[data-testid="connecteur-github"]').click(); });
  expect(hote.querySelector('[data-testid="catalogue-modes"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});
