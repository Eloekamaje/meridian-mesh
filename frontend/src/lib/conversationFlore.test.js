import { prefixeTravail, urlMessage, navigation, navVersions, navBranches, regrouper, erreurAction, resultatsRecherche, remplacerMessage, floreAProduit, estConversation, tronquerApres, garderReperes, activiteDuMessage, explicationArret, attendreReponse } from "./conversationFlore";

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

test("modifier une question : la suite disparaît tout de suite, les marqueurs d'avant restent", () => {
  const ms = [{ role: "utilisateur", texte: "a" }, { role: "flore", texte: "A" }, { marqueur: true, texte: "Contexte actualisé : x" },
    { role: "utilisateur", texte: "b" }, { role: "flore", texte: "B" }, { marqueur: true, texte: "y" }];
  expect(tronquerApres(ms, 2, "b2")).toEqual([ms[0], ms[1], ms[2], { role: "utilisateur", texte: "b2" }]);
  expect(tronquerApres(ms, 0, "a2")).toEqual([{ role: "utilisateur", texte: "a2" }]);
});

test("relire la conversation garde les marqueurs locaux à leur place", () => {
  const avant = [{ role: "utilisateur", texte: "a" }, { role: "flore", texte: "A" }, { marqueur: true, texte: "m1" },
    { role: "utilisateur", texte: "b" }];
  const serveur = [{ role: "utilisateur", texte: "a" }, { role: "flore", texte: "A*" }, { role: "utilisateur", texte: "b" },
    { role: "flore", texte: "B" }];
  expect(garderReperes(avant, serveur)).toEqual([serveur[0], serveur[1], avant[2], serveur[2], serveur[3]]);
  // un marqueur posé après le dernier message reste en bas ; sans marqueur, la conversation du serveur telle quelle
  expect(garderReperes([...serveur, { marqueur: true, texte: "fin" }], serveur).at(-1).texte).toBe("fin");
  expect(garderReperes([], serveur)).toBe(serveur);
  // une conversation raccourcie (modification) : le marqueur d'au-delà est rangé en bas, jamais perdu
  expect(garderReperes(avant, serveur.slice(0, 1)).map((m) => m.texte)).toEqual(["a", "m1"]);
});

test("l'activité d'une réponse : la locale d'abord, sinon celle enregistrée par le serveur", () => {
  const locale = { id: "l", status: "done", ops: [] };
  expect(activiteDuMessage({ _activite: locale, activite: [{ label: "x" }] })).toBe(locale);
  const lue = activiteDuMessage({ activite: [{ label: "Je lis…", outil: { id: "u", nom: "lire_code", etat: "fait" } }] });
  expect(lue.status).toBe("done");
  expect(lue.ops[0].outil.nom).toBe("lire_code");
  expect(activiteDuMessage({ texte: "ancien message" })).toBeNull();
});

test("un tour arrêté s'explique : outils faits, en cours, texte écrit, non relu", () => {
  const m = { texte: "Il existe", interrompu: true, activite: [
    { label: "a", outil: { nom: "lire_code", etat: "fait" } }, { label: "b", outil: { nom: "lire_code", etat: "fait" } },
    { label: "Je regarde…" }, { label: "c", outil: { nom: "suivre_appels", etat: "en_cours" } }] };
  expect(explicationArret(m)).toBe("Arrêté par vous · 2 outils faits (lire_code) · 1 en cours (suivre_appels) · 9 caractères écrits · non relu");
  expect(explicationArret({ texte: "", interrompu: true })).toBe("Arrêté par vous · rien d'écrit · non relu");
});

test("après une coupure non renouée, on relit jusqu'à la réponse enregistrée", async () => {
  const lectures = [{ conversation: [1, 2] }, { conversation: [1, 2, 3] }, { conversation: [1, 2, 3, 4] }];
  const charger = jest.fn(async () => lectures.shift());
  expect(await attendreReponse(charger, 2, { pas: 1 })).toEqual({ conversation: [1, 2, 3, 4] });
  expect(charger).toHaveBeenCalledTimes(3);
  expect(await attendreReponse(async () => ({ conversation: [] }), 2, { pas: 1, essais: 2 })).toBeNull();
});
