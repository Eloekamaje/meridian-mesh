import { estEnAttention, estEnNaissance, statutJumeau } from "./jumeaux";

test("un twin en naissance n'est ni à admettre ni en attention", () => {
  const twin = { statut: "observation", naissance_etat: "en_cours", couverture: 10 };
  expect(estEnNaissance(twin)).toBe(true);
  expect(estEnAttention(twin)).toBe(false);
  expect(statutJumeau(twin)).toEqual(["Naissance en cours", "#F2B84B"]);
});

test("un twin né reste en observation à admettre", () => {
  const twin = { statut: "observation", naissance_etat: "ne", couverture: 10 };
  expect(estEnAttention(twin)).toBe(true);
  expect(statutJumeau(twin)).toEqual(["Observation", "#60A5FA"]);
});

test("un échec de naissance est visible", () => {
  expect(statutJumeau({ statut: "observation", naissance_etat: "echec" })).toEqual(["Naissance échouée", "#F87171"]);
});
