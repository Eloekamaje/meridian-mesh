import { act } from "react";
import { createRoot } from "react-dom/client";
import ModaleTransition from "./ModaleTransition";
import { configurationAction } from "./boucleUi";

global.IS_REACT_ACT_ENVIRONMENT = true;

const actionInvestigation = configurationAction("ouvrir_investigation", { type: "SITUATION" });
const actionTrancher = configurationAction("trancher_decision", {
  type: "DECISION",
  donnees: { options: ["Automatiser", "Réorganiser"] },
});

function monter() {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  return { hote, racine };
}

function saisir(input, valeur) {
  const prototype = input.tagName === "TEXTAREA"
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, "value").set;
  setter.call(input, valeur);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

async function rendre(racine, props = {}) {
  await act(async () => {
    racine.render(
      <ModaleTransition
        action={actionInvestigation}
        onFermer={jest.fn()}
        onSoumettre={jest.fn()}
        {...props}
      />,
    );
  });
}

afterEach(() => {
  document.body.innerHTML = "";
});

test("affiche les champs libellés, place le focus et soumet les valeurs", async () => {
  const onSoumettre = jest.fn();
  const { hote, racine } = monter();
  await rendre(racine, { onSoumettre });

  expect(hote.querySelector('[data-testid="boucle-transition-modale"]')).not.toBeNull();
  expect(document.activeElement.tagName).toBe("INPUT");
  expect(document.activeElement.id).toBe("boucle-transition-titre");
  expect(document.activeElement.labels[0].textContent).toContain("Titre");
  expect(hote.querySelector('label[for="boucle-transition-question"]').textContent).toContain("Question");
  const ids = [...hote.querySelectorAll("[id]")].map((element) => element.id);
  expect(new Set(ids).size).toBe(ids.length);
  expect(hote.querySelector('[data-testid="boucle-transition-titre"]').getAttribute("aria-required")).toBe("true");

  await act(async () => {
    saisir(hote.querySelector('[data-testid="boucle-transition-titre"]'), "Comprendre");
    saisir(hote.querySelector('[data-testid="boucle-transition-question"]'), "Pourquoi ?");
  });
  await act(async () => { hote.querySelector('[data-testid="boucle-transition-enregistrer"]').click(); });

  expect(onSoumettre).toHaveBeenCalledWith({ titre: "Comprendre", question: "Pourquoi ?", perimetre: "" });

  await act(async () => { racine.unmount(); });
});

test("trancher rend un select avec les options proposées", async () => {
  const { hote, racine } = monter();
  await rendre(racine, { action: actionTrancher });

  const choix = hote.querySelector('[data-testid="boucle-transition-choix"]');
  expect(choix.tagName).toBe("SELECT");
  expect([...choix.options].map((option) => option.textContent))
    .toEqual(["Sélectionner…", "Automatiser", "Réorganiser"]);
  expect(hote.querySelector('[data-testid="boucle-transition-acteur"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("ferme par Échap, par le bouton et par le fond", async () => {
  const onFermer = jest.fn();
  const { hote, racine } = monter();
  await rendre(racine, { onFermer });

  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
  expect(onFermer).toHaveBeenCalledTimes(1);

  await act(async () => { hote.querySelector('[data-testid="boucle-transition-fermer"]').click(); });
  expect(onFermer).toHaveBeenCalledTimes(2);

  await act(async () => { hote.querySelector('[data-testid="boucle-transition-fond"]').click(); });
  expect(onFermer).toHaveBeenCalledTimes(3);

  await act(async () => { racine.unmount(); });
});

test("en cours d'enregistrement, désactive les champs et ignore la fermeture", async () => {
  const onFermer = jest.fn();
  const { hote, racine } = monter();
  await rendre(racine, { enCours: true, onFermer });

  expect(hote.querySelector('[data-testid="boucle-transition-titre"]').disabled).toBe(true);
  expect(hote.querySelector('[data-testid="boucle-transition-enregistrer"]').disabled).toBe(true);
  expect(hote.querySelector('[data-testid="boucle-transition-enregistrer"]').textContent).toContain("Enregistrement");
  expect(hote.querySelector('[data-testid="boucle-transition-fermer"]').disabled).toBe(false);

  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  });
  expect(onFermer).not.toHaveBeenCalled();

  await act(async () => { racine.unmount(); });
});

test("piège le focus entre le premier et le dernier contrôle", async () => {
  const { hote, racine } = monter();
  await rendre(racine);

  const premier = hote.querySelector('[data-testid="boucle-transition-fermer"]');
  const dernier = hote.querySelector('[data-testid="boucle-transition-enregistrer"]');

  await act(async () => { dernier.focus(); });
  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
  });
  expect(document.activeElement).toBe(premier);

  await act(async () => { premier.focus(); });
  await act(async () => {
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
  });
  expect(document.activeElement).toBe(dernier);

  await act(async () => { racine.unmount(); });
});

test("annonce l'erreur en role alert", async () => {
  const { hote, racine } = monter();
  await rendre(racine, { erreur: "Transition invalide." });

  const erreur = hote.querySelector('[data-testid="boucle-transition-erreur"]');
  expect(erreur.getAttribute("role")).toBe("alert");
  expect(erreur.textContent).toContain("Transition invalide.");

  await act(async () => { racine.unmount(); });
});
