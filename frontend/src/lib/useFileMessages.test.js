import { mettreEnFile, retirerDeFile, regrouperFile } from "./useFileMessages";

test("la file : on ajoute, on retire, et tout part en une seule question", () => {
  let f = mettreEnFile([], "  et si seule la base tombe ?  ");
  f = mettreEnFile(f, "");               // rien de vide
  f = mettreEnFile(f, "compare avec Gestion des articles");
  expect(f).toEqual(["et si seule la base tombe ?", "compare avec Gestion des articles"]);
  expect(retirerDeFile(f, 0)).toEqual(["compare avec Gestion des articles"]);
  expect(f).toHaveLength(2); // sans muter
  expect(regrouperFile(f)).toBe("et si seule la base tombe ?\n\ncompare avec Gestion des articles");
  expect(regrouperFile([])).toBe("");
});

import { act } from "react";
import { createRoot } from "react-dom/client";
import useFileMessages from "./useFileMessages";

test("pendant un tour les messages attendent ; à la fin du tour ils partent ensemble, une seule fois", () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const envois = [];
  let api;
  function Banc({ occupe }) {
    api = useFileMessages(occupe, (t) => envois.push(t));
    return null;
  }
  const racine = createRoot(document.createElement("div"));
  act(() => racine.render(<Banc occupe />));
  act(() => { api.ajouter("et si seule la base tombe ?"); api.ajouter("compare avec Gestion des articles"); });
  expect(envois).toEqual([]);
  expect(api.file).toHaveLength(2);
  act(() => racine.render(<Banc occupe={false} />));
  expect(envois).toEqual(["et si seule la base tombe ?\n\ncompare avec Gestion des articles"]);
  expect(api.file).toEqual([]);
  act(() => racine.render(<Banc occupe={false} />));
  expect(envois).toHaveLength(1);
  act(() => racine.unmount());
});
