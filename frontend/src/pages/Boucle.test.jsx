import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import Boucle from "./Boucle";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn() },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const situation = {
  id: "sit-1",
  famille: "emergence",
  type: "SITUATION",
  mode: "OBSERVED",
  titre: "Latence des paiements",
  donnees: {
    resume: "Les paiements ralentissent depuis la modification de la règle R-118.",
    twin_ids: ["app-paiement"],
  },
  version: 2,
  observe_le: "2026-10-29T08:00:00Z",
  cree_le: "2026-10-28T08:00:00Z",
  maj_le: "2026-10-30T08:00:00Z",
};

const investigation = {
  id: "inv-1",
  famille: "investigation",
  type: "INVESTIGATION",
  mode: "DECLARED",
  titre: "Comprendre le goulot de contrôle",
  donnees: { question: "Quel contrôle synchrone bloque les paiements ?" },
  version: 1,
  observe_le: "2026-10-29T09:00:00Z",
  maj_le: "2026-10-30T09:00:00Z",
};

const decision = {
  id: "dec-1",
  famille: "decision",
  type: "DECISION",
  mode: "DECLARED",
  titre: "Rendre le contrôle R-118 asynchrone",
  donnees: { statut: "DECIDED", choix: "Passer R-118 en asynchrone" },
  version: 1,
  observe_le: "2026-10-29T10:00:00Z",
  maj_le: "2026-10-30T10:00:00Z",
};

const initiative = {
  id: "ini-1",
  famille: "decision",
  type: "INITIATIVE",
  mode: "DECLARED",
  titre: "Déployer le contrôle asynchrone",
  donnees: { resume: "Déploiement progressif sur les trois flux de paiement." },
  version: 1,
  observe_le: "2026-10-29T11:00:00Z",
  maj_le: "2026-10-30T11:00:00Z",
};

const outcome = {
  id: "out-1",
  famille: "resultat_apprentissage",
  type: "OUTCOME",
  mode: "OBSERVED",
  titre: "Latence revenue sous la cible",
  donnees: {
    case_id: "case-paiement",
    twin_ids: ["app-paiement"],
    metrique: "p95",
    valeur_observee: "180 ms",
  },
  version: 3,
  observe_le: "2026-10-30T12:00:00Z",
  maj_le: "2026-10-30T12:00:00Z",
};

const learning = {
  id: "lea-1",
  famille: "resultat_apprentissage",
  type: "LEARNING",
  mode: "INFERRED",
  titre: "Les contrôles synchrones amplifient les incidents",
  donnees: { enonce: "Un contrôle synchrone sur un flux critique amplifie tout ralentissement." },
  version: 1,
  observe_le: "2026-10-30T13:00:00Z",
  maj_le: "2026-10-30T13:00:00Z",
};

const objets = [situation, investigation, decision, initiative, outcome, learning];

const synthese = {
  tenant: "local",
  total: 6,
  familles: {
    emergence: 1,
    investigation: 1,
    decision: 2,
    resultat_apprentissage: 2,
  },
  types: {
    SITUATION: 1,
    INVESTIGATION: 1,
    DECISION: 1,
    INITIATIVE: 1,
    OUTCOME: 1,
    LEARNING: 1,
  },
  modes: {
    OBSERVED: 2,
    DECLARED: 3,
    INFERRED: 1,
  },
};

function installerApi(options = {}) {
  const {
    liste = objets,
    comptes = synthese,
    details = {},
    objetsPourRequete,
    syntheseEnErreur = false,
  } = options;

  api.get.mockImplementation((url, config) => {
    if (url === "/boucle/objets") {
      const resultat = objetsPourRequete ? objetsPourRequete(liste, config?.params || {}) : liste;
      return Promise.resolve({ data: { tenant: "local", objets: resultat } });
    }
    if (url === "/boucle/synthese") {
      if (syntheseEnErreur) return Promise.reject(new Error("synthèse indisponible"));
      return Promise.resolve({ data: comptes });
    }
    const correspondance = url.match(/^\/boucle\/objets\/(.+)$/);
    if (correspondance) {
      const identifiant = decodeURIComponent(correspondance[1]);
      if (details[identifiant]) return Promise.resolve({ data: details[identifiant] });
      const objet = liste.find((element) => element.id === identifiant);
      return Promise.resolve({ data: { objet, chaine: [], historique: [] } });
    }
    return Promise.resolve({ data: {} });
  });
}

function monter() {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine };
}

async function rendre(racine) {
  await act(async () => { racine.render(<Boucle />); });
}

