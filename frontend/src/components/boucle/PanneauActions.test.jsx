import { act } from "react";
import { createRoot } from "react-dom/client";
import PanneauActions from "./PanneauActions";

global.IS_REACT_ACT_ENVIRONMENT = true;

function monter() {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  return { hote, racine };
}

async function rendre(racine, props) {
  await act(async () => {
    racine.render(<PanneauActions onAction={jest.fn()} {...props} />);
  });
}

afterEach(() => {
  document.body.innerHTML = "";
});

test("propose l'action correspondant à une situation", async () => {
  const onAction = jest.fn();
  const { hote, racine } = monter();
  await rendre(racine, {
    objet: { id: "sit-1", type: "SITUATION", titre: "Latence" },
    onAction,
  });

  expect(hote.querySelector('[data-testid="boucle-actions"]')).not.toBeNull();
  const bouton = hote.querySelector('[data-testid="boucle-action-investigation"]');
  expect(bouton).not.toBeNull();

  await act(async () => { bouton.click(); });
  expect(onAction).toHaveBeenCalledWith("ouvrir_investigation");

  await act(async () => { racine.unmount(); });
});

test("un learning sans action affiche la fin de chaîne", async () => {
  const { hote, racine } = monter();
  await rendre(racine, {
    objet: { id: "lea-1", type: "LEARNING", titre: "Leçon" },
  });

  expect(hote.querySelector('[data-testid="boucle-action-learning"]')).toBeNull();
  expect(hote.querySelector('[data-testid="boucle-actions-termine"]').textContent)
    .toContain("clôt la chaîne");

  await act(async () => { racine.unmount(); });
});

test("un objet sans transition disponible est signalé", async () => {
  const { hote, racine } = monter();
  await rendre(racine, {
    objet: { id: "dec-1", type: "DECISION", donnees: { statut: "REJECTED" } },
  });

  expect(hote.querySelector('[data-testid="boucle-actions-termine"]').textContent)
    .toContain("Aucune transition");

  await act(async () => { racine.unmount(); });
});

test("un objet créé peut être ouvert depuis le message de succès", async () => {
  const onOuvrir = jest.fn();
  const nouvelObjet = { id: "inv-2", type: "INVESTIGATION", titre: "Comprendre" };
  const { hote, racine } = monter();
  await rendre(racine, {
    objet: { id: "sit-1", type: "SITUATION", titre: "Latence" },
    succes: { objet: nouvelObjet },
    onOuvrir,
  });

  const succes = hote.querySelector('[data-testid="boucle-transition-succes"]');
  expect(succes.textContent).toContain("INVESTIGATION inv-2");
  expect(succes.textContent).toContain("Comprendre");
  const ouvrir = hote.querySelector('[data-testid="boucle-transition-succes-ouvrir"]');
  await act(async () => { ouvrir.click(); });
  expect(onOuvrir).toHaveBeenCalledWith(nouvelObjet);

  await act(async () => { racine.unmount(); });
});

test("une transition sur le même objet n'affiche pas de bouton d'ouverture", async () => {
  const { hote, racine } = monter();
  await rendre(racine, {
    objet: { id: "dec-1", type: "DECISION", donnees: { statut: "DECIDED" } },
    succes: { objet: { id: "dec-1", type: "DECISION", donnees: { statut: "DECIDED" } } },
  });

  expect(hote.querySelector('[data-testid="boucle-transition-succes"]').textContent)
    .toContain("Transition enregistrée");
  expect(hote.querySelector('[data-testid="boucle-transition-succes-ouvrir"]')).toBeNull();

  await act(async () => { racine.unmount(); });
});

test("pendant la vérification, les actions sont désactivées avec un message", async () => {
  const onAction = jest.fn();
  const { hote, racine } = monter();
  await rendre(racine, {
    objet: { id: "sit-1", type: "SITUATION", titre: "Latence" },
    onAction,
    verification: true,
  });

  expect(hote.querySelector('[data-testid="boucle-verification-source"]').textContent)
    .toContain("Vérification de la source");
  const bouton = hote.querySelector('[data-testid="boucle-action-investigation"]');
  expect(bouton.disabled).toBe(true);
  expect(bouton.getAttribute("aria-disabled")).toBe("true");
  await act(async () => { bouton.click(); });
  expect(onAction).not.toHaveBeenCalled();

  await act(async () => { racine.unmount(); });
});

test("une vérification indisponible affiche l'alerte et réactive les actions", async () => {
  const { hote, racine } = monter();
  await rendre(racine, {
    objet: { id: "sit-1", type: "SITUATION", titre: "Latence" },
    verificationErreur: "Vérification de la source indisponible — vérifiez manuellement.",
  });

  expect(hote.querySelector('[data-testid="boucle-verification-erreur"]').textContent)
    .toContain("Vérification de la source indisponible");
  expect(hote.querySelector('[data-testid="boucle-action-investigation"]').disabled).toBe(false);

  await act(async () => { racine.unmount(); });
});
