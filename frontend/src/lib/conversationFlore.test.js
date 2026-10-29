import { prefixeTravail, urlMessage, navigation, navVersions, navBranches, regrouper, erreurAction, resultatsRecherche, remplacerMessage, floreAProduit, estConversation } from "./conversationFlore";

test("les URL se construisent par préfixe /cases/{cid}", () => {
  expect(prefixeTravail("abc")).toBe("/cases/abc");
  expect(urlMessage(prefixeTravail("abc"), 3, "regenerer/flux")).toBe("/cases/abc/messages/3/regenerer/flux");
  expect(urlMessage(prefixeTravail("a b"), 0, "retour")).toBe("/cases/a%20b/messages/0/retour");
});

test("navigation de versions : rien s'il n'y en a qu'une, bornes sinon", () => {
  expect(navVersions({ versions: [{}], version: 0 })).toBeNull();
  expect(navVersions({})).toBeNull();
  expect(navVersions({ versions: [{}, {}, {}], version: 0 })).toEqual({ k: 1, total: 3, precedent: null, suivant: 1 });
  expect(navVersions({ versions: [{}, {}, {}], version: 2 })).toEqual({ k: 3, total: 3, precedent: 1, suivant: null });
  expect(navBranches({ branches: [{}, {}], branche: 1 })).toEqual({ k: 2, total: 2, precedent: 0, suivant: null });
  expect(navigation([{}, {}], 9).k).toBe(2); // index hors bornes ramené dans la liste
});

test("regrouper : index serveur des messages, marqueurs exclus du compte", () => {
  const e = regrouper([
    { role: "utilisateur", texte: "q1" }, { role: "flore", texte: "r1", versions: [{}, {}], version: 1 },
    { marqueur: true, texte: "ctx" },
    { role: "utilisateur", texte: "q2" },
  ]);
  expect(e).toHaveLength(3);
  expect([e[0].nq, e[0].nr, e[0].data.reponse]).toEqual([0, 1, "r1"]);
  expect(e[1].marqueur).toBe(true);
  expect([e[2].nq, e[2].data]).toEqual([2, undefined]);
});

test("remplacerMessage ne touche pas l'original", () => {
  const avant = [{ a: 1 }, { a: 2 }];
  expect(remplacerMessage(avant, 1, { a: 3 })).toEqual([{ a: 1 }, { a: 3 }]);
  expect(avant[1]).toEqual({ a: 2 });
});

test("route absente côté serveur : message clair", () => {
  expect(erreurAction({ response: { status: 404 } }, "Régénération")).toMatch(/pas encore/);
  expect(erreurAction(new Error("flux indisponible (404)"), "Régénération")).toMatch(/pas encore/);
  expect(erreurAction(new Error("boom"), "Retour")).toBe("Retour impossible.");
});

test("recherche : liste du serveur si elle filtre, sinon repli sur le titre", () => {
  const tous = [{ id: 1, titre: "Paiement" }, { id: 2, titre: "Stockage" }];
  expect(resultatsRecherche("lot", tous, [tous[1]])).toEqual([tous[1]]);
  expect(resultatsRecherche("pai", tous, tous)).toEqual([tous[0]]); // ancien serveur : tout est rendu
  expect(resultatsRecherche("", tous, null)).toBe(tous);
});

test("la proposition de conserver vient d'un plan, d'une option, d'une décision ou d'un livrable", () => {
  expect(floreAProduit(null, [{ role: "flore", texte: "bonjour" }])).toBe(false);
  expect(floreAProduit({ plan: [] , options: [] }, [])).toBe(false);
  expect(floreAProduit({ options: [{ id: 1 }] }, [])).toBe(true);
  expect(floreAProduit(null, [{ role: "flore", documentCanvas: "a.md" }])).toBe(true);
  expect(floreAProduit(null, [{ role: "utilisateur", decisions: ["x"] }])).toBe(false);
  expect(estConversation({ statut: "conversation" })).toBe(true);
});
