import { act } from "react";
import { createRoot } from "react-dom/client";
import api, { boucleApi } from "@/lib/api";
import Boucle from "./Boucle";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
  boucleApi: {
    ouvrirInvestigation: jest.fn(),
    proposerDecision: jest.fn(),
    trancherDecision: jest.fn(),
    lancerInitiative: jest.fn(),
    mesurerOutcome: jest.fn(),
    capitaliserLearningDepuisOutcome: jest.fn(),
    capitaliserLearningDepuisInvestigation: jest.fn(),
  },
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

const decisionProposee = {
  ...decision,
  id: "dec-prop",
  titre: "Faut-il automatiser le contrôle ?",
  donnees: {
    statut: "PROPOSED",
    options: ["Automatiser", "Réorganiser"],
    criteres: ["coût", "délai"],
  },
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
  let courante = liste;
  let detailsCourants = { ...details };

  api.get.mockImplementation((url, config) => {
    if (url === "/boucle/objets") {
      const resultat = objetsPourRequete ? objetsPourRequete(courante, config?.params || {}) : courante;
      return Promise.resolve({ data: { tenant: "local", objets: resultat } });
    }
    if (url === "/boucle/synthese") {
      if (syntheseEnErreur) return Promise.reject(new Error("synthèse indisponible"));
      return Promise.resolve({ data: comptes });
    }
    const correspondance = url.match(/^\/boucle\/objets\/(.+)$/);
    if (correspondance) {
      const identifiant = decodeURIComponent(correspondance[1]);
      if (detailsCourants[identifiant]) return Promise.resolve({ data: detailsCourants[identifiant] });
      const objet = courante.find((element) => element.id === identifiant);
      return Promise.resolve({ data: { objet, chaine: [], historique: [] } });
    }
    return Promise.resolve({ data: {} });
  });

  return {
    ajouter(objet) {
      if (!objet?.id) return;
      courante = [...courante.filter((element) => element.id !== objet.id), objet];
    },
    majDetail(identifiant, data) {
      detailsCourants = { ...detailsCourants, [identifiant]: data };
    },
    liste: () => courante,
  };
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
  Object.values(boucleApi).forEach((methode) => methode.mockReset());
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
    saisir(hote.querySelector('[data-testid="boucle-outcome-preuves"]'), "preuve-1, preuve-2");
  });
  await act(async () => { enregistrer().click(); });

  expect(api.post).toHaveBeenCalledWith("/boucle/outcomes", {
    initiative_id: "ini-1",
    mesure: { metrique: "p95", valeur: 180, unite: "ms" },
    enseignement: "Le contrôle asynchrone réduit la latence.",
    cible: 200,
    preuve_ids: ["preuve-1", "preuve-2"],
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

  const carte = hote.querySelector('[data-objet-id="out-1"]');
  await act(async () => { carte.focus(); carte.click(); });

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
  expect(document.activeElement).toBe(hote.querySelector('[data-testid="boucle-detail-fermer"]'));

  await cliquer(hote, "boucle-detail-fermer");
  expect(document.activeElement?.getAttribute("data-objet-id")).toBe("out-1");

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

async function ouvrirObjet(hote, identifiant) {
  await act(async () => {
    hote.querySelector(`[data-objet-id="${identifiant}"]`).click();
  });
}

async function fermerDetail(hote) {
  const bouton = hote.querySelector('[data-testid="boucle-detail-fermer"]');
  if (bouton) await act(async () => { bouton.click(); });
}

async function cliquer(hote, testid) {
  const element = hote.querySelector(`[data-testid="${testid}"]`);
  expect(element).not.toBeNull();
  await act(async () => { element.click(); });
}

async function cliquerEnFocus(hote, testid) {
  const element = hote.querySelector(`[data-testid="${testid}"]`);
  expect(element).not.toBeNull();
  await act(async () => { element.focus(); element.click(); });
}

async function choisir(select, valeur) {
  select.value = valeur;
  await act(async () => {
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

test("affiche le panneau d'actions selon le type et le statut de l'objet", async () => {
  installerApi({ liste: [...objets, decisionProposee] });

  const { hote, racine } = monter();
  await rendre(racine);

  await ouvrirObjet(hote, "sit-1");
  expect(hote.querySelector('[data-testid="boucle-actions"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-investigation"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-proposer-decision"]')).toBeNull();
  await fermerDetail(hote);

  await ouvrirObjet(hote, "inv-1");
  expect(hote.querySelector('[data-testid="boucle-action-proposer-decision"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-learning"]')).not.toBeNull();

  const investigationFermee = { ...investigation, id: "inv-close", donnees: { statut: "CLOSED" } };
  await fermerDetail(hote);
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") {
      return Promise.resolve({ data: { tenant: "local", objets: [...objets, decisionProposee, investigationFermee] } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    const correspondance = url.match(/^\/boucle\/objets\/(.+)$/);
    if (correspondance) {
      const identifiant = decodeURIComponent(correspondance[1]);
      const objet = [...objets, decisionProposee, investigationFermee].find((element) => element.id === identifiant);
      return Promise.resolve({ data: { objet, chaine: [], historique: [] } });
    }
    return Promise.resolve({ data: {} });
  });
  await act(async () => { hote.querySelector('[data-testid="boucle-actualiser"]').click(); });
  await ouvrirObjet(hote, "inv-close");
  expect(hote.querySelector('[data-testid="boucle-action-proposer-decision"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-learning"]')).not.toBeNull();

  await fermerDetail(hote);
  await ouvrirObjet(hote, "dec-prop");
  expect(hote.querySelector('[data-testid="boucle-action-trancher"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-initiative"]')).toBeNull();

  await fermerDetail(hote);
  await ouvrirObjet(hote, "dec-1");
  expect(hote.querySelector('[data-testid="boucle-action-initiative"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-trancher"]')).toBeNull();

  await fermerDetail(hote);
  await ouvrirObjet(hote, "ini-1");
  expect(hote.querySelector('[data-testid="boucle-action-outcome"]')).not.toBeNull();

  await fermerDetail(hote);
  await ouvrirObjet(hote, "out-1");
  expect(hote.querySelector('[data-testid="boucle-action-learning"]')).not.toBeNull();

  await fermerDetail(hote);
  await ouvrirObjet(hote, "lea-1");
  expect(hote.querySelector('[data-testid="boucle-action-learning"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-actions-termine"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("ouvre une investigation depuis une situation, valide le formulaire et actualise la boucle", async () => {
  const controleur = installerApi();
  const nouvelle = {
    id: "inv-2",
    famille: "investigation",
    type: "INVESTIGATION",
    mode: "DECLARED",
    titre: "Comprendre la latence",
    donnees: { question: "Pourquoi les paiements ralentissent ?", statut: "OPEN" },
    version: 1,
  };
  boucleApi.ouvrirInvestigation.mockImplementation(() => {
    controleur.ajouter(nouvelle);
    return Promise.resolve({ data: { objet: nouvelle, chaine: [situation, nouvelle] } });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  const carte = hote.querySelector('[data-objet-id="sit-1"]');
  await act(async () => { carte.focus(); carte.click(); });
  await cliquer(hote, "boucle-action-investigation");

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(document.activeElement?.id).toBe("boucle-transition-titre");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "  Comprendre la latence  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "  Pourquoi les paiements ralentissent ?  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-perimetre"]'), "paiements");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.ouvrirInvestigation).toHaveBeenCalledWith(
    "sit-1",
    {
      titre: "Comprendre la latence",
      question: "Pourquoi les paiements ralentissent ?",
      perimetre: "paiements",
    },
  );
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-succes"]').textContent).toContain("inv-2");
  expect(hote.querySelector('[data-objet-id="inv-2"]')).not.toBeNull();

  await cliquer(hote, "boucle-transition-succes-ouvrir");
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent).toContain("Comprendre la latence");
  await cliquer(hote, "boucle-detail-fermer");
  expect(document.activeElement?.getAttribute("data-objet-id")).toBe("sit-1");

  await act(async () => { racine.unmount(); });
});

test("propose une décision depuis une investigation", async () => {
  const controleur = installerApi();
  const nouvelle = {
    id: "dec-2",
    famille: "decision",
    type: "DECISION",
    mode: "DECLARED",
    titre: "Choisir le levier",
    donnees: { statut: "PROPOSED", options: ["Automatiser", "Réorganiser"] },
    version: 1,
  };
  boucleApi.proposerDecision.mockImplementation(() => {
    controleur.ajouter(nouvelle);
    return Promise.resolve({ data: { objet: nouvelle, chaine: [situation, investigation, nouvelle] } });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "inv-1");
  await cliquer(hote, "boucle-action-proposer-decision");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Choisir le levier");
    saisir(hote.querySelector('[data-testid="boucle-transition-options"]'), "Automatiser\nRéorganiser");
    saisir(hote.querySelector('[data-testid="boucle-transition-criteres"]'), "coût\ndélai");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.proposerDecision).toHaveBeenCalledWith(
    "inv-1",
    {
      titre: "Choisir le levier",
      options: ["Automatiser", "Réorganiser"],
      criteres: ["coût", "délai"],
    },
  );
  expect(hote.querySelector('[data-testid="boucle-transition-succes"]').textContent).toContain("dec-2");

  await act(async () => { racine.unmount(); });
});

test("tranche une décision proposée puis expose l'action initiative", async () => {
  installerApi({ liste: [...objets, decisionProposee] });
  const tranchee = {
    ...decisionProposee,
    donnees: {
      ...decisionProposee.donnees,
      statut: "DECIDED",
      acteur: "comité-cartes",
      choix: "Automatiser",
      rationale: "Réduire le délai",
    },
  };
  boucleApi.trancherDecision.mockResolvedValue({
    data: {
      objet: tranchee,
      chaine: [situation, investigation, tranchee],
      historique: [{ version: 1, maj_le: "2026-10-30T10:00:00Z" }],
    },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-prop");
  await cliquerEnFocus(hote, "boucle-action-trancher");

  const choix = hote.querySelector('[data-testid="boucle-transition-choix"]');
  expect(choix.tagName).toBe("SELECT");
  expect([...choix.options].map((option) => option.value)).toEqual(["", "Automatiser", "Réorganiser"]);
  expect(hote.querySelector('[data-testid="boucle-transition-acteur"]')).toBeNull();

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-motif"]'), "  Réduire le délai  ");
  });
  await choisir(choix, "Automatiser");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.trancherDecision).toHaveBeenCalledWith(
    "dec-prop",
    { choix: "Automatiser", motif: "Réduire le délai" },
  );
  expect(hote.querySelector('[data-testid="boucle-action-trancher"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-initiative"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-historique"]').textContent).toContain("Version 1");
  expect(document.activeElement).toBe(hote.querySelector('[data-testid="boucle-detail-fermer"]'));

  await act(async () => { racine.unmount(); });
});

test("affiche l'erreur 409 d'une transition refusée et garde la saisie", async () => {
  installerApi({ liste: [...objets, decisionProposee] });
  boucleApi.trancherDecision.mockRejectedValue({
    response: { status: 409, data: { detail: "décision déjà tranchée : transition refusée" } },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-prop");
  await cliquerEnFocus(hote, "boucle-action-trancher");

  await choisir(hote.querySelector('[data-testid="boucle-transition-choix"]'), "Automatiser");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("décision déjà tranchée");
  expect(hote.querySelector('[data-testid="boucle-transition-enregistrer"]').disabled).toBe(false);
  expect(hote.querySelector('[data-testid="boucle-transition-choix"]').value).toBe("Automatiser");

  await act(async () => { racine.unmount(); });
});

test("lance une initiative depuis une décision tranchée et rafraîchit la source", async () => {
  const controleur = installerApi({
    details: {
      "dec-1": {
        objet: decision,
        chaine: [situation, investigation, decision],
        historique: [{ version: 7, maj_le: "2026-10-30T10:00:00Z" }],
      },
    },
  });
  const nouvelle = {
    id: "ini-2",
    famille: "decision",
    type: "INITIATIVE",
    mode: "DECLARED",
    titre: "Déployer le contrôle asynchrone",
    donnees: { statut: "PLANNED" },
    version: 1,
  };
  const decisionSource = {
    ...decision,
    version: 8,
    donnees: { ...decision.donnees, initiative_id: "ini-2" },
  };
  boucleApi.lancerInitiative.mockImplementation(() => {
    controleur.ajouter(nouvelle);
    controleur.majDetail("dec-1", {
      objet: decisionSource,
      chaine: [situation, investigation, decisionSource],
      historique: [{ version: 8, maj_le: "2026-10-30T12:00:00Z" }],
    });
    return Promise.resolve({
      data: {
        objet: nouvelle,
        chaine: [situation, investigation, decisionSource, nouvelle],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-1");
  await cliquerEnFocus(hote, "boucle-action-initiative");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Déployer le contrôle asynchrone");
    saisir(hote.querySelector('[data-testid="boucle-transition-proprietaire"]'), "Alice");
    saisir(hote.querySelector('[data-testid="boucle-transition-outcome_attendu_ids"]'), "out-attendu");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.lancerInitiative).toHaveBeenCalledWith(
    "dec-1",
    {
      titre: "Déployer le contrôle asynchrone",
      proprietaire: "Alice",
      outcome_attendu_ids: ["out-attendu"],
    },
  );
  expect(hote.querySelector('[data-testid="boucle-action-initiative"]')).toBeNull();
  expect(hote.querySelector('[data-objet-id="ini-2"]')).not.toBeNull();
  await deplier(hote, "boucle-chaine-section");
  const chaine = hote.querySelector('[data-testid="boucle-chaine"]');
  expect(chaine.querySelectorAll('[data-testid="boucle-chaine-etape"]')).toHaveLength(2);
  expect(chaine.textContent).not.toContain("Déployer le contrôle asynchrone");
  expect(hote.querySelector('[data-testid="boucle-historique"]').textContent).toContain("Version 8");
  expect(hote.querySelector('[data-testid="boucle-version"]').textContent).toBe("8");
  expect(document.activeElement).toBe(hote.querySelector('[data-testid="boucle-detail-fermer"]'));

  await act(async () => { racine.unmount(); });
});

test("mesure un outcome depuis une initiative et rafraîchit la source", async () => {
  const controleur = installerApi({
    details: {
      "ini-1": {
        objet: initiative,
        chaine: [situation, investigation, decision, initiative],
        historique: [{ version: 4, maj_le: "2026-10-30T11:00:00Z" }],
      },
    },
  });
  const nouvelOutcome = {
    id: "out-2",
    famille: "resultat_apprentissage",
    type: "OUTCOME",
    mode: "OBSERVED",
    titre: "p95",
    donnees: { statut: "OBSERVED", metrique: "p95", valeur_observee: 180 },
    version: 1,
  };
  const initiativeSource = {
    ...initiative,
    version: 5,
    donnees: { ...initiative.donnees, outcome_ids: ["out-2"] },
  };
  boucleApi.mesurerOutcome.mockImplementation(() => {
    controleur.ajouter(nouvelOutcome);
    controleur.majDetail("ini-1", {
      objet: initiativeSource,
      chaine: [situation, investigation, decision, initiativeSource],
      historique: [{ version: 5, maj_le: "2026-10-30T13:00:00Z" }],
    });
    return Promise.resolve({
      data: {
        objet: nouvelOutcome,
        chaine: [situation, investigation, decision, initiativeSource, nouvelOutcome],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "ini-1");
  await cliquerEnFocus(hote, "boucle-action-outcome");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-metrique"]'), "p95");
    saisir(hote.querySelector('[data-testid="boucle-transition-valeur"]'), "180");
    saisir(hote.querySelector('[data-testid="boucle-transition-unite"]'), "ms");
    saisir(hote.querySelector('[data-testid="boucle-transition-cible"]'), "200");
    saisir(hote.querySelector('[data-testid="boucle-transition-periode"]'), "2026-10");
    saisir(hote.querySelector('[data-testid="boucle-transition-preuves"]'), "preuve-1, preuve-2");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.mesurerOutcome).toHaveBeenCalledWith(
    "ini-1",
    {
      mesure: { metrique: "p95", valeur: 180, unite: "ms" },
      valeur_attendue: 200,
      periode: "2026-10",
      preuves: ["preuve-1", "preuve-2"],
    },
  );
  await deplier(hote, "boucle-liens");
  expect(hote.querySelector('[data-testid="boucle-outcomes"]').textContent).toContain("out-2");
  await deplier(hote, "boucle-chaine-section");
  const chaine = hote.querySelector('[data-testid="boucle-chaine"]');
  expect(chaine.querySelectorAll('[data-testid="boucle-chaine-etape"]')).toHaveLength(3);
  expect(chaine.textContent).not.toContain("out-2");
  expect(hote.querySelector('[data-testid="boucle-historique"]').textContent).toContain("Version 5");
  expect(hote.querySelector('[data-testid="boucle-version"]').textContent).toBe("5");
  expect(document.activeElement).toBe(hote.querySelector('[data-testid="boucle-action-outcome"]'));

  await act(async () => { racine.unmount(); });
});

test("capitalise un learning depuis un outcome", async () => {
  const controleur = installerApi();
  const nouveauLearning = {
    id: "lea-2",
    famille: "resultat_apprentissage",
    type: "LEARNING",
    mode: "INFERRED",
    titre: "Un contrôle synchrone amplifie les incidents",
    donnees: { statut: "PROPOSED", enonce: "Un contrôle synchrone amplifie les incidents" },
    version: 1,
  };
  boucleApi.capitaliserLearningDepuisOutcome.mockImplementation(() => {
    controleur.ajouter(nouveauLearning);
    return Promise.resolve({ data: { objet: nouveauLearning, chaine: [situation, investigation, decision, initiative, outcome, nouveauLearning] } });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "out-1");
  await cliquer(hote, "boucle-action-learning");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-enonce"]'), "Un contrôle synchrone amplifie les incidents");
    saisir(hote.querySelector('[data-testid="boucle-transition-scope"]'), "paiements");
    saisir(hote.querySelector('[data-testid="boucle-transition-conditions_applicabilite"]'), "volume stable\ncharge nominale");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.capitaliserLearningDepuisOutcome).toHaveBeenCalledWith(
    "out-1",
    {
      enonce: "Un contrôle synchrone amplifie les incidents",
      scope: "paiements",
      conditions_applicabilite: ["volume stable", "charge nominale"],
    },
  );

  await act(async () => { racine.unmount(); });
});

async function echap() {
  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
}

test("capitalise un learning depuis une investigation", async () => {
  const controleur = installerApi();
  const nouveauLearning = {
    id: "lea-inv-2",
    famille: "resultat_apprentissage",
    type: "LEARNING",
    mode: "INFERRED",
    titre: "L'enquête elle-même est réutilisable",
    donnees: { statut: "PROPOSED", enonce: "L'enquête elle-même est réutilisable" },
    version: 1,
  };
  boucleApi.capitaliserLearningDepuisInvestigation.mockImplementation(() => {
    controleur.ajouter(nouveauLearning);
    return Promise.resolve({
      data: { objet: nouveauLearning, chaine: [situation, investigation, nouveauLearning] },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "inv-1");
  await cliquer(hote, "boucle-action-learning");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-enonce"]'), "L'enquête elle-même est réutilisable");
    saisir(hote.querySelector('[data-testid="boucle-transition-scope"]'), "paiements");
    saisir(hote.querySelector('[data-testid="boucle-transition-conditions_applicabilite"]'), "volume stable");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.capitaliserLearningDepuisInvestigation).toHaveBeenCalledWith(
    "inv-1",
    {
      enonce: "L'enquête elle-même est réutilisable",
      scope: "paiements",
      conditions_applicabilite: ["volume stable"],
    },
  );
  expect(hote.querySelector('[data-testid="boucle-transition-succes"]').textContent)
    .toContain("lea-inv-2");

  await act(async () => { racine.unmount(); });
});

test("Échap ferme la modale sans fermer le détail, et ne ferme rien pendant l'enregistrement", async () => {
  installerApi();
  let resoudre;
  boucleApi.ouvrirInvestigation.mockImplementation(() => new Promise((resolve) => { resoudre = resolve; }));

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "sit-1");
  await cliquer(hote, "boucle-action-investigation");

  await echap();
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail"]')).not.toBeNull();

  await cliquer(hote, "boucle-action-investigation");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Comprendre");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "Pourquoi ?");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  await echap();
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail"]')).not.toBeNull();

  await act(async () => {
    resoudre({
      data: {
        objet: { ...investigation, id: "inv-lent" },
        chaine: [situation, { ...investigation, id: "inv-lent" }],
      },
    });
  });
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail"]')).not.toBeNull();

  await echap();
  expect(hote.querySelector('[data-testid="boucle-detail"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("la garde anti-double-submit n'envoie qu'une transition", async () => {
  installerApi();
  let resoudre;
  boucleApi.ouvrirInvestigation.mockImplementation(() => new Promise((resolve) => { resoudre = resolve; }));

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "sit-1");
  await cliquer(hote, "boucle-action-investigation");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Comprendre");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "Pourquoi ?");
    const formulaire = hote.querySelector('[data-testid="boucle-transition-modale"] form');
    formulaire.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    formulaire.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });

  expect(boucleApi.ouvrirInvestigation).toHaveBeenCalledTimes(1);
  expect(boucleApi.ouvrirInvestigation.mock.calls[0]).toHaveLength(2);
  const croix = hote.querySelector('[data-testid="boucle-transition-fermer"]');
  expect(croix.disabled).toBe(true);
  await act(async () => { croix.click(); });
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail"]').getAttribute("aria-hidden")).toBe("true");
  expect(hote.querySelector('[data-testid="boucle-detail"]').hasAttribute("inert")).toBe(true);

  await act(async () => {
    resoudre({ data: { objet: { ...investigation, id: "inv-garde" }, chaine: [] } });
  });
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail"]').getAttribute("aria-hidden")).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail"]').hasAttribute("inert")).toBe(false);

  await act(async () => { racine.unmount(); });
});

test("après un 409, recharge le détail et propose la transition suivante", async () => {
  const tranchee = {
    ...decisionProposee,
    donnees: {
      ...decisionProposee.donnees,
      statut: "DECIDED",
      acteur: "comité-cartes",
      choix: "Automatiser",
    },
  };
  let appelsDetail = 0;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") {
      return Promise.resolve({ data: { tenant: "local", objets: [...objets, decisionProposee] } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    if (url === "/boucle/objets/dec-prop") {
      appelsDetail += 1;
      const objet = appelsDetail === 1 ? decisionProposee : tranchee;
      return Promise.resolve({
        data: { objet, chaine: [situation, investigation, objet], historique: [] },
      });
    }
    return Promise.resolve({ data: {} });
  });
  boucleApi.trancherDecision.mockRejectedValue({
    response: { status: 409, data: { detail: "décision déjà tranchée" } },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-prop");
  await cliquerEnFocus(hote, "boucle-action-trancher");
  await choisir(hote.querySelector('[data-testid="boucle-transition-choix"]'), "Automatiser");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("déjà tranchée");
  expect(appelsDetail).toBe(2);
  const appelsObjets = api.get.mock.calls.filter(([url]) => url === "/boucle/objets").length;
  expect(appelsObjets).toBeGreaterThan(1);

  await cliquer(hote, "boucle-transition-annuler");
  expect(hote.querySelector('[data-testid="boucle-action-initiative"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-trancher"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("un GET détail lent ne réécrase pas le résultat d'une transition", async () => {
  let resoudreDetail;
  let appelsDetail = 0;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") {
      return Promise.resolve({ data: { tenant: "local", objets } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    if (url === "/boucle/objets/sit-1") {
      appelsDetail += 1;
      if (appelsDetail === 1) {
        return new Promise((resolve) => { resoudreDetail = resolve; });
      }
      return Promise.resolve({
        data: { objet: situation, chaine: [situation], historique: [] },
      });
    }
    return Promise.resolve({ data: {} });
  });
  const nouvelle = {
    id: "inv-rapide",
    famille: "investigation",
    type: "INVESTIGATION",
    mode: "DECLARED",
    titre: "Investigation rapide",
    donnees: { statut: "OPEN" },
    version: 1,
  };
  boucleApi.ouvrirInvestigation.mockResolvedValue({
    data: { objet: nouvelle, chaine: [situation, nouvelle] },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "sit-1");
  expect(typeof resoudreDetail).toBe("function");
  await cliquer(hote, "boucle-action-investigation");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Investigation rapide");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "Pourquoi ?");
  });
  await cliquer(hote, "boucle-transition-enregistrer");
  expect(hote.querySelector('[data-testid="boucle-transition-succes"]').textContent)
    .toContain("inv-rapide");

  await act(async () => {
    resoudreDetail({
      data: {
        objet: { ...situation, titre: "Version périmée" },
        chaine: [],
        historique: [],
      },
    });
  });

  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent).not.toContain("Version périmée");
  expect(hote.querySelector('[data-testid="boucle-transition-succes"]').textContent)
    .toContain("inv-rapide");

  await act(async () => { racine.unmount(); });
});

test("le succès disparaît quand on change d'objet", async () => {
  const controleur = installerApi();
  const nouvelle = {
    id: "inv-succes",
    famille: "investigation",
    type: "INVESTIGATION",
    mode: "DECLARED",
    titre: "Investigation",
    donnees: { statut: "OPEN" },
    version: 1,
  };
  boucleApi.ouvrirInvestigation.mockImplementation(() => {
    controleur.ajouter(nouvelle);
    return Promise.resolve({ data: { objet: nouvelle, chaine: [situation, nouvelle] } });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "sit-1");
  await cliquer(hote, "boucle-action-investigation");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Investigation");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "Pourquoi ?");
  });
  await cliquer(hote, "boucle-transition-enregistrer");
  expect(hote.querySelector('[data-testid="boucle-transition-succes"]')).not.toBeNull();

  await fermerDetail(hote);
  await ouvrirObjet(hote, "inv-1");
  expect(hote.querySelector('[data-testid="boucle-transition-succes"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("le détail piège le focus, le place sur la fermeture et le restitue à la carte", async () => {
  installerApi();
  const { hote, racine } = monter();
  await rendre(racine);

  const carte = hote.querySelector('[data-objet-id="sit-1"]');
  await act(async () => { carte.focus(); carte.click(); });

  const fermer = hote.querySelector('[data-testid="boucle-detail-fermer"]');
  expect(document.activeElement).toBe(fermer);

  const panneau = hote.querySelector('[data-testid="boucle-detail"] [role="dialog"]');
  const focusables = [...panneau.querySelectorAll(
    'a[href], button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])',
  )];
  const dernier = focusables[focusables.length - 1];
  await act(async () => { dernier.focus(); });
  await act(async () => {
    panneau.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
  });
  expect(document.activeElement).toBe(fermer);

  await act(async () => { fermer.focus(); });
  await act(async () => {
    panneau.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
  });
  expect(document.activeElement).toBe(dernier);

  await echap();
  expect(hote.querySelector('[data-testid="boucle-detail"]')).toBeNull();
  expect(document.activeElement).toBe(carte);

  await act(async () => { racine.unmount(); });
});

test("après un 404, recharge le détail et affiche l'erreur de contexte", async () => {
  let appelsDetail = 0;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") {
      return Promise.resolve({ data: { tenant: "local", objets: [...objets, decisionProposee] } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    if (url === "/boucle/objets/dec-prop") {
      appelsDetail += 1;
      if (appelsDetail === 1) {
        return Promise.resolve({ data: { objet: decisionProposee, chaine: [], historique: [] } });
      }
      return Promise.reject({ response: { status: 404, data: { detail: "Objet introuvable" } } });
    }
    return Promise.resolve({ data: {} });
  });
  boucleApi.trancherDecision.mockRejectedValue({
    response: { status: 404, data: { detail: "Objet introuvable" } },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-prop");
  await cliquerEnFocus(hote, "boucle-action-trancher");
  await choisir(hote.querySelector('[data-testid="boucle-transition-choix"]'), "Automatiser");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(appelsDetail).toBe(2);
  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("Objet introuvable");

  await cliquer(hote, "boucle-transition-annuler");
  await deplier(hote, "boucle-chaine-section");
  expect(hote.querySelector('[data-testid="boucle-detail-erreur"]').textContent)
    .toContain("Objet introuvable");

  await act(async () => { racine.unmount(); });
});

test("un 422 pendant un GET détail lent recharge le panneau", async () => {
  let appelsDetail = 0;
  let resoudreLent;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") {
      return Promise.resolve({ data: { tenant: "local", objets } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    if (url === "/boucle/objets/sit-1") {
      appelsDetail += 1;
      if (appelsDetail === 1) {
        return new Promise((resolve) => { resoudreLent = resolve; });
      }
      return Promise.resolve({
        data: {
          objet: { ...situation, titre: "Source rechargée" },
          chaine: [],
          historique: [],
        },
      });
    }
    return Promise.resolve({ data: {} });
  });
  boucleApi.ouvrirInvestigation.mockRejectedValue({
    response: {
      status: 422,
      data: { detail: [{ loc: ["body", "titre"], msg: "Champ requis" }] },
    },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "sit-1");
  await cliquer(hote, "boucle-action-investigation");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Comprendre");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "Pourquoi ?");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("titre : Champ requis");
  expect(appelsDetail).toBe(2);
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent)
    .toContain("Source rechargée");

  await act(async () => {
    resoudreLent({
      data: { objet: { ...situation, titre: "Version périmée" }, chaine: [], historique: [] },
    });
  });
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent)
    .toContain("Source rechargée");

  await act(async () => { racine.unmount(); });
});

test("un timeout ambigu affiche un message et recharge détail et liste", async () => {
  installerApi();
  boucleApi.ouvrirInvestigation.mockRejectedValue(new Error("timeout of 20000ms exceeded"));
  const appelsDetail = () => api.get.mock.calls.filter(([url]) => url === "/boucle/objets/sit-1").length;
  const appelsObjets = () => api.get.mock.calls.filter(([url]) => url === "/boucle/objets").length;

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "sit-1");
  const avantDetail = appelsDetail();
  const avantObjets = appelsObjets();

  await cliquer(hote, "boucle-action-investigation");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Comprendre");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "Pourquoi ?");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("Résultat incertain");
  expect(appelsDetail()).toBe(avantDetail + 1);
  expect(appelsObjets()).toBeGreaterThan(avantObjets);
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("pendant le rechargement après 409, la croix ferme puis le verrou persiste", async () => {
  const tranchee = {
    ...decisionProposee,
    donnees: {
      ...decisionProposee.donnees,
      statut: "DECIDED",
      acteur: "comité-cartes",
      choix: "Automatiser",
    },
  };
  let appelsDetail = 0;
  let resoudreRechargement;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") {
      return Promise.resolve({ data: { tenant: "local", objets: [...objets, decisionProposee] } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    if (url === "/boucle/objets/dec-prop") {
      appelsDetail += 1;
      if (appelsDetail === 1) {
        return Promise.resolve({ data: { objet: decisionProposee, chaine: [], historique: [] } });
      }
      return new Promise((resolve) => { resoudreRechargement = resolve; });
    }
    return Promise.resolve({ data: {} });
  });
  boucleApi.trancherDecision.mockRejectedValue({
    response: { status: 409, data: { detail: "décision déjà tranchée" } },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-prop");
  await cliquerEnFocus(hote, "boucle-action-trancher");
  await choisir(hote.querySelector('[data-testid="boucle-transition-choix"]'), "Automatiser");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-enregistrer"]').textContent)
    .toContain("Vérification");
  const croix = hote.querySelector('[data-testid="boucle-transition-fermer"]');
  expect(croix.disabled).toBe(false);
  await act(async () => { croix.click(); });

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail"]')).not.toBeNull();
  expect(document.activeElement).toBe(hote.querySelector('[data-testid="boucle-detail-fermer"]'));
  expect(hote.querySelector('[data-testid="boucle-verification-source"]').textContent)
    .toContain("Vérification de la source");
  expect(hote.querySelector('[data-testid="boucle-action-trancher"]').disabled).toBe(true);
  expect(hote.querySelector('[data-testid="boucle-action-trancher"]').getAttribute("aria-disabled")).toBe("true");

  await cliquerEnFocus(hote, "boucle-action-trancher");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();

  await act(async () => {
    resoudreRechargement({
      data: {
        objet: tranchee,
        chaine: [situation, investigation, tranchee],
        historique: [],
      },
    });
  });

  expect(hote.querySelector('[data-testid="boucle-verification-source"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-action-trancher"]')).toBeNull();
  await cliquerEnFocus(hote, "boucle-action-initiative");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("pendant le rechargement après un succès sans chaîne source, le détail reste fermable", async () => {
  let appelsDetail = 0;
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") return Promise.resolve({ data: { tenant: "local", objets } });
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    if (url === "/boucle/objets/dec-1") {
      appelsDetail += 1;
      if (appelsDetail === 1) {
        return Promise.resolve({ data: { objet: decision, chaine: [], historique: [] } });
      }
      return new Promise(() => {});
    }
    return Promise.resolve({ data: {} });
  });
  const nouvelle = {
    id: "ini-sans-chaine",
    famille: "decision",
    type: "INITIATIVE",
    mode: "DECLARED",
    titre: "Initiative",
    donnees: { statut: "PLANNED" },
    version: 1,
  };
  boucleApi.lancerInitiative.mockResolvedValue({ data: { objet: nouvelle, chaine: [] } });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-1");
  await cliquerEnFocus(hote, "boucle-action-initiative");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Initiative");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  await cliquer(hote, "boucle-detail-fermer");
  expect(hote.querySelector('[data-testid="boucle-detail"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("un GET de vérification suspendu est abandonné et libère le verrou", async () => {
  jest.useFakeTimers();
  try {
    let appelsDetail = 0;
    api.get.mockImplementation((url, config) => {
      if (url === "/boucle/objets") {
        return Promise.resolve({ data: { tenant: "local", objets: [...objets, decisionProposee] } });
      }
      if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
      if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
      if (url === "/boucle/objets/dec-prop") {
        appelsDetail += 1;
        if (appelsDetail === 1) {
          return Promise.resolve({ data: { objet: decisionProposee, chaine: [], historique: [] } });
        }
        return new Promise((resolve, reject) => {
          const annuler = () => reject(Object.assign(new Error("aborted"), {
            name: "CanceledError",
            code: "ERR_CANCELED",
          }));
          if (config?.signal?.aborted) annuler();
          else config?.signal?.addEventListener("abort", annuler);
        });
      }
      return Promise.resolve({ data: {} });
    });
    boucleApi.trancherDecision.mockRejectedValue({
      response: { status: 409, data: { detail: "décision déjà tranchée" } },
    });

    const { hote, racine } = monter();
    await rendre(racine);
    await ouvrirObjet(hote, "dec-prop");
    await cliquerEnFocus(hote, "boucle-action-trancher");
    await choisir(hote.querySelector('[data-testid="boucle-transition-choix"]'), "Automatiser");
    await cliquer(hote, "boucle-transition-enregistrer");

    const croix = hote.querySelector('[data-testid="boucle-transition-fermer"]');
    await act(async () => { croix.click(); });
    expect(hote.querySelector('[data-testid="boucle-verification-source"]')).not.toBeNull();
    expect(hote.querySelector('[data-testid="boucle-action-trancher"]').disabled).toBe(true);

    await act(async () => {
      jest.advanceTimersByTime(10000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(hote.querySelector('[data-testid="boucle-verification-source"]')).toBeNull();
    expect(hote.querySelector('[data-testid="boucle-verification-erreur"]').textContent)
      .toContain("Vérification de la source indisponible");
    expect(hote.querySelector('[data-testid="boucle-action-trancher"]').disabled).toBe(false);
    expect(hote.querySelector('[data-testid="boucle-action-trancher"]').getAttribute("aria-disabled")).toBeNull();

    await cliquerEnFocus(hote, "boucle-action-trancher");
    expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

    await act(async () => { racine.unmount(); });
  } finally {
    jest.useRealTimers();
  }
});

test("un échec du GET de fond conserve la chaîne et le panneau source", async () => {
  let appelsDetail = 0;
  const decisionSource = {
    ...decision,
    version: 8,
    donnees: { ...decision.donnees, initiative_id: "ini-fond" },
  };
  api.get.mockImplementation((url) => {
    if (url === "/boucle/objets") return Promise.resolve({ data: { tenant: "local", objets } });
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    if (url === "/boucle/objets/dec-1") {
      appelsDetail += 1;
      if (appelsDetail === 1) {
        return Promise.resolve({
          data: {
            objet: decision,
            chaine: [situation, investigation, decision],
            historique: [{ version: 7, maj_le: "2026-10-30T10:00:00Z" }],
          },
        });
      }
      return Promise.reject(new Error("fond indisponible"));
    }
    return Promise.resolve({ data: {} });
  });
  boucleApi.lancerInitiative.mockResolvedValue({
    data: {
      objet: { id: "ini-fond", type: "INITIATIVE", titre: "Initiative", donnees: { statut: "PLANNED" } },
      chaine: [situation, investigation, decisionSource, { id: "ini-fond", type: "INITIATIVE", titre: "Initiative" }],
    },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "dec-1");
  await cliquerEnFocus(hote, "boucle-action-initiative");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Initiative");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-detail"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent).not.toBe("");
  expect(hote.querySelector('[data-testid="boucle-historique"]').textContent).toContain("Version 7");
  await deplier(hote, "boucle-chaine-section");
  expect(hote.querySelector('[data-testid="boucle-chaine"]').querySelectorAll('[data-testid="boucle-chaine-etape"]'))
    .toHaveLength(2);

  await act(async () => { racine.unmount(); });
});
