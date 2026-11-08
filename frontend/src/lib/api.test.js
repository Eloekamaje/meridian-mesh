import api, { boucleApi, entetesPerimetre } from "./api";

beforeEach(() => {
  localStorage.clear();
});

test("entetesPerimetre ajoute X-Tenant quand un tenant est stocké", () => {
  localStorage.setItem("meridian.tenant", "banque");
  expect(entetesPerimetre()).toMatchObject({ "X-Tenant": "banque" });
});

test("entetesPerimetre n'envoie pas d'en-tête X-Tenant vide", () => {
  localStorage.setItem("meridian.tenant", "   ");
  expect(entetesPerimetre()).not.toHaveProperty("X-Tenant");
  localStorage.removeItem("meridian.tenant");
  expect(entetesPerimetre()).not.toHaveProperty("X-Tenant");
});

test("le timeout de 20 secondes est réservé aux transitions, pas au client global", () => {
  expect(api.defaults.timeout).toBe(0);
});

describe("boucleApi", () => {
  let poster;

  beforeEach(() => {
    poster = jest.spyOn(api, "post").mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    poster.mockRestore();
  });

  test("creerSituation poste la situation racine sans en-tête d'idempotence", async () => {
    const corps = {
      titre: "Latence des paiements",
      description: "Les paiements ralentissent.",
      resume: "Trois flux concernés.",
      priorite: "haute",
      twin_ids: ["app-paiement", "process-controle"],
      mode: "OBSERVED",
    };

    await boucleApi.creerSituation(corps);

    expect(poster).toHaveBeenCalledWith("/boucle/situations", corps, { timeout: 20000 });
    expect(poster.mock.calls[0][2]).not.toHaveProperty("headers");
  });

  test("creerScenario poste le scénario rattaché sans en-tête d'idempotence", async () => {
    const corps = {
      titre: "Automatiser la pièce",
      investigation_id: "inv-1",
      valeur_estimee: 12000,
      reversibilite: "PARTIELLE",
    };

    await boucleApi.creerScenario(corps);

    expect(poster).toHaveBeenCalledWith("/boucle/scenarios", corps, { timeout: 20000 });
    expect(poster.mock.calls[0][2]).not.toHaveProperty("headers");
  });

  test("creerExpression poste l'expression rattachée sans en-tête d'idempotence", async () => {
    const corps = {
      type_expression: "OPPORTUNITE",
      formulation: "Automatiser la ressaisie",
      canal: "entretien",
      auteur: "Alice",
      inconnues: ["volume réel"],
      confiance: 0.8,
    };

    await boucleApi.creerExpression("sit/1", corps);

    expect(poster).toHaveBeenCalledWith(
      "/boucle/situations/sit%2F1/expressions",
      corps,
      { timeout: 20000 },
    );
    expect(poster.mock.calls[0][2]).not.toHaveProperty("headers");
  });

  test("comparerScenarios poste les ids et la référence", async () => {
    const corps = { scenario_ids: ["s1", "s2"], reference_id: "s2" };

    await boucleApi.comparerScenarios(corps);

    expect(poster).toHaveBeenCalledWith("/boucle/scenarios/comparer", corps, { timeout: 20000 });
  });

  test("listerScenarios interroge la liste avec les filtres et le timeout des transitions", async () => {
    const get = jest.spyOn(api, "get").mockResolvedValue({ data: { scenarios: [] } });

    await boucleApi.listerScenarios({ investigation_id: "inv/1" });

    expect(get).toHaveBeenCalledWith("/boucle/scenarios", {
      params: { investigation_id: "inv/1" },
      timeout: 20000,
    });
    get.mockRestore();
  });

  test("listerOpportunites et listerRisques filtrent par expression", async () => {
    const get = jest.spyOn(api, "get").mockResolvedValue({ data: {} });

    await boucleApi.listerOpportunites("expr/1", { limite: 25 });
    await boucleApi.listerRisques("expr/1");

    expect(get).toHaveBeenNthCalledWith(
      1, "/boucle/expressions/expr%2F1/opportunities",
      { params: { limite: 25 }, timeout: 20000 });
    expect(get).toHaveBeenNthCalledWith(
      2, "/boucle/expressions/expr%2F1/risks",
      { params: undefined, timeout: 20000 });
    get.mockRestore();
  });

  test("les erreurs de scénario sont propagées sans être masquées", async () => {
    const erreur = { response: { status: 404, data: { detail: "Scénario introuvable" } } };
    poster.mockRejectedValueOnce(erreur);

    await expect(boucleApi.comparerScenarios({ scenario_ids: ["s1", "s2"] }))
      .rejects.toBe(erreur);
  });

  test("creerSituation propage l'erreur du backend sans la masquer", async () => {
    const erreur = {
      response: { status: 409, data: { detail: "objet déjà existant" } },
    };
    poster.mockRejectedValueOnce(erreur);

    await expect(boucleApi.creerSituation({ titre: "Doublon" })).rejects.toBe(erreur);
  });

  test.each([
    ["ouvrirInvestigation", "sit/1", "/boucle/situations/sit%2F1/investigations"],
    ["creerExpression", "sit/1", "/boucle/situations/sit%2F1/expressions"],
    ["creerOpportunite", "expr/1", "/boucle/expressions/expr%2F1/opportunities"],
    ["creerRisque", "expr/1", "/boucle/expressions/expr%2F1/risks"],
    ["changerStatutOpportunite", "opportunity/1", "/boucle/opportunities/opportunity%2F1/statut"],
    ["changerStatutRisque", "risk/1", "/boucle/risks/risk%2F1/statut"],
    ["proposerDecision", "inv-1", "/boucle/investigations/inv-1/decisions"],
    ["trancherDecision", "dec-1", "/boucle/decisions/dec-1/trancher"],
    ["lancerInitiative", "dec-1", "/boucle/decisions/dec-1/initiatives"],
    ["mesurerOutcome", "ini-1", "/boucle/initiatives/ini-1/outcomes"],
    ["capitaliserLearningDepuisOutcome", "out-1", "/boucle/outcomes/out-1/learnings"],
    ["capitaliserLearningDepuisInvestigation", "inv-1", "/boucle/investigations/inv-1/learnings"],
  ])("%s poste le corps vers %s", async (methode, identifiant, chemin) => {
    const corps = { exemple: true };
    await boucleApi[methode](identifiant, corps);
    expect(poster).toHaveBeenCalledWith(chemin, corps, { timeout: 20000 });
  });

  test("ajoute une clé d'idempotence quand elle est fournie", async () => {
    const corps = { titre: "Comprendre" };
    await boucleApi.ouvrirInvestigation("sit-1", corps, { idempotencyKey: "cle-123" });
    expect(poster).toHaveBeenCalledWith(
      "/boucle/situations/sit-1/investigations",
      corps,
      { timeout: 20000, headers: { "Idempotency-Key": "cle-123" } },
    );
  });

  test("n'envoie aucun en-tête d'idempotence par défaut", async () => {
    await boucleApi.ouvrirInvestigation("sit-1", { titre: "Comprendre" });
    expect(poster.mock.calls[0][2]).toEqual({ timeout: 20000 });
    expect(poster.mock.calls[0][2]).not.toHaveProperty("headers");
  });

  test("refuse un identifiant vide sans appeler le backend", async () => {
    await expect(boucleApi.mesurerOutcome("", {})).rejects.toThrow("identifiant");
    expect(poster).not.toHaveBeenCalled();
  });
});
