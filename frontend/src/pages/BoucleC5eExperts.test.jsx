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
    creerSituation: jest.fn(),
    creerScenario: jest.fn(),
    creerExpression: jest.fn(),
    creerOpportunite: jest.fn(),
    creerRisque: jest.fn(),
    creerHypothese: jest.fn(),
    creerSignal: jest.fn(),
    creerSignalSituation: jest.fn(),
    creerExpert: jest.fn(),
    listerExperts: jest.fn(),
    changerStatutExpert: jest.fn(),
    creerContributionInvestigation: jest.fn(),
    creerContributionHypothese: jest.fn(),
    listerContributions: jest.fn(),
    changerStatutContribution: jest.fn(),
    listerOpportunites: jest.fn(),
    listerRisques: jest.fn(),
    listerHypotheses: jest.fn(),
    listerSignaux: jest.fn(),
    changerStatutOpportunite: jest.fn(),
    changerStatutRisque: jest.fn(),
    changerStatutHypothese: jest.fn(),
    listerScenarios: jest.fn(),
    comparerScenarios: jest.fn(),
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
  donnees: { resume: "Les paiements ralentissent.", signal_ids: [] },
  version: 2,
  observe_le: "2026-10-29T08:00:00Z",
  maj_le: "2026-10-30T08:00:00Z",
};

const investigation = {
  id: "inv-1",
  famille: "investigation",
  type: "INVESTIGATION",
  mode: "DECLARED",
  titre: "Comprendre la latence",
  donnees: {
    question: "Pourquoi les paiements ralentissent-ils ?",
    situation_id: "sit-1",
    statut: "OPEN",
    expert_ids: [],
    hypothesis_ids: [],
    preuves: [],
  },
  version: 1,
};

const hypothese = {
  id: "hypothesis-1",
  famille: "investigation",
  type: "HYPOTHESIS",
  mode: "PROPOSED",
  titre: "Le contrôle synchrone bloque",
  donnees: {
    investigation_id: "inv-1",
    enonce: "Le contrôle synchrone bloque",
    statut: "OPEN",
    preuves: [],
  },
  version: 1,
};

const expert = {
  id: "expert-1",
  famille: "investigation",
  type: "EXPERT",
  mode: "DECLARED",
  titre: "Camille Martin",
  donnees: {
    nom: "Camille Martin",
    domaine: "Cartes bancaires",
    role: "Expert métier",
    methodes: ["Entretien"],
    responsabilites: ["Valider les règles de gestion"],
    perimetre: "Équipe cartes",
    sources_autorisees: ["Confluence"],
    outils_autorises: ["lecture"],
    limites: ["Pas d'accès aux données clients"],
    statut: "ACTIVE",
    confiance: 0.7,
  },
  version: 1,
};

const contribution = {
  id: "contribution-1",
  famille: "investigation",
  type: "EXPERT_CONTRIBUTION",
  mode: "DECLARED",
  titre: "La règle est contournée",
  donnees: {
    expert_id: "expert-1",
    investigation_id: "inv-1",
    hypothesis_id: null,
    contenu: "La règle est contournée par le canal agence",
    constats: ["La pièce est saisie après validation"],
    statut: "PROPOSED",
    preuves: [],
  },
  version: 1,
};

const contributionHypothese = {
  ...contribution,
  id: "contribution-2",
  titre: "Le contournement est confirmé",
  donnees: {
    ...contribution.donnees,
    hypothesis_id: "hypothesis-1",
    contenu: "Le contournement est confirmé",
  },
};

const synthese = {
  tenant: "local",
  total: 2,
  familles: { emergence: 1, investigation: 1 },
  types: { SITUATION: 1, INVESTIGATION: 1 },
  modes: { OBSERVED: 1, DECLARED: 1 },
};

