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
  default: { get: jest.fn(), post: jest.fn() },
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
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  return { hote, racine };
}

async function rendre(racine) {
  await act(async () => { racine.render(<Boucle />); });
}

function saisir(input, valeur) {
  const prototype = input.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value").set;
  setter.call(input, valeur);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function deplier(hote, testid) {
  const bouton = hote.querySelector(`[data-testid="${testid}-bouton"]`);
  if (bouton && bouton.getAttribute("aria-expanded") !== "true") {
    await act(async () => { bouton.click(); });
  }
  return hote.querySelector(`[data-testid="${testid}-contenu"]`);
}

beforeEach(() => {
  jest.clearAllMocks();
  mockNavigate.mockReset();
  api.post.mockReset();
  api.post.mockResolvedValue({ data: {} });
});

afterEach(() => {
  document.body.innerHTML = "";
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
  await deplier(hote, "boucle-chaine-section");
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

test("crée un outcome, bloque les saisies invalides et recharge la liste", async () => {
  installerApi();
  api.post.mockResolvedValue({
    data: { outcome: { id: "out-2" }, learning: { id: "lea-2" } },
  });
  const appelsObjets = () => api.get.mock.calls.filter(([url]) => url === "/boucle/objets").length;

  const { hote, racine } = monter();
  await rendre(racine);
  const avant = appelsObjets();

  const enregistrer = () => hote.querySelector('[data-testid="boucle-outcome-enregistrer"]');
  const erreur = () => hote.querySelector('[data-testid="boucle-outcome-erreur"]');

  await act(async () => { enregistrer().click(); });
  expect(api.post).not.toHaveBeenCalled();
  expect(erreur().textContent).toContain("initiative");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-outcome-initiative"]'), "ini-1");
    saisir(hote.querySelector('[data-testid="boucle-outcome-metrique"]'), "p95");
    saisir(hote.querySelector('[data-testid="boucle-outcome-valeur"]'), "pas-un-nombre");
    saisir(hote.querySelector('[data-testid="boucle-outcome-enseignement"]'), "Le contrôle asynchrone réduit la latence.");
  });
  await act(async () => { enregistrer().click(); });
  expect(api.post).not.toHaveBeenCalled();
  expect(erreur().textContent).toContain("nombre");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-outcome-valeur"]'), "180");
    saisir(hote.querySelector('[data-testid="boucle-outcome-unite"]'), "ms");
    saisir(hote.querySelector('[data-testid="boucle-outcome-cible"]'), "200");
  });
  await act(async () => { enregistrer().click(); });

  expect(api.post).toHaveBeenCalledWith("/boucle/outcomes", {
    initiative_id: "ini-1",
    mesure: { metrique: "p95", valeur: 180, unite: "ms" },
    enseignement: "Le contrôle asynchrone réduit la latence.",
    cible: 200,
  });
  expect(hote.querySelector('[data-testid="boucle-outcome-succes"]').textContent).toContain("out-2");
  expect(hote.querySelector('[data-testid="boucle-outcome-succes"]').textContent).toContain("lea-2");
  expect(appelsObjets()).toBe(avant + 1);

  await act(async () => { racine.unmount(); });
});

test("montre les preuves, claims et outcomes exposés et ouvre un outcome lié", async () => {
  const outcomeLie = { ...outcome, id: "out-2", titre: "Outcome lié" };
  const outcomeAvecLiens = {
    ...outcome,
    donnees: {
      ...outcome.donnees,
      preuves: ["preuve-1", { id: "preuve-2", source: "suivi-cartes" }],
      claim_ids: ["claim-1"],
      outcome_ids: ["out-2"],
    },
  };
  installerApi({
    liste: [...objets, outcomeLie],
    details: {
      "out-1": { objet: outcomeAvecLiens, chaine: [], historique: [] },
    },
  });

  const { hote, racine } = monter();
  await rendre(racine);

  await act(async () => {
    hote.querySelector('[data-objet-id="out-1"]').click();
  });

  const boutonLiens = hote.querySelector('[data-testid="boucle-liens-bouton"]');
  expect(boutonLiens).not.toBeNull();
  expect(boutonLiens.getAttribute("aria-expanded")).toBe("false");
  expect(hote.querySelector('[data-testid="boucle-claims"]')).toBeNull();
  await deplier(hote, "boucle-liens");

  const liens = hote.querySelector('[data-testid="boucle-liens"]');
  expect(liens).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-preuves"]').textContent).toContain("preuve-1");
  expect(hote.querySelector('[data-testid="boucle-preuves"]').textContent).toContain("suivi-cartes");
  expect(hote.querySelector('[data-testid="boucle-claims"]').textContent).toContain("claim-1");
  expect(hote.querySelector('[data-testid="boucle-outcomes"]').textContent).toContain("out-2");
  expect(hote.querySelector('[data-testid="boucle-claim-claim-1-copier"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-preuve-0-copier"]')).not.toBeNull();

  const writeText = jest.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  await act(async () => {
    hote.querySelector('[data-testid="boucle-claim-claim-1-copier"]').click();
  });
  expect(writeText).toHaveBeenCalledWith("claim-1");

  await act(async () => {
    hote.querySelector('[data-testid="boucle-outcome-lien-out-2"]').click();
  });
  expect(api.get).toHaveBeenCalledWith("/boucle/objets/out-2", { params: { historique: true } });
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent).toContain("Outcome lié");

  await act(async () => { racine.unmount(); });
});

