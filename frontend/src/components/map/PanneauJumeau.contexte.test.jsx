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
