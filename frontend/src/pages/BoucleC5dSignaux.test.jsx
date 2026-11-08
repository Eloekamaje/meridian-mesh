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
  donnees: {
    resume: "Les paiements ralentissent depuis la modification de la règle R-118.",
    signal_ids: [],
  },
  version: 2,
  observe_le: "2026-10-29T08:00:00Z",
  maj_le: "2026-10-30T08:00:00Z",
};

const signalGlobal = {
  id: "signal-1",
  famille: "emergence",
  type: "SIGNAL",
  mode: "OBSERVED",
  titre: "Dépendance nouvelle",
  donnees: {
    libelle: "Dépendance nouvelle",
    source: "git://depot",
    type_signal: "CHANGEMENT",
    description: "Paquet non maintenu",
    statut: "DETECTED",
    intensite: 0.7,
    detecte_le: "2026-11-08T10:00:00+00:00",
    situation_ids: [],
    preuves: ["preuve-1"],
    confiance: 0.6,
    fingerprint: "abc123",
  },
  version: 1,
  observe_le: "2026-11-08T10:00:00Z",
  maj_le: "2026-11-08T10:00:00Z",
};

const signalLie = {
  ...signalGlobal,
  id: "signal-2",
  titre: "Latence en hausse",
  donnees: {
    ...signalGlobal.donnees,
    libelle: "Latence en hausse",
    source: "suivi-cartes",
    type_signal: "ANOMALIE",
    situation_ids: ["sit-1"],
  },
};

const signalMulti = {
  ...signalGlobal,
  id: "signal-3",
  titre: "Phénomène transversal",
  donnees: {
    ...signalGlobal.donnees,
    libelle: "Phénomène transversal",
    situation_ids: ["sit-1", "sit-2"],
  },
};

const synthese = {
  tenant: "local",
  total: 2,
  familles: { emergence: 2 },
  types: { SITUATION: 1, SIGNAL: 1 },
  modes: { OBSERVED: 2 },
};

function installerApi(options = {}) {
  const { liste = [situation], details = {} } = options;
  let courante = [...liste];
  let detailsCourants = { ...details };

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

async function ouvrirObjet(hote, identifiant) {
  await act(async () => {
    hote.querySelector(`[data-objet-id="${identifiant}"]`).click();
  });
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
});

afterEach(() => {
  document.body.innerHTML = "";
});

test("enregistre un signal global, le sélectionne et affiche une chaîne sans amont", async () => {
  const controleur = installerApi({ liste: [situation] });
  boucleApi.creerSignal.mockImplementation((corps) => {
    expect(corps).toEqual({
      libelle: "Dépendance nouvelle",
      source: "git://depot",
      type_signal: "CHANGEMENT",
      description: "Paquet non maintenu",
      intensite: 0.7,
      detecte_le: "2026-11-08T10:00:00+00:00",
      situation_ids: ["sit-1"],
      preuves: ["preuve-1"],
      confiance: 0.6,
    });
    controleur.ajouter(signalGlobal);
    return Promise.resolve({
      data: {
        objet: signalGlobal,
        chaine: [signalGlobal],
        historique: [],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-nouveau-signal"]')).not.toBeNull();
  await cliquerEnFocus(hote, "boucle-nouveau-signal");

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-libelle"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-source"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-type_signal"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-situation_ids"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-statut"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-mode"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-fingerprint"]')).toBeNull();

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-libelle"]'), "  Dépendance nouvelle  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-source"]'), "  git://depot  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-description"]'), "  Paquet non maintenu  ");
    saisir(hote.querySelector('[data-testid="boucle-transition-intensite"]'), "0,7");
    saisir(hote.querySelector('[data-testid="boucle-transition-detecte_le"]'), " 2026-11-08T10:00:00+00:00 ");
    saisir(hote.querySelector('[data-testid="boucle-transition-situation_ids"]'), " sit-1 ,, ");
    saisir(hote.querySelector('[data-testid="boucle-transition-preuves"]'), "preuve-1");
    saisir(hote.querySelector('[data-testid="boucle-transition-confiance"]'), "0,6");
  });
  await choisir(hote.querySelector('[data-testid="boucle-transition-type_signal"]'), "CHANGEMENT");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.creerSignal).toHaveBeenCalledTimes(1);
  expect(boucleApi.creerSignalSituation).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-objet-id="signal-1"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent)
    .toContain("Dépendance nouvelle");
  const precisions = hote.querySelector('[data-testid="boucle-precisions"]');
  expect(precisions.textContent).toContain("CHANGEMENT");
  expect(precisions.textContent).toContain("git://depot");

  await deplier(hote, "boucle-chaine-section");
  expect(hote.querySelectorAll('[data-testid="boucle-chaine-etape"]')).toHaveLength(0);
  expect(hote.querySelector('[data-testid="boucle-chaine-vide"]').textContent)
    .toContain("Aucune chaîne amont");

  await act(async () => { racine.unmount(); });
});

test("enregistre un signal depuis une situation, force la route et rafraîchit le parent", async () => {
  const controleur = installerApi({ liste: [situation] });
  const situationLiee = {
    ...situation,
    donnees: { ...situation.donnees, signal_ids: [signalLie.id] },
  };
  boucleApi.creerSignalSituation.mockImplementation((situationId, corps) => {
    expect(situationId).toBe("sit-1");
    expect(corps).toEqual({
      libelle: "Latence en hausse",
      source: "suivi-cartes",
      type_signal: "ANOMALIE",
    });
    controleur.ajouter(signalLie);
    controleur.majDetail("sit-1", {
      objet: situationLiee,
      chaine: [situationLiee],
      historique: [],
    });
    return Promise.resolve({
      data: {
        objet: signalLie,
        chaine: [situationLiee, signalLie],
        historique: [],
      },
    });
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "sit-1");

  expect(hote.querySelector('[data-testid="boucle-action-creer-signal"]')).not.toBeNull();
  await cliquerEnFocus(hote, "boucle-action-creer-signal");

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-situation_ids"]')).toBeNull();

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-libelle"]'), "Latence en hausse");
    saisir(hote.querySelector('[data-testid="boucle-transition-source"]'), "suivi-cartes");
  });
  await choisir(hote.querySelector('[data-testid="boucle-transition-type_signal"]'), "ANOMALIE");
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(boucleApi.creerSignalSituation).toHaveBeenCalledTimes(1);
  expect(boucleApi.creerSignal).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-detail-titre"]').textContent)
    .toContain("Latence en hausse");
  expect(api.get).toHaveBeenCalledWith(
    "/boucle/objets/sit-1",
    { params: { historique: true } },
  );

  await deplier(hote, "boucle-chaine-section");
  expect(hote.querySelectorAll('[data-testid="boucle-chaine-etape"]')).toHaveLength(1);
  expect(hote.querySelector('[data-testid="boucle-chaine"]').textContent)
    .toContain("Latence des paiements");

  await act(async () => { racine.unmount(); });
});

