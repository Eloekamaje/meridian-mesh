import { act } from "react";
import { createRoot } from "react-dom/client";
import PropositionsFlore from "./PropositionsFlore";

global.IS_REACT_ACT_ENVIRONMENT = true;

const prop = { claim: 7, jumeau: "conduit", nom: "Conduit", predicat: "AUTORISE", objet: "publier un article" };

test("valider une connaissance demande une confirmation explicite", async () => {
  const decide = jest.fn();
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  await act(async () => {
    racine.render(<PropositionsFlore propositions={[prop]} index={3} actif onDecider={decide} />);
  });

  const valider = hote.querySelector('[data-testid="approuver-3-7"]');
  expect(valider).not.toBeNull();
  await act(async () => { valider.click(); });
  expect(hote.querySelector('[data-testid="confirmation-3-7"]')).not.toBeNull();
  expect(decide).not.toHaveBeenCalled();

  const confirmer = hote.querySelector('[data-testid="confirmer-validation-3-7"]');
  await act(async () => { confirmer.click(); });
  expect(decide).toHaveBeenCalledWith(7, "ACCEPTED");

  await act(async () => { racine.unmount(); });
});
