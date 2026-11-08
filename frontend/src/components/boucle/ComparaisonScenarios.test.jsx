import { act } from "react";
import { createRoot } from "react-dom/client";
import ComparaisonScenarios from "./ComparaisonScenarios";
import { boucleApi } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  boucleApi: {
    listerScenarios: jest.fn(),
    comparerScenarios: jest.fn(),
  },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const investigation = {
  id: "inv-1",
  type: "INVESTIGATION",
  famille: "investigation",
  titre: "Comprendre le délai",
  donnees: { statut: "OPEN" },
};

const scenarios = [
  {
    id: "s1",
    titre: "Automatiser",
    statut: "PROPOSED",
    investigation_id: "inv-1",
    valeur_estimee: 100,
    cout_estime: 50,
    delai_jours: 10,
    risque: 0.2,
    reversibilite: "REVERSIBLE",
    complexite: 0.4,
  },
  {
    id: "s2",
    titre: "Réorganiser",
    statut: "DRAFT",
    investigation_id: "inv-1",
    valeur_estimee: 120,
    cout_estime: null,
    delai_jours: 8,
    risque: 0.3,
    reversibilite: "PARTIELLE",
    complexite: 0.5,
  },
];

function comparaison() {
  return {
    reference: scenarios[0],
    scenarios: [
      {
        ...scenarios[0],
        ecarts: {
          valeur_estimee: { delta: 0, delta_pct: 0, sens: "identique" },
          cout_estime: { delta: 0, delta_pct: 0, sens: "identique" },
          delai_jours: { delta: 0, delta_pct: 0, sens: "identique" },
          risque: { delta: 0, delta_pct: 0, sens: "identique" },
          complexite: { delta: 0, delta_pct: 0, sens: "identique" },
          reversibilite: { reference: "REVERSIBLE", scenario: "REVERSIBLE", identique: true },
          statut: { reference: "PROPOSED", scenario: "PROPOSED", identique: true },
        },
      },
      {
        ...scenarios[1],
        ecarts: {
          valeur_estimee: { delta: 20, delta_pct: 20, sens: "hausse" },
          cout_estime: { delta: null, delta_pct: null, sens: null },
          delai_jours: { delta: -2, delta_pct: -20, sens: "baisse" },
          risque: { delta: 0.1, delta_pct: 50, sens: "hausse" },
          complexite: { delta: 0.1, delta_pct: 25, sens: "hausse" },
          reversibilite: { reference: "REVERSIBLE", scenario: "PARTIELLE", identique: false },
          statut: { reference: "PROPOSED", scenario: "DRAFT", identique: false },
        },
      },
    ],
  };
}

function monter() {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  return { hote, racine };
}