function saisir(input, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(input, valeur);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

beforeEach(() => {
  jest.clearAllMocks();
  mockNavigate.mockReset();
});

test("affiche les six étapes, la synthèse et filtre par recherche locale", async () => {
  let resoudreObjets;
  let resoudreSynthese;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") return new Promise((resolve) => { resoudreObjets = resolve; });
    if (url === "/boucle/synthese") return new Promise((resolve) => { resoudreSynthese = resolve; });
    return Promise.resolve({ data: {} });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(api.get).toHaveBeenCalledWith("/boucle/objets", { params: { limite: 500 } });
  expect(api.get).toHaveBeenCalledWith("/boucle/synthese");
  expect(hote.querySelector('[data-testid="boucle-page"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-titre"]').textContent).toContain("De la situation au learning");
  expect(hote.querySelector('[data-testid="boucle-chargement"]')).not.toBeNull();

  await act(async () => {
    resoudreObjets({ data: { tenant: "local", objets } });
    resoudreSynthese({ data: synthese });
  });

  expect(hote.querySelector('[data-testid="boucle-chargement"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-tenant"]').textContent).toContain("local");
  expect(hote.querySelector('[data-testid="boucle-total"]').textContent).toContain("6 objets");
  expect(hote.querySelector('[data-testid="boucle-synthese"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-compteur-situation"]').textContent).toBe("1");
  expect(hote.querySelector('[data-testid="boucle-compteur-learning"]').textContent).toBe("1");

  for (const type of ["situation", "investigation", "decision", "initiative", "outcome", "learning"]) {
    expect(hote.querySelector(`[data-testid="boucle-section-${type}"]`)).not.toBeNull();
  }
  expect(hote.querySelectorAll('[data-testid="boucle-objet"]')).toHaveLength(6);
  expect(hote.querySelector('[data-testid="boucle-section-situation"]').textContent).toContain("Latence des paiements");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-recherche"]'), "ralentissent");
  });

  expect(hote.querySelectorAll('[data-testid="boucle-objet"]')).toHaveLength(1);
  expect(hote.querySelector('[data-testid="boucle-section-situation"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-section-learning"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-nb-resultats"]').textContent).toContain("1 objet affiché");

  await act(async () => { racine.unmount(); });
});

test("les filtres famille, type et mode sont présents et le type interroge l'API", async () => {
  installerApi({
    objetsPourRequete: (liste, params) =>
      params.type ? liste.filter((objet) => objet.type === params.type) : liste,
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-filtre-famille"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-filtre-mode"]')).not.toBeNull();
  const filtreType = hote.querySelector('[data-testid="boucle-filtre-type"]');
  expect(filtreType).not.toBeNull();

  await act(async () => {
    filtreType.value = "DECISION";
    filtreType.dispatchEvent(new Event("change", { bubbles: true }));
  });

  expect(api.get).toHaveBeenCalledWith("/boucle/objets", {
    params: { limite: 500, type: "DECISION" },
  });
  expect(hote.querySelector('[data-testid="boucle-section-decision"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-section-situation"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-nb-resultats"]').textContent).toContain("1 objet affiché");

  await act(async () => {
    hote.querySelector('[data-testid="boucle-reinitialiser"]').click();
  });

  expect(api.get).toHaveBeenLastCalledWith("/boucle/objets", { params: { limite: 500 } });

  await act(async () => { racine.unmount(); });
});

test("ouvre le détail, montre la chaîne amont et les liens Travail et Atlas sans injecter de HTML", async () => {
  const outcomeAvecHtml = {
    ...outcome,
    titre: "Latence revenue <img src=x onerror=alert(1)>",
  };
  installerApi({
    details: {
      "out-1": {
        objet: outcomeAvecHtml,
        chaine: [situation, investigation, decision, initiative, outcomeAvecHtml],
        historique: [{ version: 1, maj_le: "2026-10-30T11:00:00Z" }],
      },
    },
  });

  const { hote, racine } = monter();
  await rendre(racine);

  await act(async () => {
    hote.querySelector('[data-objet-id="out-1"]').click();
  });

  expect(api.get).toHaveBeenCalledWith("/boucle/objets/out-1", { params: { historique: true } });
  const detail = hote.querySelector('[data-testid="boucle-detail"]');
  expect(detail).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent).toContain("<img src=x");
  expect(detail.querySelector("img")).toBeNull();
  expect(detail.querySelector('[data-testid="boucle-chaine"]')).not.toBeNull();
  expect(detail.querySelectorAll('[data-testid="boucle-chaine-etape"]')).toHaveLength(4);
  expect(detail.textContent).toContain("Latence des paiements");
  expect(detail.textContent).toContain("Comprendre le goulot de contrôle");
  expect(detail.querySelector('[data-testid="boucle-chaine-vide"]')).toBeNull();
  expect(detail.querySelector('[data-testid="boucle-historique"]')).not.toBeNull();

  await act(async () => {
    hote.querySelector('[data-testid="boucle-lien-travail"]').click();
  });
  expect(mockNavigate).toHaveBeenCalledWith("/travaux/case-paiement");

  await act(async () => {
    hote.querySelector('[data-testid="boucle-lien-atlas"]').click();
  });
  expect(mockNavigate).toHaveBeenCalledWith("/atlas?focus=app-paiement");

  await act(async () => {
    hote.querySelector('[data-testid="boucle-detail-fermer"]').click();
  });
  expect(hote.querySelector('[data-testid="boucle-detail"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("affiche l'erreur puis recharge les objets au clic sur Réessayer", async () => {
  let appelsObjets = 0;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") {
      appelsObjets += 1;
      if (appelsObjets === 1) {
        return Promise.reject({ response: { data: { detail: "Boucle indisponible" } } });
      }
      return Promise.resolve({ data: { tenant: "local", objets } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    return Promise.resolve({ data: {} });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-erreur"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-erreur"]').textContent).toContain("Boucle indisponible");

  await act(async () => {
    hote.querySelector('[data-testid="boucle-reessayer"]').click();
  });

  expect(hote.querySelector('[data-testid="boucle-erreur"]')).toBeNull();
  expect(hote.querySelectorAll('[data-testid="boucle-objet"]')).toHaveLength(6);
  expect(appelsObjets).toBe(2);

  await act(async () => { racine.unmount(); });
});

test("affiche l'état vide et garde les objets si la synthèse échoue", async () => {
  installerApi({
    liste: [],
    comptes: { total: 0 },
    syntheseEnErreur: true,
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-vide"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-vide"]').textContent).toContain("Aucun objet dans la boucle.");
  expect(hote.querySelector('[data-testid="boucle-synthese-erreur"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});
