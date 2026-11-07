import { act } from "react";
import { createRoot } from "react-dom/client";
import api from "@/lib/api";
import TravailDetail from "./TravailDetail";

jest.mock("react-router-dom", () => ({
  useParams: () => ({ cid: "case-1" }),
  useLocation: () => ({ state: {} }),
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), patch: jest.fn() },
}));

jest.mock("@/lib/perimetre", () => ({
  usePerimetre: () => ({ version: 0 }),
}));

jest.mock("@/lib/ecran", () => ({
  useEcran: () => "bureau",
}));

jest.mock("sonner", () => ({
  toast: { error: jest.fn() },
}));

jest.mock("./Travaux", () => ({
  TYPES_CASE: { demande: ["Demande", "#60A5FA"] },
}));

jest.mock("@/components/case/OngletTravail", () => {
  const React = require("react");
  return {
    __esModule: true,
    default: ({ entete }) => React.createElement("div", { "data-testid": "onglet-travail" }, entete),
  };
});

jest.mock("@/components/case/DecisionPassation", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/components/case/PartagerTravail", () => ({
  __esModule: true,
  default: () => null,
}));

jest.mock("@/components/EntetePage", () => {
  const React = require("react");
  return {
    BoutonRetour: ({ label, onClick }) => React.createElement("button", { onClick }, label),
  };
});

global.IS_REACT_ACT_ENVIRONMENT = true;

const cas = {
  id: "case-1",
  titre: "Travail lié à une décision",
  type: "demande",
  statut: "en_cours",
  sensibilite: "interne",
  conversation: [],
  jumeaux_participants: [],
  pieces: [],
  livrables: [],
  historique: [],
  peut_deposer: false,
};

function monter() {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  return { hote, racine };
}

async function rendre(racine) {
  await act(async () => { racine.render(<TravailDetail />); });
}

beforeEach(() => {
  jest.clearAllMocks();
  api.get.mockReset();
  api.patch.mockReset();
});

afterEach(() => {
  document.body.innerHTML = "";
});

test("construit la trace canonique depuis /boucle/objets quand le travail expose boucle_id", async () => {
  api.get.mockImplementation((url) => {
    if (url === "/cases/case-1") {
      return Promise.resolve({ data: { ...cas, boucle_id: "dec-1" } });
    }
    if (url === "/boucle/objets/dec-1") {
      return Promise.resolve({
        data: {
          objet: { id: "dec-1", type: "DECISION", statut: "DECIDED" },
          chaine: [
            { id: "sit-1", type: "SITUATION", titre: "Latence des paiements" },
            { id: "dec-1", type: "DECISION", titre: "Automatiser le contrôle", statut: "DECIDED" },
          ],
        },
      });
    }
    return Promise.resolve({ data: {} });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(api.get).toHaveBeenCalledWith("/boucle/objets/dec-1", { params: { historique: true } });
  const trace = hote.querySelector('[data-testid="travail-boucle-trace"]');
  expect(trace).not.toBeNull();
  expect(hote.querySelector('[data-testid="travail-boucle-id"]').textContent).toBe("dec-1");
  expect(hote.querySelector('[data-testid="travail-boucle-statut"]').textContent).toBe("DECIDED");
  const etapes = hote.querySelectorAll('[data-testid="travail-boucle-etape"]');
  expect(etapes).toHaveLength(2);
  expect(etapes[0].textContent).toContain("Latence des paiements");

  await act(async () => { racine.unmount(); });
});

test("utilise directement la trace cas.boucle sans appel supplémentaire", async () => {
  const chaine = [
    { id: "sit-1", type: "SITUATION", titre: "Latence" },
    { id: "dec-1", type: "DECISION", titre: "Automatiser", statut: "DECIDED" },
  ];
  api.get.mockImplementation((url) => {
    if (url === "/cases/case-1") {
      return Promise.resolve({
        data: {
          ...cas,
          boucle: { id: "dec-1", statut: "DECIDED", chaine },
        },
      });
    }
    return Promise.resolve({ data: {} });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(api.get).not.toHaveBeenCalledWith("/boucle/objets/dec-1", expect.anything());
  expect(hote.querySelector('[data-testid="travail-boucle-id"]').textContent).toBe("dec-1");
  expect(hote.querySelectorAll('[data-testid="travail-boucle-etape"]')).toHaveLength(2);

  await act(async () => { racine.unmount(); });
});

test("n'affiche aucune trace quand le travail legacy n'en porte pas", async () => {
  api.get.mockImplementation((url) => {
    if (url === "/cases/case-1") return Promise.resolve({ data: cas });
    return Promise.resolve({ data: {} });
  });

  const { hote, racine } = monter();
  await rendre(racine);

  expect(hote.querySelector('[data-testid="travail-boucle-trace"]')).toBeNull();
  expect(hote.querySelector('[data-testid="travail-titre"]').textContent).toContain("Travail lié");

  await act(async () => { racine.unmount(); });
});
