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

describe("boucleApi", () => {
  let poster;

  beforeEach(() => {
    poster = jest.spyOn(api, "post").mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    poster.mockRestore();
  });

  test.each([
    ["ouvrirInvestigation", "sit/1", "/boucle/situations/sit%2F1/investigations"],
    ["proposerDecision", "inv-1", "/boucle/investigations/inv-1/decisions"],
    ["trancherDecision", "dec-1", "/boucle/decisions/dec-1/trancher"],
    ["lancerInitiative", "dec-1", "/boucle/decisions/dec-1/initiatives"],
    ["mesurerOutcome", "ini-1", "/boucle/initiatives/ini-1/outcomes"],
    ["capitaliserLearningDepuisOutcome", "out-1", "/boucle/outcomes/out-1/learnings"],
    ["capitaliserLearningDepuisInvestigation", "inv-1", "/boucle/investigations/inv-1/learnings"],
  ])("%s poste le corps vers %s", async (methode, identifiant, chemin) => {
    const corps = { exemple: true };
    await boucleApi[methode](identifiant, corps);
    expect(poster).toHaveBeenCalledWith(chemin, corps, undefined);
  });

  test("ajoute une clé d'idempotence quand elle est fournie", async () => {
    const corps = { titre: "Comprendre" };
    await boucleApi.ouvrirInvestigation("sit-1", corps, { idempotencyKey: "cle-123" });
    expect(poster).toHaveBeenCalledWith(
      "/boucle/situations/sit-1/investigations",
      corps,
      { headers: { "Idempotency-Key": "cle-123" } },
    );
  });

  test("refuse un identifiant vide sans appeler le backend", async () => {
    await expect(boucleApi.mesurerOutcome("", {})).rejects.toThrow("identifiant");
    expect(poster).not.toHaveBeenCalled();
  });
});
