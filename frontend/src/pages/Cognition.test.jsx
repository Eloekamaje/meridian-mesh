import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import Cognition from "./Cognition";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}));

global.IS_REACT_ACT_ENVIRONMENT = true;

const memoireUtilisateur = {
  id: "memoire-1",
  scope: "user",
  scope_id: "alice",
  classe: "preference",
  contenu: "Préfère les revues le mardi matin.",
  provenance: "conversation:42",
  consentement: true,
  consenti_le: "2026-10-01T09:00:00Z",
  confiance: 0.8,
  expire_le: "2026-11-01T09:00:00Z",
  cree_le: "2026-10-01T09:00:00Z",
};

const memoireTwin = {
  id: "memoire-2",
  scope: "twin",
  scope_id: "app-paiement",
  classe: "contexte",
  contenu: "Le twin paiement dépend du service de contrôle.",
  provenance: "atlas:app-paiement",
  consentement: false,
  confiance: 0.6,
  expire_le: "2026-11-02T09:00:00Z",
  cree_le: "2026-10-02T09:00:00Z",
};

const approbation = {
  id: "appro-1",
  run_id: "run-42",
  etape: "execution",
  outil: "deployer",
  cible: "service-paiement",
  operation: "redemarrer",
  demandeur: "flore",
  statut: "PROPOSE",
  cree_le: "2026-10-31T08:00:00Z",
  payload: { environnement: "recette" },
};