function installerApi(options = {}) {
  const { liste = [situation], details = {} } = options;
  let courante = [...liste];
  let detailsCourants = { ...details };
  let experts = [];

  api.get.mockImplementation((url, config) => {
    if (url === "/boucle/objets") {
      const params = config?.params || {};
      const resultat = params.type
        ? courante.filter((objet) => objet.type === params.type)
        : courante;
      return Promise.resolve({ data: { tenant: "local", objets: resultat } });
    }
    if (url === "/boucle/synthese") return Promise.resolve({ data: synthese });
    if (url === "/boucle/twins") return Promise.resolve({ data: { twins: [] } });
    const correspondance = url.match(/^\/boucle\/objets\/(.+)$/);
    if (correspondance) {
      const identifiant = decodeURIComponent(correspondance[1]);
      if (detailsCourants[identifiant]) {
        return Promise.resolve({ data: detailsCourants[identifiant] });
      }
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
    remplacer(identifiant, objet) {
      courante = courante.map((element) => (
        element.id === identifiant ? objet : element));
    },
    majDetail(identifiant, data) {
      detailsCourants = { ...detailsCourants, [identifiant]: data };
    },
    expertsDisponibles(valeurs) {
      experts = valeurs;
    },
    experts: () => experts,
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

async function laisserPromesses() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
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

async function cliquer(hote, testid) {
  const element = hote.querySelector(`[data-testid="${testid}"]`);
  expect(element).not.toBeNull();
  await act(async () => { element.click(); });
}

async function ouvrirObjet(hote, identifiant) {
  await act(async () => {
    hote.querySelector(`[data-objet-id="${identifiant}"]`).click();
  });
  await laisserPromesses();
}

async function choisir(select, valeur) {
  select.value = valeur;
  await act(async () => {
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  mockNavigate.mockReset();
  api.post.mockReset();
  api.post.mockResolvedValue({ data: {} });
  Object.values(boucleApi).forEach((methode) => methode.mockReset());
  boucleApi.listerScenarios.mockResolvedValue({ data: { scenarios: [] } });
  boucleApi.listerExperts.mockResolvedValue({ data: { experts: [] } });
});

afterEach(() => {
  document.body.innerHTML = "";
});

test("inscrit un expert dans le registre puis le sélectionne sans chaîne amont", async () => {
  const controleur = installerApi({ liste: [situation] });
  boucleApi.creerExpert.mockImplementation((corps) => {
    expect(corps).toEqual({
      nom: "Camille Martin",
      domaine: "Cartes bancaires",
      role: "Expert métier",
      methodes: ["Entretien"],
      responsabilites: ["Valider les règles de gestion"],
      perimetre: "Équipe cartes",
      sources_autorisees: ["Confluence"],
      outils_autorises: ["lecture"],
      limites: ["Pas d'accès aux données clients"],
      preuves: ["doc://entretien"],
      confiance: 0.7,
    });
    controleur.ajouter(expert);
    return Promise.resolve({
      data: { objet: expert, chaine: [expert], historique: [] },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-nouveau-expert"]')).not.toBeNull();
  await cliquer(hote, "boucle-nouveau-expert");

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-nom"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-domaine"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-role"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-statut"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-mode"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-id"]')).toBeNull();

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-nom"]'), "  Camille Martin  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-domaine"]'), "  Cartes bancaires  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-role"]'), "  Expert métier  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-methodes"]'), "Entretien");
    saisir(
      hote.querySelector('[data-testid="boucle-transition-responsabilites"]'),
      "Valider les règles de gestion",
    );
    saisir(hote.querySelector('[data-testid="boucle-transition-perimetre"]'), "Équipe cartes");
    saisir(hote.querySelector('[data-testid="boucle-transition-sources_autorisees"]'), "Confluence");
    saisir(hote.querySelector('[data-testid="boucle-transition-outils_autorises"]'), "lecture");
    saisir(
      hote.querySelector('[data-testid="boucle-transition-limites"]'),
      "Pas d'accès aux données clients",
    );
    saisir(hote.querySelector('[data-testid="boucle-transition-preuves"]'), "doc://entretien");
    saisir(hote.querySelector('[data-testid="boucle-transition-confiance"]'), "0,7");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.creerExpert).toHaveBeenCalledTimes(1);
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-objet-id="expert-1"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent)
    .toContain("Camille Martin");
  const precisions = hote.querySelector('[data-testid="boucle-precisions"]');
  expect(precisions.textContent).toContain("Cartes bancaires");
  expect(precisions.textContent).toContain("Expert métier");

  await deplier(hote, "boucle-chaine-section");
  expect(hote.querySelectorAll('[data-testid="boucle-chaine-etape"]')).toHaveLength(0);
  expect(hote.querySelector('[data-testid="boucle-chaine-vide"]').textContent)
    .toContain("Aucune chaîne amont");

  await act(async () => { racine.unmount(); });
});

test("refuse un expert sans nom puis sans domaine sans appeler le backend", async () => {
  installerApi({ liste: [situation] });
  const { hote, racine } = monter();
  await rendre(racine);
  await cliquer(hote, "boucle-nouveau-expert");

  await cliquer(hote, "boucle-transition-enregistrer");
  expect(boucleApi.creerExpert).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("nom");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-nom"]'), "Camille Martin");
  });
  await cliquer(hote, "boucle-transition-enregistrer");
  expect(boucleApi.creerExpert).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("domaine");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("sollicite un expert depuis une investigation avec un select du registre", async () => {
  const controleur = installerApi({ liste: [situation, investigation] });
  controleur.expertsDisponibles([{ id: "expert-1", nom: "Camille Martin" }]);
  boucleApi.listerExperts.mockResolvedValue({ data: { experts: [expert] } });
  boucleApi.creerContributionInvestigation.mockImplementation((investigationId, corps) => {
    expect(investigationId).toBe("inv-1");
    expect(corps).toEqual({
      expert_id: "expert-1",
      contenu: "La règle est contournée par le canal agence",
      constats: ["La pièce est saisie après validation"],
      claim_ids_proposes: ["claim-3"],
      hypothesis_ids_soutenues: ["hypothesis-1"],
      hypothesis_ids_contestees: ["hypothesis-2"],
      inconnues: ["volume réel"],
      contribution_le: "2026-11-08T10:00:00+00:00",
      preuves: ["doc://entretien"],
      confiance: 0.7,
    });
    controleur.ajouter(contribution);
    controleur.majDetail("inv-1", {
      objet: { ...investigation, donnees: { ...investigation.donnees, expert_ids: ["expert-1"] } },
      chaine: [situation, investigation],
      historique: [],
    });
    controleur.majDetail("contribution-1", {
      objet: contribution,
      chaine: [situation, investigation, contribution],
      historique: [],
    });
    return Promise.resolve({
      data: {
        objet: contribution,
        chaine: [situation, investigation, contribution],
        historique: [],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "inv-1");

  expect(hote.querySelector('[data-testid="boucle-action-solliciter-expert"]')).not.toBeNull();
  await cliquer(hote, "boucle-action-solliciter-expert");
  await laisserPromesses();

  const selectExpert = hote.querySelector('[data-testid="boucle-transition-expert_id"]');
  expect(selectExpert).not.toBeNull();
  expect([...selectExpert.options].map((option) => option.value)).toContain("expert-1");
  await choisir(selectExpert, "expert-1");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-contenu"]'),
      "  La règle est contournée par le canal agence  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-constats"]'),
      "La pièce est saisie après validation");
    saisir(hote.querySelector('[data-testid="boucle-transition-claim_ids_proposes"]'), "claim-3");
    saisir(hote.querySelector('[data-testid="boucle-transition-hypothesis_ids_soutenues"]'),
      "hypothesis-1");
    saisir(hote.querySelector('[data-testid="boucle-transition-hypothesis_ids_contestees"]'),
      "hypothesis-2");
    saisir(hote.querySelector('[data-testid="boucle-transition-inconnues"]'), "volume réel");
    saisir(hote.querySelector('[data-testid="boucle-transition-contribution_le"]'),
      "2026-11-08T10:00:00+00:00");
    saisir(hote.querySelector('[data-testid="boucle-transition-preuves"]'), "doc://entretien");
    saisir(hote.querySelector('[data-testid="boucle-transition-confiance"]'), "0,7");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.creerContributionInvestigation).toHaveBeenCalledTimes(1);
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-objet-id="contribution-1"]')).not.toBeNull();

  await ouvrirObjet(hote, "contribution-1");
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent)
    .toContain("La règle est contournée");
  await deplier(hote, "boucle-chaine-section");
  expect(hote.querySelectorAll('[data-testid="boucle-chaine-etape"]'))
    .toHaveLength(2);

  await act(async () => { racine.unmount(); });
});

test("sollicite un expert depuis une hypothèse sans exposer les liens de la route", async () => {
  const controleur = installerApi({
    liste: [situation, investigation, hypothese],
  });
  boucleApi.listerExperts.mockResolvedValue({ data: { experts: [expert] } });
  boucleApi.creerContributionHypothese.mockImplementation((hypothesisId, corps) => {
    expect(hypothesisId).toBe("hypothesis-1");
    expect(corps).toEqual({
      expert_id: "expert-1",
      contenu: "Le contournement est confirmé",
      constats: ["Constat"],
      confiance: 0.6,
    });
    controleur.ajouter(contributionHypothese);
    return Promise.resolve({
      data: {
        objet: contributionHypothese,
        chaine: [situation, investigation, hypothese, contributionHypothese],
        historique: [],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "hypothesis-1");
  await cliquer(hote, "boucle-action-solliciter-expert");
  await laisserPromesses();

  expect(hote.querySelector('[data-testid="boucle-transition-hypothesis_id"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-investigation_id"]')).toBeNull();
  await choisir(hote.querySelector('[data-testid="boucle-transition-expert_id"]'), "expert-1");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-contenu"]'),
      "Le contournement est confirmé");
    saisir(hote.querySelector('[data-testid="boucle-transition-constats"]'), "Constat");
    saisir(hote.querySelector('[data-testid="boucle-transition-confiance"]'), "0,6");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.creerContributionHypothese).toHaveBeenCalledTimes(1);
  expect(boucleApi.creerContributionInvestigation).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-objet-id="contribution-2"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("affiche l'échec du registre des experts et permet de réessayer", async () => {
  installerApi({ liste: [situation, investigation] });
  boucleApi.listerExperts
    .mockRejectedValueOnce({ response: { status: 503, data: {} } })
    .mockResolvedValueOnce({ data: { experts: [expert] } });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "inv-1");
  await cliquer(hote, "boucle-action-solliciter-expert");
  await laisserPromesses();

  const alerte = hote.querySelector(
    '[data-testid="boucle-transition-erreur-chargement"]');
  expect(alerte).not.toBeNull();
  expect(alerte.getAttribute("role")).toBe("alert");
  expect(alerte.textContent).toContain("registre des experts");
  expect(hote.querySelector('[data-testid="boucle-transition-enregistrer"]').disabled)
    .toBe(true);

  await cliquer(hote, "boucle-transition-reessayer");
  await laisserPromesses();

  expect(hote.querySelector('[data-testid="boucle-transition-erreur-chargement"]'))
    .toBeNull();
  const selectExpert = hote.querySelector('[data-testid="boucle-transition-expert_id"]');
  expect([...selectExpert.options].map((option) => option.value)).toContain("expert-1");
  expect(hote.querySelector('[data-testid="boucle-transition-enregistrer"]').disabled)
    .toBe(false);

  await act(async () => { racine.unmount(); });
});

test("change le statut d'une contribution avec motif et preuves dans un dialogue accessible", async () => {
  const controleur = installerApi({ liste: [situation, investigation, contribution] });
  const acceptee = {
    ...contribution,
    donnees: { ...contribution.donnees, statut: "ACCEPTED", motif: "Relecture concordante" },
  };
  boucleApi.changerStatutContribution.mockImplementation((identifiant, corps) => {
    expect(identifiant).toBe("contribution-1");
    expect(corps).toEqual({
      vers: "ACCEPTED",
      motif: "Relecture concordante",
      preuves: ["preuve-1"],
    });
    controleur.remplacer("contribution-1", acceptee);
    return Promise.resolve({
      data: {
        objet: acceptee,
        chaine: [situation, investigation, acceptee],
        historique: [{ donnees: { statut: "PROPOSED" } }],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "contribution-1");

  await cliquer(hote, "boucle-action-statut-contribution");
  const modale = hote.querySelector('[data-testid="boucle-transition-modale"]');
  expect(modale.getAttribute("role")).toBe("dialog");
  expect(modale.getAttribute("aria-modal")).toBe("true");
  expect(hote.querySelector('[data-testid="boucle-contenu"]').getAttribute("inert"))
    .not.toBeNull();
  const select = hote.querySelector('[data-testid="boucle-transition-vers"]');
  expect([...select.options].map((option) => option.value))
    .toEqual(["", "ACCEPTED", "REJECTED", "ARCHIVED"]);
  expect(hote.querySelector('[data-testid="boucle-transition-statut"]')).toBeNull();

  await choisir(select, "ACCEPTED");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-motif"]'), "  Relecture concordante  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-preuves"]'), "preuve-1");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.changerStatutContribution).toHaveBeenCalledTimes(1);
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail-statut"]').textContent)
    .toContain("ACCEPTED");

  await act(async () => { racine.unmount(); });
});

test("ferme la modale de contribution avec Escape sans soumettre", async () => {
  installerApi({ liste: [situation, investigation, contribution] });
  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "contribution-1");
  await cliquer(hote, "boucle-action-statut-contribution");

  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", {
      key: "Escape", bubbles: true,
    }));
  });

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(boucleApi.changerStatutContribution).not.toHaveBeenCalled();

  await act(async () => { racine.unmount(); });
});

test("garde la modale de contribution sur un 409 avec un message lisible", async () => {
  installerApi({ liste: [situation, investigation, contribution] });
  boucleApi.changerStatutContribution.mockRejectedValue({
    response: { status: 409, data: { detail: "transition de contribution refusée" } },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "contribution-1");
  await cliquer(hote, "boucle-action-statut-contribution");
  await choisir(hote.querySelector('[data-testid="boucle-transition-vers"]'), "REJECTED");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("transition de contribution refusée");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("change le statut d'un expert avec motif et preuves dans un dialogue accessible", async () => {
  const controleur = installerApi({ liste: [situation, expert] });
  const inactif = {
    ...expert,
    donnees: {
      ...expert.donnees,
      statut: "INACTIVE",
      motif: "Congé longue durée",
      preuves: ["doc://rh"],
    },
  };
  boucleApi.changerStatutExpert.mockImplementation((identifiant, corps) => {
    expect(identifiant).toBe("expert-1");
    expect(corps).toEqual({
      vers: "INACTIVE",
      motif: "Congé longue durée",
      preuves: ["doc://rh"],
    });
    controleur.ajouter(inactif);
    return Promise.resolve({
      data: {
        objet: inactif,
        chaine: [inactif],
        historique: [{ donnees: { statut: "ACTIVE" } }],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "expert-1");

  expect(hote.querySelector('[data-testid="boucle-action-statut-expert"]')).not.toBeNull();
  await cliquer(hote, "boucle-action-statut-expert");
  const modale = hote.querySelector('[data-testid="boucle-transition-modale"]');
  expect(modale.getAttribute("role")).toBe("dialog");
  expect(modale.getAttribute("aria-modal")).toBe("true");
  expect(hote.querySelector('[data-testid="boucle-contenu"]').getAttribute("inert"))
    .not.toBeNull();
  const select = hote.querySelector('[data-testid="boucle-transition-vers"]');
  expect([...select.options].map((option) => option.value))
    .toEqual(["", "INACTIVE", "ARCHIVED"]);
  expect(hote.querySelector('[data-testid="boucle-transition-statut"]')).toBeNull();

  await choisir(select, "INACTIVE");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-motif"]'),
      "  Congé longue durée  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-preuves"]'), "doc://rh");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.changerStatutExpert).toHaveBeenCalledTimes(1);
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail-statut"]').textContent)
    .toContain("INACTIVE");

  await act(async () => { racine.unmount(); });
});

test("un expert archivé n'expose plus le changement de statut", async () => {
  installerApi({
    liste: [situation, {
      ...expert,
      donnees: { ...expert.donnees, statut: "ARCHIVED" },
    }],
  });
  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "expert-1");

  expect(hote.querySelector('[data-testid="boucle-action-statut-expert"]')).toBeNull();
  await act(async () => { racine.unmount(); });
});

test("garde la modale de statut expert sur un 409 avec un message lisible", async () => {
  installerApi({ liste: [situation, expert] });
  boucleApi.changerStatutExpert.mockRejectedValue({
    response: { status: 409, data: { detail: "transition d'expert refusée" } },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "expert-1");
  await cliquer(hote, "boucle-action-statut-expert");
  await choisir(hote.querySelector('[data-testid="boucle-transition-vers"]'), "ARCHIVED");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("transition d'expert refusée");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("affiche les stades et filtres EXPERT et EXPERT_CONTRIBUTION", async () => {
  installerApi({ liste: [situation, expert, contribution] });
  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-compteur-expert"]').textContent).toBe("1");
  expect(hote.querySelector('[data-testid="boucle-compteur-expert_contribution"]').textContent)
    .toBe("1");
  expect(hote.querySelector('[data-testid="boucle-section-expert"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-section-expert_contribution"]'))
    .not.toBeNull();
  const filtre = hote.querySelector('[data-testid="boucle-filtre-type"]');
  expect([...filtre.options].map((option) => option.value))
    .toEqual(expect.arrayContaining(["EXPERT", "EXPERT_CONTRIBUTION"]));

  await choisir(filtre, "EXPERT");
  expect(api.get).toHaveBeenLastCalledWith(
    "/boucle/objets",
    { params: { limite: 500, type: "EXPERT" } },
  );

  await act(async () => { racine.unmount(); });
});
