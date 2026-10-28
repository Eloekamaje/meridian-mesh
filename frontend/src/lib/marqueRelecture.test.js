import { badgeRelecture } from "./marqueRelecture";

test("« relu » n'est affiché que quand la relecture a réellement eu lieu", () => {
  expect(badgeRelecture({ relecture_etat: "relue" }).texte).toBe("relu");
  expect(badgeRelecture({ relecture_etat: "indisponible" }).texte).toBe("non relu");
  expect(badgeRelecture({ relecture_etat: "verdict_illisible" }).texte).toBe("non relu");
});

test("une correction n'est pas présentée comme une relecture", () => {
  expect(badgeRelecture({ relecture_etat: "corrigee_non_relue" }).texte).toBe("corrigé — non relu");
  expect(badgeRelecture({ relecture_etat: "objection_sans_effet" }).texte).toBe("relecture non appliquée");
});

test("une réponse d'un serveur antérieur n'affiche aucune étiquette", () => {
  expect(badgeRelecture({ relu: true, corrige: false })).toBeNull();
  expect(badgeRelecture(null)).toBeNull();
});
