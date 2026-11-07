import { traceCanoniqueDeTravail } from "./boucleUi";

describe("traceCanoniqueDeTravail", () => {
  test("lit une trace imbriquée dans le travail", () => {
    const trace = traceCanoniqueDeTravail({
      boucle: {
        objet: { id: "dec-1", statut: "DECIDED" },
        chaine: [{ id: "sit-1", type: "SITUATION", titre: "Latence" }],
      },
    });
    expect(trace).toEqual({
      id: "dec-1",
      statut: "DECIDED",
      chaine: [{ id: "sit-1", type: "SITUATION", titre: "Latence" }],
    });
  });

  test("accepte une trace plate et une trace textuelle", () => {
    expect(traceCanoniqueDeTravail({
      boucle_id: "ini-1",
      boucle_statut: "PLANNED",
      boucle_chaine: ["sit-1", "dec-1"],
    })).toEqual({ id: "ini-1", statut: "PLANNED", chaine: ["sit-1", "dec-1"] });

    expect(traceCanoniqueDeTravail({ boucle: "sit-1" }))
      .toEqual({ id: "sit-1", statut: "", chaine: [] });
  });

  test("lit aussi trace_canonique et objet_boucle", () => {
    expect(traceCanoniqueDeTravail({
      trace_canonique: { id: "out-1", donnees: { statut: "OBSERVED" }, objets: ["ini-1"] },
    })).toEqual({ id: "out-1", statut: "OBSERVED", chaine: ["ini-1"] });
    expect(traceCanoniqueDeTravail({
      objet_boucle: { objet_id: "inv-1", statut: "OPEN", chaine: [] },
    })).toEqual({ id: "inv-1", statut: "OPEN", chaine: [] });
  });

  test("accepte une chaîne canonique exposée directement en tableau", () => {
    expect(traceCanoniqueDeTravail({
      boucle: [
        { id: "sit-1", type: "SITUATION", titre: "Latence" },
        { id: "inv-1", type: "INVESTIGATION", titre: "Comprendre", statut: "OPEN" },
      ],
    })).toEqual({
      id: "inv-1",
      statut: "OPEN",
      chaine: [
        { id: "sit-1", type: "SITUATION", titre: "Latence" },
        { id: "inv-1", type: "INVESTIGATION", titre: "Comprendre", statut: "OPEN" },
      ],
    });
  });

  test("retourne null sans trace exploitable", () => {
    expect(traceCanoniqueDeTravail(null)).toBeNull();
    expect(traceCanoniqueDeTravail({ id: "case-1", titre: "Travail legacy" })).toBeNull();
    expect(traceCanoniqueDeTravail({ boucle: { chaine: [] } })).toBeNull();
  });
});