async function rendre(racine, objet = investigation) {
  await act(async () => {
    racine.render(<ComparaisonScenarios objet={objet} />);
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  boucleApi.listerScenarios.mockResolvedValue({ data: { scenarios } });
  boucleApi.comparerScenarios.mockResolvedValue({ data: comparaison() });
});

afterEach(() => {
  document.body.innerHTML = "";
});

test("charge les scénarios du parent, les sélectionne et compare", async () => {
  const { hote, racine } = monter();
  await rendre(racine);

  expect(boucleApi.listerScenarios).toHaveBeenCalledWith({ investigation_id: "inv-1" });
  expect(hote.querySelector('[data-testid="boucle-comparaison"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-comparaison-scenario-s1"]').checked).toBe(true);
  expect(hote.querySelector('[data-testid="boucle-comparaison-scenario-s2"]').checked).toBe(true);
  expect(hote.querySelector('[data-testid="boucle-comparaison-reference"]').value).toBe("s1");
  expect(hote.querySelector('[data-testid="boucle-comparaison-lancer"]').disabled).toBe(false);

  await act(async () => {
    hote.querySelector('[data-testid="boucle-comparaison-lancer"]').click();
  });

  expect(boucleApi.comparerScenarios).toHaveBeenCalledWith({
    scenario_ids: ["s1", "s2"],
    reference_id: "s1",
  });
  const tableau = hote.querySelector('[data-testid="boucle-comparaison-resultat"] table');
  expect(tableau).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-comparaison-resultat"]').textContent)
    .toContain("+20");
  expect(hote.querySelector('[data-testid="boucle-comparaison-ligne-s2"]').textContent)
    .toContain("PARTIELLE");
  expect(hote.querySelector('[data-testid="boucle-comparaison-ligne-s2"]').textContent)
    .toContain("écart inconnu");

  await act(async () => { racine.unmount(); });
});

test("un seul scénario désactive la comparaison et l'état vide est explicite", async () => {
  boucleApi.listerScenarios.mockResolvedValue({ data: { scenarios: [scenarios[0]] } });
  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-comparaison-lancer"]').disabled).toBe(true);
  expect(hote.querySelector('[data-testid="boucle-comparaison-incomplet"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });

  boucleApi.listerScenarios.mockResolvedValue({ data: { scenarios: [] } });
  const second = monter();
  await rendre(second.racine);
  expect(second.hote.querySelector('[data-testid="boucle-comparaison-vide"]')).not.toBeNull();

  await act(async () => { second.racine.unmount(); });
});

test("annonce les erreurs de liste et de comparaison", async () => {
  boucleApi.listerScenarios.mockRejectedValue({ response: { status: 503 } });
  const { hote, racine } = monter();
  await rendre(racine);

  const erreur = hote.querySelector('[data-testid="boucle-comparaison-erreur"]');
  expect(erreur).not.toBeNull();
  expect(erreur.getAttribute("role")).toBe("alert");
  expect(erreur.textContent).toContain("indisponible");

  await act(async () => { racine.unmount(); });

  boucleApi.listerScenarios.mockResolvedValue({ data: { scenarios } });
  boucleApi.comparerScenarios.mockRejectedValue({ response: { status: 404 } });
  const second = monter();
  await rendre(second.racine);
  await act(async () => {
    second.hote.querySelector('[data-testid="boucle-comparaison-lancer"]').click();
  });

  const erreurComparaison = second.hote.querySelector('[data-testid="boucle-comparaison-erreur"]');
  expect(erreurComparaison).not.toBeNull();
  expect(erreurComparaison.textContent).toContain("introuvable");

  await act(async () => { second.racine.unmount(); });
});

test("changer la référence efface l'ancienne comparaison et invalide une réponse en vol", async () => {
  const { hote, racine } = monter();
  await rendre(racine);
  await act(async () => {
    hote.querySelector('[data-testid="boucle-comparaison-lancer"]').click();
  });
  expect(hote.querySelector('[data-testid="boucle-comparaison-resultat"]')).not.toBeNull();

  await act(async () => {
    const reference = hote.querySelector('[data-testid="boucle-comparaison-reference"]');
    reference.value = "s2";
    reference.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(hote.querySelector('[data-testid="boucle-comparaison-resultat"]')).toBeNull();

  let resoudre;
  boucleApi.comparerScenarios.mockImplementation(
    () => new Promise((resolve) => { resoudre = resolve; }),
  );
  await act(async () => {
    hote.querySelector('[data-testid="boucle-comparaison-lancer"]').click();
  });
  await act(async () => {
    const reference = hote.querySelector('[data-testid="boucle-comparaison-reference"]');
    reference.value = "s1";
    reference.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => {
    resoudre({ data: comparaison() });
  });
  expect(hote.querySelector('[data-testid="boucle-comparaison-resultat"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("plafonne la sélection à 50 scénarios", async () => {
  const nombreux = Array.from({ length: 51 }, (_, index) => ({
    ...scenarios[0],
    id: `s-${index}`,
    titre: `Scénario ${index}`,
  }));
  boucleApi.listerScenarios.mockResolvedValue({ data: { scenarios: nombreux } });

  const { hote, racine } = monter();
  await rendre(racine);

  const coches = [...hote.querySelectorAll('[data-testid^="boucle-comparaison-scenario-"]')]
    .filter((input) => input.checked);
  expect(coches).toHaveLength(50);
  expect(hote.querySelector('[data-testid="boucle-comparaison-selection-erreur"]').textContent)
    .toContain("50");

  await act(async () => {
    hote.querySelector('[data-testid="boucle-comparaison-scenario-s-50"]').click();
  });
  expect([...hote.querySelectorAll('[data-testid^="boucle-comparaison-scenario-"]')]
    .filter((input) => input.checked)).toHaveLength(50);

  await act(async () => { racine.unmount(); });
});

test("un changement d'objet invalide une comparaison en vol", async () => {
  const autreObjet = { ...investigation, id: "inv-2", titre: "Autre investigation" };
  let resoudreComparaison;
  boucleApi.comparerScenarios.mockImplementation(
    () => new Promise((resolve) => { resoudreComparaison = resolve; }),
  );

  const { hote, racine } = monter();
  await rendre(racine);
  await act(async () => {
    hote.querySelector('[data-testid="boucle-comparaison-lancer"]').click();
  });
  expect(hote.querySelector('[data-testid="boucle-comparaison-lancer"]').textContent)
    .toContain("Comparaison");

  await act(async () => {
    racine.render(<ComparaisonScenarios objet={autreObjet} />);
  });
  expect(boucleApi.listerScenarios).toHaveBeenLastCalledWith({ investigation_id: "inv-2" });
  expect(hote.querySelector('[data-testid="boucle-comparaison-lancer"]').textContent)
    .toBe("Comparer");

  await act(async () => {
    resoudreComparaison({ data: comparaison() });
  });
  expect(hote.querySelector('[data-testid="boucle-comparaison-resultat"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-comparaison-lancer"]').textContent)
    .toBe("Comparer");

  await act(async () => { racine.unmount(); });
});

test("le tableau est accessible et expose les en-têtes de colonnes", async () => {
  const { hote, racine } = monter();
  await rendre(racine);
  await act(async () => {
    hote.querySelector('[data-testid="boucle-comparaison-lancer"]').click();
  });

  const tableau = hote.querySelector('[data-testid="boucle-comparaison-resultat"] table');
  expect(tableau).not.toBeNull();
  expect(tableau.querySelector("caption")).not.toBeNull();
  expect([...tableau.querySelectorAll("thead th")].every((th) => th.getAttribute("scope") === "col"))
    .toBe(true);
  expect(tableau.querySelector("tbody th").getAttribute("scope")).toBe("row");

  await act(async () => { racine.unmount(); });
});
