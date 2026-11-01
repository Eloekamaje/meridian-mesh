// Troisième vague ECC : l'ajout d'une conversation à un Travail passe par la fusion serveur.
// Le serveur copie la source dans la cible, supprime la source et rend la cible : le panneau
// n'envoie plus la conversation par PATCH et ne supprime plus rien lui-même.
const fs = require("fs");
const path = require("path");

const source = () => fs.readFileSync(path.join(__dirname, "FlorePanel.jsx"), "utf8");

function corps(nom, suivant) {
  const texte = source();
  const debut = texte.indexOf(`const ${nom} = async`);
  const fin = texte.indexOf(`\n  const ${suivant} =`, debut);
  expect(debut).toBeGreaterThan(-1);
  expect(fin).toBeGreaterThan(debut);
  return texte.slice(debut, fin);
}

test("ajouter à un travail : un seul appel /fusion, sans GET, PATCH conversation ni DELETE client", () => {
  const ajout = corps("ajouterATravail", "proposerAjout");
  expect(ajout).toContain("api.post(`/cases/${cid}/fusion`, { source_cid: travailId })");
  expect(ajout).not.toContain("api.get(");
  expect(ajout).not.toMatch(/api\.patch\(/);
  expect(ajout).not.toMatch(/api\.delete/);
  // La source est nettoyée par le serveur : le panneau repart simplement d'une conversation neuve.
  expect(ajout).toContain("nouvelleConversation()");
  expect(ajout).toContain('new Event("meridian:travaux-maj")');
  expect(ajout).toContain("setTravail(data)");
});

test("une conversation locale sans Travail garde le chemin de création d'un nouveau Travail", () => {
  const ajout = corps("ajouterATravail", "proposerAjout");
  expect(ajout).toMatch(/if \(!travailId\)[\s\S]*creerCase\(\)/);
});

test("aucun api.patch du panneau ne modifie conversation ; seul le statut de creerCase reste", () => {
  const texte = source();
  const patchs = [...texte.matchAll(/api\.patch\(([\s\S]*?)\);/g)].map((m) => m[1]);
  expect(patchs.length).toBeGreaterThan(0);
  for (const p of patchs) expect(p).not.toMatch(/conversation/);
  expect(texte).toContain("api.patch(`/cases/${travailId}`, { statut: STATUT_CONSERVE })");
});

test("la liste « Ajouter à un travail » propose les travaux ouverts du périmètre, sans filtre d’acteur", () => {
  const texte = source();
  expect(texte).toContain("const { info } = usePerimetre()");
  const proposition = texte.slice(texte.indexOf("const proposerAjout"), texte.indexOf("// Sur une page Travail"));
  expect(proposition).toContain('api.get("/cases")');
  expect(proposition).toContain('c.statut !== "clos"');
  expect(proposition).toContain("!estConversation(c)");
  expect(proposition).not.toContain("c.responsable ===");
  expect(proposition).not.toContain("acteur");
});

test("un refus annoncé (400/403/429) ne replie pas sur /aurora et affiche le message", () => {
  const texte = source();
  const demander = texte.slice(texte.indexOf("const demander = async"), texte.indexOf("// Superposition"));
  const refus = demander.indexOf("const refusSansRepli = [400, 403, 429].includes(err.statut);");
  const arretAnnonce = demander.indexOf("if (err.annoncee || refusSansRepli || estArret(err) || err.tourEnCours) throw err;");
  const aurora = demander.indexOf('demanderEnFlux("/aurora/demander/flux"');
  expect(refus).toBeGreaterThan(-1);
  expect(arretAnnonce).toBeGreaterThan(refus);
  expect(aurora).toBeGreaterThan(-1);
  // Le refus annoncé sort du bloc Travail avant tout repli vers /aurora.
  expect(arretAnnonce).toBeLessThan(aurora);
  // Et le message du serveur est rendu dans le fil, pas remplacé par « injoignable ».
  expect(demander).toContain('texte: err.message || "Flore est momentanément injoignable."');
});
