import { act } from "react";
import { createRoot } from "react-dom/client";
import { TextDecoder, TextEncoder } from "util";
import api from "@/lib/api";

global.TextDecoder = TextDecoder;
global.TextEncoder = TextEncoder;
global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("@/lib/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() } }));
jest.mock("@/lib/atlasGraph", () => ({ idNumerique: (id) => String(id) }));
jest.mock("react-router-dom", () => require("react-router"), { virtual: true });

const { MemoryRouter } = require("react-router");
const PanneauJumeau = require("./PanneauJumeau").default;

const jumeau = {
  id: "app-crm",
  nom: "CRM",
  domaine: "Relation",
  mission: "Gère les clients",
  statut: "actif",
  fraicheur: "fraîche",
};

const faits = [
  { specialiste: "impact", type: "IMPACT", titre: "Impact de app-crm : 2 amont", preuves: ["p-1"], confiance: 0.8 },
  { specialiste: "preuve", type: "PREUVE", titre: "Claim de dépendance vérifié", preuves: ["p-2"], confiance: 0.7 },
  { specialiste: "decouverte", type: "MODELE", titre: "Interface observée", preuves: ["p-3"], confiance: 0.6 },
  { specialiste: "outcome", type: "QUESTION", titre: "Quatrième fait : baseline absente", preuves: ["p-4"], confiance: 0.5 },
];

const reponse = {
  data: {
    tenant: "banque",
    profil: { id: "architecte", libelle: "Architecte", autorite: "proposition" },
    contexte: {
      fingerprint: "abc123def4567890abc123def4567890",
      faits,
      preuves: ["p-1", "p-2", "p-3", "p-4", "p-5"],
      memoires: [{ id: "m-1" }, { id: "m-2" }],
      limites: ["contexte partiel", "preuves limitées au périmètre"],
    },
    raisonnement: {
      trace_id: "tr-abc123456789",
      etapes: [{ specialiste: "preuve" }, { specialiste: "impact" }],
      limites: ["contexte partiel"],
    },
    reponse: {
      autorite: "proposition",
      socle: { faits, preuves: ["p-1", "p-2", "p-3", "p-4", "p-5"], limites: ["limite socle"] },
      decision_support: { abstention: "signaux baseline absents" },
    },
  },
};

function monter(entree = "/atlas") {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine, entree };
}

