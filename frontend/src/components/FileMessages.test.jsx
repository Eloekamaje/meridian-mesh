import { renderToStaticMarkup } from "react-dom/server";
import FileMessages from "./FileMessages";

test("les messages en attente s'affichent avec Modifier, Retirer, et Réorienter maintenant pendant un tour", () => {
  const html = renderToStaticMarkup(<FileMessages file={["et si seule la base tombe ?"]} occupe onRetirer={() => {}} onModifier={() => {}} onReorienter={() => {}} />);
  expect(html).toContain("et si seule la base tombe ?");
  expect(html).toContain("Modifier");
  expect(html).toContain("Retirer");
  expect(html).toContain("Réorienter maintenant");
  expect(renderToStaticMarkup(<FileMessages file={[]} occupe />)).toBe("");
});
