// P0 de MERIDIAN_Chat_Standards_v1 : aucun bouton des conversations ne promet une action qu'il ne fait pas.
// Un bouton doit agir (onClick), soumettre un formulaire (type="submit") ou servir de déclencheur à un composant
// qui le gère (asChild). Un bouton sans rien de cela est factice : le test le refuse et dit lequel.
const fs = require("fs");
const path = require("path");

const ECRANS = ["components/case/OngletTravail.jsx", "components/FlorePanel.jsx", "components/ComposerFlore.jsx"];

function boutons(source) {
  const trouves = [];
  const motif = /<button\b/g;
  let m;
  while ((m = motif.exec(source)) !== null) {
    let i = m.index + 7, profondeur = 0;
    for (; i < source.length; i++) {  // jusqu'au « > » qui ferme la balise, hors des {expressions}
      if (source[i] === "{") profondeur++;
      else if (source[i] === "}") profondeur--;
      else if (source[i] === ">" && profondeur === 0) break;
    }
    trouves.push({ balise: source.slice(m.index, i + 1), ligne: source.slice(0, m.index).split("\n").length });
  }
  return trouves;
}

test.each(ECRANS)("aucun bouton factice dans %s", (fichier) => {
  const source = fs.readFileSync(path.join(__dirname, "..", fichier), "utf8");
  const factices = boutons(source)
    .filter(({ balise }) => !/onClick=|type="submit"|\basChild\b|\{\.\.\./.test(balise))
    .map(({ ligne }) => `${fichier}:${ligne}`);
  expect(factices).toEqual([]);
});

test("les retours 👍/👎 partent au serveur, pas dans un simple message", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "components/case/OngletTravail.jsx"), "utf8");
  expect(source).toContain("/messages/${index}/retour");
  expect(source).not.toMatch(/Merci pour votre retour|Feedback pris en compte|Lien prêt/);
});

test.each(ECRANS)("aucun bouton qui annonce seulement « bientôt » dans %s", (fichier) => {
  // Une action qui n'existe pas encore n'a pas de bouton : un bouton « bientôt » reste une promesse.
  const source = fs.readFileSync(path.join(__dirname, "..", fichier), "utf8");
  expect(source).not.toMatch(/arrive prochainement|\(bientôt\)/);
});