async function rendre(montage) {
  await act(async () => {
    montage.racine.render(
      <MemoryRouter initialEntries={[montage.entree]}>
        <PanneauJumeau
          jumeau={jumeau}
          voisins={[]}
          relationsRecentes={[]}
          onFermer={jest.fn()}
        />
      </MemoryRouter>
    );
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  api.get.mockResolvedValue({ data: {} });
});

test("affiche le contexte cognitif du twin et permet de dépasser trois faits", async () => {
  localStorage.setItem("meridian.tenant", "banque");
  api.post.mockResolvedValue(reponse);
  const montage = monter();

  await rendre(montage);

  expect(api.post).toHaveBeenCalledWith(
    "/boucle/analyser",
    { question: "Explique-moi ce Twin et son contexte", surface: "twin", twin_id: "app-crm" },
    { headers: { "X-Tenant": "banque" } }
  );
  const section = montage.hote.querySelector('[data-testid="rubrique-contexte-cognitif"]');
  expect(section).not.toBeNull();
  expect(section.textContent).toContain("Contexte cognitif");

  await act(async () => { section.querySelector('[data-testid="rubrique-contexte-cognitif-bascule"]').click(); });

  expect(section.textContent).toContain("Architecte");
  expect(section.textContent).toContain("proposition");
  expect(section.textContent).toContain("abc123def456");
  expect(section.textContent).toContain("4 faits");
  expect(section.textContent).toContain("5 preuves");
  expect(section.textContent).toContain("2 mémoires");
  expect(section.textContent).toContain("Impact de app-crm : 2 amont");
  expect(section.textContent).not.toContain("Quatrième fait");
  expect(section.textContent).toContain("tr-abc123456789");
  expect(section.textContent).toContain("2 étapes");
  expect(section.textContent).toContain("signaux baseline absents");
  expect(section.textContent).toContain("contexte partiel");
  expect(section.textContent).toContain("limite socle");
  expect(section.textContent).toContain("aucune action automatique");

  await act(async () => { section.querySelector('[data-testid="contexte-cognitif-tout"]').click(); });
  expect(section.textContent).toContain("Quatrième fait : baseline absente");
  expect(section.textContent).toContain("Réduire");

  await act(async () => { montage.racine.unmount(); });
});

test("affiche le manifeste et les propositions de relation du Twin", async () => {
  localStorage.setItem("meridian.tenant", "banque");
  api.post.mockImplementation((url) => {
    if (String(url).endsWith("/enqueter")) {
      return Promise.resolve({ data: { investigation: {
        arret: "candidat trouvé", candidats: [{ id: "c2" }], budget_atteint: false,
      } } });
    }
    return Promise.resolve({ data: {} });
  });
  api.get.mockImplementation((url) => {
    if (url.includes("/manifeste")) {
      return Promise.resolve({ data: { manifeste: {
        status: "PROVISIONAL",
        exposures: [{ operation: "GET /articles", portee: "SERVICE" }],
        consumptions: [{ logical_ref: "GET /articles" }],
        unknowns: ["binding serveur absent"],
      } } });
    }
    if (url.includes("/relations")) {
      return Promise.resolve({ data: { propositions: [{
        id: "r1", consumer_id: "app-crm", provider_id: "app-pay", object: "GET /articles",
        state: "supposee", mode: "PROPOSED", confidence: 0.8, evidence_ids: ["claim:1"],
        consumer_owner: "Alice", provider_owner: "Bob", unknowns: [],
        transport: "HTTP", portee: "SERVICE", via: "gateway:articles",
      }] } });
    }
    if (url.includes("/resolutions")) {
      return Promise.resolve({ data: { resolutions: [{
        id: "case-1", reference: "${billing.base-url}",
        missing_evidence: "propriété absente", next_check: "manifeste de déploiement",
        owner: "Équipe plateforme",
        candidates: [{
          id: "c1", twin_id: "comptes", service: "comptes-api", confidence: 0.8,
          reason: "la route correspond au service", source: "AGENT", status: "proposed",
        }],
      }] } });
    }
    return Promise.resolve({ data: {} });
  });
  const montage = monter();

  await rendre(montage);
  await act(async () => {});

  const section = montage.hote.querySelector('[data-testid="rubrique-relations-cognitives"]');
  expect(section).not.toBeNull();
  await act(async () => { section.querySelector('[data-testid="rubrique-relations-cognitives-bascule"]').click(); });
  const manifeste = montage.hote.querySelector('[data-testid="twin-manifeste"]');
  expect(manifeste.textContent).toContain("provisoire");
  expect(manifeste.textContent).toContain("1 exposition");
  expect(manifeste.querySelector('[data-testid="twin-manifeste-portees"]').textContent).toContain("1 éligible");
  const relation = montage.hote.querySelector('[data-testid="relation-r1"]');
  expect(relation.textContent).toContain("app-crm → app-pay");
  expect(relation.textContent).toContain("proposée");
  expect(relation.textContent).toContain("HTTP · service");
  expect(relation.textContent).toContain("via gateway:articles");
  expect(relation.textContent).toContain("Alice");
  expect(relation.textContent).toContain("1 preuve");
  const enquete = montage.hote.querySelector('[data-testid="twin-resolutions"]');
  expect(enquete.textContent).toContain("Enquêtes ouvertes");
  expect(enquete.textContent).toContain("${billing.base-url}");
  expect(enquete.textContent).toContain("manifeste de déploiement");
  const candidat = montage.hote.querySelector('[data-testid="candidat-c1"]');
  expect(candidat.textContent).toContain("comptes");
  expect(candidat.textContent).toContain("la route correspond au service");

  const enqueter = [...enquete.querySelectorAll("button")].find((b) => b.textContent === "Enquêter");
  await act(async () => { enqueter.click(); });
  expect(api.post).toHaveBeenCalledWith(
    "/boucle/resolutions/case-1/enqueter",
    {},
    { headers: { "X-Tenant": "banque" } }
  );
  const resultatEnquete = montage.hote.querySelector('[data-testid="enquete-case-1"]');
  expect(resultatEnquete.textContent).toContain("candidat trouvé");
  expect(resultatEnquete.textContent).toContain("1 candidat");

  const accepter = [...candidat.querySelectorAll("button")].find((b) => b.textContent === "Accepter");
  await act(async () => { accepter.click(); });
  expect(api.post).toHaveBeenCalledWith(
    "/boucle/resolutions/case-1/revue",
    { candidate_id: "c1", decision: "accepter", motif: "" },
    { headers: { "X-Tenant": "banque" } }
  );

  await act(async () => { montage.racine.unmount(); });
});

test("lit le tenant depuis l'URL et n'affiche rien sans contexte", async () => {
  api.post.mockResolvedValue({ data: { profil: { libelle: "Architecte" } } });
  const montage = monter("/atlas?tenant=assurance");

  await rendre(montage);

  expect(api.post).toHaveBeenCalledWith(
    "/boucle/analyser",
    { question: "Explique-moi ce Twin et son contexte", surface: "twin", twin_id: "app-crm" },
    { headers: { "X-Tenant": "assurance" } }
  );
  expect(montage.hote.querySelector('[data-testid="twin-contexte-cognitif"]')).toBeNull();

  await act(async () => { montage.racine.unmount(); });
});

test("n'interroge pas le contexte cognitif sans tenant", async () => {
  const montage = monter();

  await rendre(montage);

  expect(api.post).not.toHaveBeenCalled();
  expect(montage.hote.querySelector('[data-testid="twin-contexte-cognitif"]')).toBeNull();

  await act(async () => { montage.racine.unmount(); });
});

test("ignore silencieusement une erreur du contexte cognitif", async () => {
  localStorage.setItem("meridian.tenant", "banque");
  api.post.mockRejectedValue(new Error("indisponible"));
  const montage = monter();

  await rendre(montage);

  expect(montage.hote.querySelector('[data-testid="twin-contexte-cognitif"]')).toBeNull();

  await act(async () => { montage.racine.unmount(); });
});
