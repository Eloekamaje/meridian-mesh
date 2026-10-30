const {
  COMMANDES, appliquerCommande, appliquerMention, commandesFiltrees,
  normaliser, requeteCommande, requeteMention, resoudreCommande,
} = require("./mentionsCommandes");

test("une mention se détecte et s'insère au dernier token", () => {
  expect(requeteMention("Que dit @cond")).toBe("cond");
  expect(requeteMention("Que dit @")).toBe("");
  expect(requeteMention("email a@b.fr")).toBeNull();
  expect(appliquerMention("Que dit @cond", "Conduit")).toBe("Que dit @Conduit ");
});

test("une commande se détecte et remplit une consigne explicite", () => {
  expect(requeteCommande("/resu")).toBe("resu");
  expect(requeteCommande("question /resu")).toBe("resu");
  expect(requeteCommande("http://x/y")).toBeNull();
  expect(commandesFiltrees("resu").map((c) => c.nom)).toEqual(["resumer"]);
  const commande = resoudreCommande("/resumer");
  expect(commande.prompt).toContain("Résume ce travail");
  expect(appliquerCommande("/resumer", commande)).toBe(commande.prompt);
  expect(resoudreCommande("/aide").local).toContain("/investiguer");
  expect(resoudreCommande("/inconnue")).toBeNull();
});

test("les commandes sont stables et sans doublon", () => {
  expect(new Set(COMMANDES.map((c) => c.nom)).size).toBe(COMMANDES.length);
  expect(normaliser("Résumer")).toBe("resumer");
});


test("le compositeur du Travail câble mentions et commandes", () => {
  const fs = require("fs");
  const path = require("path");
  const source = fs.readFileSync(path.join(__dirname, "..", "components", "case", "OngletTravail.jsx"), "utf8");
  expect(source).toContain('data-testid="case-mention-menu"');
  expect(source).toContain('data-testid="case-commande-menu"');
  expect(source).toContain("mentions: mentionsActives");
  expect(source).toContain("resoudreCommande(brut)");
});
