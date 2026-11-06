import { premierArgument, resumeOutil } from "./renduOutil";

test("lire_code expose une référence copiable et masque le code", () => {
  const resume = resumeOutil({
    nom: "lire_code",
    arguments: { depot: "conduit", chemin: "app/api/routes/articles.py", debut: 10, fin: 20 },
  });
  expect(resume.titre).toBe("Lecture de code");
  expect(resume.detail).toBe("app/api/routes/articles.py#L10-L20");
  expect(resume.champs).toContainEqual({ label: "Dépôt", valeur: "conduit" });
  expect(resume.actions).toContainEqual({
    type: "copier", texte: "app/api/routes/articles.py#L10-L20", label: "Copier la référence",
  });
  expect(resume.masquerExtrait).toBe(true);
});

test("mobiliser_jumeaux expose les jumeaux et une action par jumeau", () => {
  const resume = resumeOutil({
    nom: "mobiliser_jumeaux",
    arguments: { jumeaux: ["conduit", "gestion-des-articles"], question: "Qui peut publier ?" },
  });
  expect(resume.detail).toBe("Qui peut publier ?");
  expect(resume.champs).toEqual([{ label: "Jumeaux", valeur: "conduit, gestion-des-articles" }]);
  expect(resume.actions.map((a) => a.id)).toEqual(["conduit", "gestion-des-articles"]);
});

test("lire_piece expose une action vers la pièce", () => {
  const resume = resumeOutil({
    nom: "lire_piece",
    arguments: { piece_id: "piece-7", section_id: "s3" },
  });
  expect(resume.detail).toBe("piece-7 · s3");
  expect(resume.actions).toEqual([{ type: "piece", id: "piece-7", label: "Ouvrir la pièce" }]);
});

test("un outil inconnu retombe sur le premier argument, sans invention", () => {
  const resume = resumeOutil({ nom: "outil_inedit", arguments: { x: 42 } });
  expect(resume.titre).toBe("outil_inedit");
  expect(resume.detail).toBe("42");
  expect(resume.actions).toEqual([]);
  expect(premierArgument({ a: "premier", b: "second" })).toBe("premier");
});

test("lire_table expose la pièce et la feuille", () => {
  const resume = resumeOutil({ nom: "lire_table", arguments: { piece_id: "piece-9", feuille: "Budget" } });
  expect(resume.detail).toBe("piece-9 · Budget");
  expect(resume.actions).toEqual([{ type: "piece", id: "piece-9", label: "Ouvrir la pièce" }]);
});