function installerApi({ approbations = [], memoires = [] } = {}) {
  api.get.mockImplementation((url, config) => {
    if (url === "/runs/approvals") return Promise.resolve({ data: { approbations } });
    if (url === "/boucle/memoire/durable/export") return Promise.resolve({ data: { memoires } });
    if (url === "/boucle/memoire/durable") {
      const params = config?.params || {};
      const filtrees = memoires.filter(
        (memoire) => (!params.scope || memoire.scope === params.scope)
          && (!params.classe || memoire.classe === params.classe),
      );
      return Promise.resolve({ data: { memoires: filtrees } });
    }
    if (url === "/boucle/runs/run-42/evaluation") {
      return Promise.resolve({
        data: {
          evaluation: {
            score: 0.8,
            raisons: ["autorité absente ou inconnue"],
            limites: ["coût non fourni"],
            verifications: { preuves: true, contexte: true, autorite: false, abstention: true, outils: true },
            metriques: { latence_ms: 120, cout: null },
          },
        },
      });
    }
    if (url === "/boucle/runs/run-42/replay") {
      return Promise.resolve({
        data: {
          replay: {
            reconstructible: true,
            etapes: 2,
            evenements: 3,
            empreintes: {
              contexte: { ok: true },
              raisonnement: { ok: true },
            },
            raisons: [],
            limites: ["aucune étape ni événement à rejouer"],
          },
        },
      });
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
  await act(async () => { racine.render(<Cognition />); });
  await act(async () => {});
}

function saisir(input, valeur) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(input, valeur);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function changer(select, valeur) {
  select.value = valeur;
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

beforeEach(() => {
  jest.clearAllMocks();
  api.post.mockResolvedValue({ data: {} });
  installerApi();
});

test("affiche un état vide propre quand la liste des approbations n'est pas exposée", async () => {
  api.get.mockImplementation((url) => {
    if (url === "/runs/approvals") {
      return Promise.reject({ response: { status: 404, data: { detail: "run introuvable" } } });
    }
    if (url === "/boucle/memoire/durable") return Promise.resolve({ data: { memoires: [] } });
    return Promise.resolve({ data: {} });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="cognition-page"]')).not.toBeNull();
  const vide = hote.querySelector('[data-testid="cognition-approbations-vide-texte"]');
  expect(vide).not.toBeNull();
  expect(vide.textContent).toContain("pas encore exposée");
  expect(hote.querySelector('[data-testid="cognition-approbations-erreur"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("liste une approbation, affiche son détail et enregistre la décision", async () => {
  installerApi({ approbations: [approbation] });
  let resoudreDecision;
  api.post.mockReturnValue(new Promise((resolve) => { resoudreDecision = resolve; }));

  const { hote, racine } = monter();
  await rendre(racine);

  await act(async () => { hote.querySelector('[data-testid="cognition-approbation-appro-1"]').click(); });
  expect(hote.querySelector('[data-testid="cognition-approbation-detail"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="cognition-approbation-detail"]').textContent).toContain("service-paiement");
  expect(hote.querySelector('[data-testid="cognition-approbation-detail"]').textContent).toContain("recette");

  const approuver = hote.querySelector('[data-testid="cognition-approbation-approuver"]');
  await act(async () => { approuver.click(); });
  expect(approuver.disabled).toBe(true);
  expect(api.post).toHaveBeenCalledWith("/runs/run-42/approval", { approuve: true });

  await act(async () => { resoudreDecision({ data: { run: { run_id: "run-42", etat: "EN_COURS" } } }); });
  expect(hote.querySelector('[data-testid="cognition-approbation-succes"]').textContent).toContain("approuvé");
  expect(hote.querySelector('[data-testid="cognition-approbation-appro-1"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("filtre la mémoire par portée et par classe et rend le consentement visible", async () => {
  installerApi({ memoires: [memoireUtilisateur, memoireTwin] });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="cognition-memoire-compteur"]').textContent).toContain("2 mémoire");
  expect(hote.querySelector('[data-testid="cognition-memoire-memoire-1"]').textContent).toContain("Consentement explicite");
  expect(hote.querySelector('[data-testid="cognition-memoire-memoire-2"]').textContent).toContain("Sans consentement");

  await act(async () => {
    changer(hote.querySelector('[data-testid="cognition-memoire-filtre-scope"]'), "user");
  });
  expect(api.get).toHaveBeenCalledWith("/boucle/memoire/durable", { params: { limite: 200, scope: "user" } });
  expect(hote.querySelector('[data-testid="cognition-memoire-compteur"]').textContent).toContain("1 mémoire");
  expect(hote.querySelector('[data-testid="cognition-memoire-memoire-1"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="cognition-memoire-memoire-2"]')).toBeNull();

  await act(async () => {
    changer(hote.querySelector('[data-testid="cognition-memoire-filtre-classe"]'), "preference");
  });
  expect(api.get).toHaveBeenCalledWith("/boucle/memoire/durable", {
    params: { limite: 200, scope: "user", classe: "preference" },
  });

  await act(async () => { racine.unmount(); });
});

test("exporte la mémoire durable et purge les entrées expirées après confirmation", async () => {
  installerApi({ memoires: [memoireUtilisateur] });
  api.post.mockResolvedValue({ data: { supprimees: 3 } });

  const { hote, racine } = monter();
  await rendre(racine);

  await act(async () => { hote.querySelector('[data-testid="cognition-memoire-export"]').click(); });
  expect(api.get).toHaveBeenCalledWith("/boucle/memoire/durable/export", { params: {} });
  expect(hote.querySelector('[data-testid="cognition-memoire-export-succes"]').textContent).toContain("1 mémoire");

  await act(async () => { hote.querySelector('[data-testid="cognition-memoire-purge"]').click(); });
  expect(hote.querySelector('[data-testid="cognition-memoire-purge-confirmer"]')).not.toBeNull();
  await act(async () => { hote.querySelector('[data-testid="cognition-memoire-purge-confirmer"]').click(); });

  expect(api.post).toHaveBeenCalledWith("/boucle/memoire/durable/purge");
  expect(hote.querySelector('[data-testid="cognition-memoire-purge-succes"]').textContent).toContain("3 entrée");

  await act(async () => { racine.unmount(); });
});

test("propose les doublons et conflits puis applique uniquement les groupes cochés", async () => {
  installerApi({ memoires: [memoireUtilisateur, memoireTwin] });

  const { hote, racine } = monter();
  await rendre(racine);

  await act(async () => {
    hote.querySelector('[data-testid="cognition-memoire-selectionner-memoire-1"]').click();
    hote.querySelector('[data-testid="cognition-memoire-selectionner-memoire-2"]').click();
  });
  expect(hote.querySelector('[data-testid="cognition-memoire-selection"]').textContent).toContain("2 sélectionnée");

  api.post.mockResolvedValueOnce({
    data: {
      proposition: {
        groupes: [{ keep_id: "memoire-1", remove_ids: ["memoire-2"], raison: "Doublon exact", confiance: 0.95, evidences: [] }],
        conflits: [{ ids: ["memoire-1", "memoire-2"], raison: "Valeurs divergentes", type: "valeur", gravite: "haute" }],
        limites: ["proposition seule : aucune fusion ni suppression automatique"],
      },
      ecritures: false,
    },
  });

  await act(async () => { hote.querySelector('[data-testid="cognition-consolidation-proposer"]').click(); });

  expect(api.post).toHaveBeenNthCalledWith(1, "/boucle/memoire/consolidation", {
    memoires: [memoireUtilisateur, memoireTwin],
    seuil_similarite: 0.9,
  });
  expect(hote.querySelector('[data-testid="cognition-groupe-memoire-1"]').textContent).toContain("Doublon exact");
  expect(hote.querySelector('[data-testid="cognition-conflit-0"]').textContent).toContain("Valeurs divergentes");
  expect(hote.querySelector('[data-testid="cognition-consolidation-appliquer"]').disabled).toBe(true);

  await act(async () => { hote.querySelector('[data-testid="cognition-groupe-appliquer-memoire-1"]').click(); });
  expect(hote.querySelector('[data-testid="cognition-consolidation-appliquer"]').disabled).toBe(false);

  api.post.mockResolvedValueOnce({
    data: {
      proposition: { groupes: [], conflits: [], limites: [] },
      plan: { groupes: [{ keep_id: "memoire-1" }], gardees: ["memoire-1"], archivees: ["memoire-2"], ignorees: [] },
      ecritures: true,
    },
  });

  await act(async () => { hote.querySelector('[data-testid="cognition-consolidation-appliquer"]').click(); });

  expect(api.post).toHaveBeenNthCalledWith(2, "/boucle/memoire/consolidation", {
    memoires: [memoireUtilisateur, memoireTwin],
    ids: ["memoire-1"],
    acteur: "interface-cognition",
  });
  expect(hote.querySelector('[data-testid="cognition-consolidation-plan"]').textContent).toContain("Archivées : 1");
  expect(hote.querySelector('[data-testid="cognition-consolidation-succes"]').textContent).toContain("1 groupe");

  await act(async () => { racine.unmount(); });
});

test("affiche l'évaluation et le rejeu sans prétendre relancer le modèle", async () => {
  installerApi();

  const { hote, racine } = monter();
  await rendre(racine);

  await act(async () => { saisir(hote.querySelector('[data-testid="cognition-run-id"]'), "run-42"); });
  await act(async () => { hote.querySelector('[data-testid="cognition-evaluation-lancer"]').click(); });
  await act(async () => {});

  expect(api.get).toHaveBeenCalledWith("/boucle/runs/run-42/evaluation");
  expect(api.get).toHaveBeenCalledWith("/boucle/runs/run-42/replay");
  expect(hote.querySelector('[data-testid="cognition-evaluation-score"]').textContent).toBe("80 %");
  expect(hote.querySelector('[data-testid="cognition-evaluation-resultat"]').textContent).toContain("Autorité bornée");
  expect(hote.querySelector('[data-testid="cognition-evaluation-resultat"]').textContent).toContain("autorité absente ou inconnue");
  expect(hote.querySelector('[data-testid="cognition-replay-limite"]').textContent).toContain("le modèle n'est jamais rappelé");
  expect(hote.querySelector('[data-testid="cognition-replay-resultat"]').textContent).toContain("Reconstructible");
  expect(hote.querySelector('[data-testid="cognition-replay-comptes"]').textContent).toContain("2 étape");

  await act(async () => { racine.unmount(); });
});