test("crée un twin non applicatif, valide les champs et recharge la liste", async () => {
  let twins = [];
  const objetsTwins = [];
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") return Promise.resolve({ data: { tenant: "local", objets } });
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins } });
    return Promise.resolve({ data: {} });
  });
  api.post.mockImplementation((url, corps) => {
    if (url !== "/boucle/twins") return Promise.resolve({ data: {} });
    const twin = { id: corps.id, type: corps.type, nom: corps.nom, domaine: corps.domaine || null };
    twins = [...twins, twin];
    objetsTwins.push(corps);
    return Promise.resolve({ data: { twin } });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  const appelsTwins = () => api.get.mock.calls.filter(([url]) => url === "/boucle/twins").length;
  const avant = appelsTwins();

  expect(api.get).toHaveBeenCalledWith("/boucle/twins", { params: { limite: 200 } });
  expect(hote.querySelector('[data-testid="boucle-twins-vide"]')).not.toBeNull();
  expect([...hote.querySelector('[data-testid="boucle-twin-type"]').options].map((option) => option.value))
    .toEqual(["PROCESS", "CAPABILITY", "JOURNEY", "ORGANIZATION", "PRODUCT", "DATA_DOMAIN"]);

  const enregistrer = () => hote.querySelector('[data-testid="boucle-twin-enregistrer"]');
  const erreur = () => hote.querySelector('[data-testid="boucle-twin-erreur"]');

  await act(async () => { enregistrer().click(); });
  expect(api.post).not.toHaveBeenCalled();
  expect(erreur().textContent).toContain("identifiant");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-twin-id"]'), "process-facturation");
  });
  await act(async () => { enregistrer().click(); });
  expect(api.post).not.toHaveBeenCalled();
  expect(erreur().textContent).toContain("nom");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-twin-nom"]'), "Facturation client");
    saisir(hote.querySelector('[data-testid="boucle-twin-mission"]'), "Émettre et recouvrer les factures.");
    saisir(hote.querySelector('[data-testid="boucle-twin-domaine"]'), "Finance");
  });
  await act(async () => { enregistrer().click(); });

  expect(api.post).toHaveBeenCalledTimes(1);
  expect(objetsTwins[0]).toEqual({
    id: "process-facturation",
    type: "PROCESS",
    nom: "Facturation client",
    equipe: "à confirmer",
    mission: "Émettre et recouvrer les factures.",
    domaine: "Finance",
  });
  expect(hote.querySelector('[data-testid="boucle-twin-succes"]').textContent).toContain("process-facturation");
  expect(appelsTwins()).toBe(avant + 1);
  expect(hote.querySelector('[data-testid="boucle-twin-process-facturation"]').textContent).toContain("Facturation client");

  await act(async () => { racine.unmount(); });
});

test("affiche l'erreur de l'API quand la création du twin échoue", async () => {
  installerApi();
  api.post.mockRejectedValue({ response: { data: { detail: "changement de type refusé" } } });

  const { hote, racine } = monter();
  await rendre(racine);

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-twin-id"]'), "cap-paiement");
    saisir(hote.querySelector('[data-testid="boucle-twin-nom"]'), "Capacité paiement");
  });
  await act(async () => { hote.querySelector('[data-testid="boucle-twin-enregistrer"]').click(); });

  expect(hote.querySelector('[data-testid="boucle-twin-erreur"]').textContent).toContain("changement de type refusé");
  expect(hote.querySelector('[data-testid="boucle-twin-succes"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});
