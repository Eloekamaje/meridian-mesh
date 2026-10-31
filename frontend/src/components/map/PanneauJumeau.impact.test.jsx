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

function impact(mode, aval = [], amont = []) {
  return { data: { tenant: "banque", twin: "app-crm", profondeur: 2, mode, impact: { aval, amont } } };
}

function monter(entree = "/atlas") {
  const hote = document.createElement("div");
  const racine = createRoot(hote);
  return { hote, racine, entree };
}

async function rendre(montage, props = {}) {
  await act(async () => {
    montage.racine.render(
      <MemoryRouter initialEntries={[montage.entree]}>
        <PanneauJumeau
          jumeau={jumeau}
          voisins={[]}
          relationsRecentes={[]}
          onFermer={jest.fn()}
          {...props}
        />
      </MemoryRouter>
    );
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  localStorage.clear();
  api.post.mockResolvedValue({ data: {} });
});

test("affiche l'impact canonique du tenant stocké, borné à 6 ids par sens", async () => {
  localStorage.setItem("meridian.tenant", "banque");
  const aval = Array.from({ length: 8 }, (_, i) => ({
    id: `app-aval-${i}`, profondeur: 1, chemin: ["app-crm", `app-aval-${i}`], relation: `rel-${i}`, etat: "confirmee",
  }));
  const amont = [{ id: "app-amont-1", profondeur: 1, chemin: ["app-amont-1", "app-crm"], relation: "rel-amont", etat: "observee" }];
  api.get.mockResolvedValue(impact("neo4j", aval, amont));
  const onChoisirVoisin = jest.fn();
  const montage = monter();

  await rendre(montage, { onChoisirVoisin });

  expect(api.get).toHaveBeenCalledWith("/boucle/graphe/app-crm/impact?profondeur=2", {
    headers: { "X-Tenant": "banque" },
  });
  const section = montage.hote.querySelector('[data-testid="twin-impact-canonique"]');
  expect(section).not.toBeNull();
  expect(section.textContent).toContain("Impact canonique");
  expect(section.textContent).toContain("1 amont · 8 aval");
  expect(section.querySelectorAll('[data-testid^="twin-impact-aval-"]')).toHaveLength(6);
  expect(section.textContent).not.toContain("app-aval-6");
  expect(section.textContent).not.toContain("app-aval-7");

  await act(async () => { section.querySelector('[data-testid="twin-impact-aval-app-aval-0"]').click(); });
  expect(onChoisirVoisin).toHaveBeenCalledWith("app-aval-0");

  await act(async () => { montage.racine.unmount(); });
});

test("lit le tenant depuis l'URL et masque un impact en mode mémoire", async () => {
  api.get.mockResolvedValue(impact("memoire"));
  const montage = monter("/atlas?tenant=assurance");

  await rendre(montage);

  expect(api.get).toHaveBeenCalledWith("/boucle/graphe/app-crm/impact?profondeur=2", {
    headers: { "X-Tenant": "assurance" },
  });
  expect(montage.hote.querySelector('[data-testid="twin-impact-canonique"]')).toBeNull();

  await act(async () => { montage.racine.unmount(); });
});

test("n'interroge pas l'impact sans tenant", async () => {
  const montage = monter();

  await rendre(montage);

  expect(api.get).not.toHaveBeenCalled();
  expect(montage.hote.querySelector('[data-testid="twin-impact-canonique"]')).toBeNull();

  await act(async () => { montage.racine.unmount(); });
});