test("refuse un signal sans libellé puis sans source sans appeler le backend", async () => {
  installerApi({ liste: [situation] });
  const { hote, racine } = monter();
  await rendre(racine);
  await cliquer(hote, "boucle-nouveau-signal");

  await cliquer(hote, "boucle-transition-enregistrer");
  expect(boucleApi.creerSignal).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("libellé");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-libelle"]'), "Signal");
  });
  await cliquer(hote, "boucle-transition-enregistrer");
  expect(boucleApi.creerSignal).not.toHaveBeenCalled();
  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("source");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("garde la modale de signal sur un doublon 409 avec un message lisible", async () => {
  installerApi({ liste: [situation] });
  boucleApi.creerSignal.mockRejectedValue({
    response: {
      status: 409,
      data: { detail: "empreinte de Signal déjà connue : 'abc123'" },
    },
  });

  const { hote, racine } = monter();
  await rendre(racine);
  await cliquer(hote, "boucle-nouveau-signal");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-libelle"]'), "Dépendance nouvelle");
    saisir(hote.querySelector('[data-testid="boucle-transition-source"]'), "git://depot");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("Signal déjà enregistré");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-transition-libelle"]').value)
    .toBe("Dépendance nouvelle");

  await act(async () => { racine.unmount(); });
});

test("affiche le stade et le filtre SIGNAL dans la boucle", async () => {
  installerApi({ liste: [situation, signalGlobal] });
  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="boucle-compteur-signal"]').textContent).toBe("1");
  expect(hote.querySelector('[data-testid="boucle-section-signal"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="boucle-section-signal"]').textContent)
    .toContain("Dépendance nouvelle");

  await choisir(hote.querySelector('[data-testid="boucle-filtre-type"]'), "SIGNAL");

  expect(api.get).toHaveBeenLastCalledWith(
    "/boucle/objets",
    { params: { limite: 500, type: "SIGNAL" } },
  );
  expect(hote.querySelector('[data-testid="boucle-section-signal"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("un signal multi-situation s'affiche sans chaîne amont", async () => {
  installerApi({
    liste: [situation, signalMulti],
    details: {
      "signal-3": {
        objet: signalMulti,
        chaine: [signalMulti],
        historique: [],
      },
    },
  });
  const { hote, racine } = monter();
  await rendre(racine);
  await ouvrirObjet(hote, "signal-3");

  await deplier(hote, "boucle-chaine-section");
  expect(hote.querySelectorAll('[data-testid="boucle-chaine-etape"]')).toHaveLength(0);
  expect(hote.querySelector('[data-testid="boucle-chaine-vide"]').textContent)
    .toContain("Aucune chaîne amont");

  await act(async () => { racine.unmount(); });
});

test("un échec réseau de création de signal reste incertain et garde la modale", async () => {
  installerApi({ liste: [situation] });
  boucleApi.creerSignal.mockRejectedValue(new Error("Network Error"));

  const { hote, racine } = monter();
  await rendre(racine);
  await cliquer(hote, "boucle-nouveau-signal");
  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-libelle"]'), "Signal");
    saisir(hote.querySelector('[data-testid="boucle-transition-source"]'), "source");
  });
  await cliquer(hote, "boucle-transition-enregistrer");

  expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
    .toContain("Résultat incertain");
  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("affiche lisiblement les erreurs 404 et 503 d'une création de signal", async () => {
  for (const [statut, attendu] of [[404, "introuvable"], [503, "indisponible"]]) {
    installerApi({ liste: [situation] });
    boucleApi.creerSignal.mockRejectedValue({
      response: { status: statut, data: {} },
    });

    const { hote, racine } = monter();
    await rendre(racine);
    await cliquer(hote, "boucle-nouveau-signal");
    await act(async () => {
      saisir(hote.querySelector('[data-testid="boucle-transition-libelle"]'), "Signal");
      saisir(hote.querySelector('[data-testid="boucle-transition-source"]'), "source");
    });
    await cliquer(hote, "boucle-transition-enregistrer");

    expect(hote.querySelector('[data-testid="boucle-transition-erreur"]').textContent)
      .toContain(attendu);
    expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();

    await act(async () => { racine.unmount(); });
    document.body.innerHTML = "";
  }
});
