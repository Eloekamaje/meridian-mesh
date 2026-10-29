import { renderToStaticMarkup } from "react-dom/server";
import PropositionsFlore from "./PropositionsFlore";

const prop = (extra = {}) => ({ claim: 7, jumeau: "conduit", nom: "Conduit", predicat: "AUTORISE", objet: "publier un article", ...extra });

test("une connaissance proposée par Flore se tranche dans la conversation : Valider / Contester", () => {
  const html = renderToStaticMarkup(<PropositionsFlore propositions={[prop()]} index={3} actif onDecider={() => {}} />);
  expect(html).toContain("publier un article");
  expect(html).toContain("Conduit");
  expect(html).toContain('data-testid="approuver-3-7"');
  expect(html).toContain('data-testid="contester-3-7"');
});

test("tranchée : la décision s'affiche, les boutons disparaissent", () => {
  const props = [prop({ decision: { valeur: "ACCEPTED", par: "architecte", quand: "t" } })];
  const html = renderToStaticMarkup(<PropositionsFlore propositions={props} index={3} actif onDecider={() => {}} />);
  expect(html).toContain("Validée par architecte");
  expect(html).not.toContain('data-testid="approuver-3-7"');
});

test("sans Travail (démonstration), la proposition se lit mais ne se tranche pas ici", () => {
  const html = renderToStaticMarkup(<PropositionsFlore propositions={[prop()]} index={3} actif={false} onDecider={() => {}} />);
  expect(html).toContain("publier un article");
  expect(html).not.toContain('data-testid="approuver-3-7"');
});
