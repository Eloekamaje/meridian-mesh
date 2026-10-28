import { badgeOrigine } from "./origineFlore";

test("une réponse de démonstration se distingue d'une réponse calculée", () => {
  expect(badgeOrigine({ origine: "scenario" }).texte).toBe("scénario de démonstration");
  expect(badgeOrigine({ origine: "repli" }).texte).toBe("aucune réponse calculée");
});

test("une réponse calculée ne porte aucune étiquette d'origine", () => {
  expect(badgeOrigine({ origine: "modele" })).toBeNull();
  expect(badgeOrigine({})).toBeNull();
});
