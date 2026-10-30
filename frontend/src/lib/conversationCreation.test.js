// Quatrième vague ECC : `conversation` ne se modifie plus par PATCH. L'accueil de Flore part
// avec le POST /cases qui crée le Travail.
const fs = require("fs");
const path = require("path");

const lire = (f) => fs.readFileSync(path.join(__dirname, "..", f), "utf8");

const bloc = (source, debut, suivant) => {
  const i = source.indexOf(debut);
  const j = source.indexOf(suivant, i);
  expect(i).toBeGreaterThan(-1);
  expect(j).toBeGreaterThan(i);
  return source.slice(i, j);
};

test.each(["pages/Atlas.jsx", "pages/LaboAtlasEtendu.jsx"])("%s ne modifie jamais la conversation par PATCH", (fichier) => {
  const source = lire(fichier);
  const patchs = [...source.matchAll(/api\.patch\(([\s\S]*?)\);/g)].map((m) => m[1]);
  for (const p of patchs) expect(p).not.toMatch(/conversation/);
});

test.each([
  ["pages/Atlas.jsx", "const ouvrirInvestigationJumeau = async"],
  ["pages/LaboAtlasEtendu.jsx", "const voler = useCallback"],
])("%s crée le Travail avec l'accueil de Flore déjà dans conversation", (fichier, suivant) => {
  const source = lire(fichier);
  const creation = bloc(source, "const parlerAuJumeau = async", suivant);
  expect(creation).toContain('api.post("/cases"');
  expect(creation).toContain("conversation: [{ role: \"flore\", comportement: \"expliquer\", texte: accueil, quand: now }]");
  expect(creation).not.toMatch(/api\.patch\(/);
});
