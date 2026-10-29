import { numeroPastille, couperPastille, phraseDe, bilanEffets, typeSource, sansPastilles } from "./preuvesFlore";

test("une pastille se reconnaît à son lien #preuve-n", () => {
  expect(numeroPastille("#preuve-3")).toBe(3);
  expect(numeroPastille("https://exemple.org")).toBeNull();
  expect(numeroPastille("#preuve-x")).toBeNull();
});

test("au fil de l'eau, une pastille à moitié écrite ne s'affiche pas", () => {
  expect(couperPastille("Une base [1](#pre")).toBe("Une base");
  expect(couperPastille("Une base [1")).toBe("Une base");
  expect(couperPastille("Une base [1](#preuve-1) et")).toBe("Une base [1](#preuve-1) et");
});

test("la phrase que supporte une preuve : celle de sa pastille, sans marques", () => {
  const t = "Intro. Elle dépend d'une base unique [1](#preuve-1). Autre chose.\n- **bloquant** — Tout s'arrête [2](#preuve-2) [1](#preuve-1)";
  expect(phraseDe(t, 1)).toBe("Elle dépend d'une base unique.");
  expect(phraseDe(t, 2)).toBe("bloquant — Tout s'arrête");
  expect(phraseDe(t, 9)).toBeNull();
});

test("le bilan d'une note d'impact : effets prouvés sur effets", () => {
  const t = "- **Bloquant** — a [1](#preuve-1)\n- **dégradé** : b\n- **sans effet visible** — c [2](#preuve-2)\n- **Inconnu** — d\n- autre ligne";
  expect(bilanEffets(t)).toEqual({ prouves: 2, total: 4 });
  expect(bilanEffets("Pas de note.")).toBeNull();
});

test("le type d'une source se lit dans son emplacement", () => {
  expect(typeSource("git://conduit@abc:app/x.py#L1-L2")).toBe("Code");
  expect(typeSource("confluence://TBT/123@7#L1")).toBe("Confluence");
  expect(typeSource("jira://PAY/1@2#L1")).toBe("Jira");
});

test("le texte copié n'emporte pas les pastilles", () => {
  expect(sansPastilles("Une base [1](#preuve-1) [2](#preuve-2).")).toBe("Une base.");
});
