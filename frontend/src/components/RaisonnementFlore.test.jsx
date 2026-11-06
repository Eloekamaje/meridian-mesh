import { renderToStaticMarkup } from "react-dom/server";
import RaisonnementFlore from "./RaisonnementFlore";

const texte = (html) => html.replace(/<[^>]+>/g, " ");

test("un dossier N3 expose le niveau, le statut et les findings", () => {
  const html = renderToStaticMarkup(<RaisonnementFlore raisonnement={{
    niveau: "N3", statut: "partiel",
    demande: { questions: ["Quel est le périmètre ?"] },
    options: [{ titre: "A" }, { titre: "B" }],
    critiques: [{ findings: [{ id: "f1", severite: "majeure", constat: "Deux options manquent", remediation: "comparer" }] }],
    gates: [{ id: "G-KRN-03", statut: "echec", message: "0 option" }],
  }} />);
  expect(html).toContain("N3");
  expect(html).toContain("proposition partielle");
  expect(html).toContain("Deux options manquent");
  expect(texte(html)).toMatch(/2\s+options comparées/);
  expect(html).toContain("Quel est le périmètre ?");
});

test("un dossier sain ne signale pas de finding", () => {
  const html = renderToStaticMarkup(<RaisonnementFlore raisonnement={{
    niveau: "N0", statut: "reponse", critiques: [], options: [], gates: [{ id: "G-KRN-00", statut: "ok" }],
  }} />);
  expect(html).toContain("direct");
  expect(html).not.toContain("Revue");
});
