import { formaterGrasCode } from "./renduMarkdown";

test("le texte du modèle est échappé avant le gras et le code", () => {
  const html = formaterGrasCode("Voir <img src=x onerror=alert(1)> et **gras** `a<b`");
  expect(html).not.toContain("<img");
  expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
  expect(html).toContain("<strong class='font-semibold text-white'>gras</strong>");
  expect(html).toContain(">a&lt;b</code>");
});

test("guillemets échappés : pas de sortie d'attribut", () => {
  expect(formaterGrasCode(`"' onmouseover=x`)).toBe("&quot;&#39; onmouseover=x");
});
