const { coutTemps, formatCout, formatDuree, formatJetons } = require("./coutTemps");

test("le temps, les jetons et le coût sont formatés en français", () => {
  expect(formatDuree(12.4)).toBe("12,4 s");
  expect(formatJetons(3245)).toBe("3\u202f245 jetons");
  expect(formatCout({ montant: 0.0034, devise: "USD" })).toBe("~0,0034 $");
  expect(formatCout({ montant: 0.12, devise: "EUR" })).toBe("~0,12 €");
});

test("la ligne de coût et temps assemble les mesures disponibles", () => {
  const ligne = coutTemps({
    durees: { total: 9.2, premier_texte: 1.8, agent: 6, relecture: 1.2 },
    usage: { total: 3245, cout: { montant: 0.0034, devise: "USD" } },
  });
  expect(ligne.texte).toBe("9,2 s · premier mot 1,8 s · 3\u202f245 jetons · ~0,0034 $");
  expect(ligne.titre).toContain("agent 6,0 s");
  expect(ligne.titre).toContain("relecture 1,2 s");
});

test("une réponse sans mesure n'affiche rien", () => {
  expect(coutTemps({})).toBeNull();
  expect(coutTemps({ durees: {}, usage: {} })).toBeNull();
  expect(formatCout(null)).toBe("");
});


test("le message partagé du Travail et du panneau affiche la ligne", () => {
  const fs = require("fs");
  const path = require("path");
  const source = fs.readFileSync(path.join(__dirname, "..", "components", "MessageFlore.jsx"), "utf8");
  expect(source).toContain("coutTemps");
  expect(source).toContain('data-testid="message-cout-temps"');
});
