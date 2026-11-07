import { act } from "react";
import { createRoot } from "react-dom/client";
import TraceCanonique from "./TraceCanonique";

global.IS_REACT_ACT_ENVIRONMENT = true;

function monter() {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  return { hote, racine };
}

afterEach(() => {
  document.body.innerHTML = "";
});

test("affiche l'identifiant, le statut et la chaîne canonique", async () => {
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(
      <TraceCanonique
        trace={{
          id: "dec-1",
          statut: "DECIDED",
          chaine: [
            { id: "sit-1", type: "SITUATION", titre: "Latence des paiements" },
            { id: "inv-1", type: "INVESTIGATION", titre: "Comprendre le goulot" },
          ],
        }}
      />,
    );
  });

  expect(hote.querySelector('[data-testid="travail-boucle-trace"]')).not.toBeNull();
  expect(hote.querySelector('[data-testid="travail-boucle-id"]').textContent).toBe("dec-1");
  expect(hote.querySelector('[data-testid="travail-boucle-statut"]').textContent).toBe("DECIDED");
  const etapes = hote.querySelectorAll('[data-testid="travail-boucle-etape"]');
  expect(etapes).toHaveLength(2);
  expect(etapes[0].textContent).toContain("Latence des paiements");
  expect(etapes[0].textContent).toContain("SITUATION");

  await act(async () => { racine.unmount(); });
});

test("rend une étape textuelle et signale une chaîne absente", async () => {
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(<TraceCanonique trace={{ id: "sit-1", statut: "", chaine: ["sit-1"] }} />);
  });

  expect(hote.querySelector('[data-testid="travail-boucle-statut"]')).toBeNull();
  expect(hote.querySelector('[data-testid="travail-boucle-etape"]').textContent).toContain("sit-1");

  await act(async () => {
    racine.render(<TraceCanonique trace={{ id: "sit-1", statut: "", chaine: [] }} />);
  });
  expect(hote.querySelector('[data-testid="travail-boucle-chaine-vide"]')).not.toBeNull();

  await act(async () => { racine.unmount(); });
});

test("ne rend rien sans trace", async () => {
  const { hote, racine } = monter();
  await act(async () => { racine.render(<TraceCanonique trace={null} />); });
  expect(hote.innerHTML).toBe("");

  await act(async () => { racine.unmount(); });
});

test("tolère une étape sans titre et lit le type porté par donnees", async () => {
  const { hote, racine } = monter();
  await act(async () => {
    racine.render(
      <TraceCanonique
        className="test-classe"
        trace={{
          id: "out-1",
          statut: "OBSERVED",
          chaine: [
            { id: "sans-titre" },
            { donnees: { type: "OUTCOME" }, titre: "Mesure" },
            null,
          ],
        }}
      />,
    );
  });

  const etapes = hote.querySelectorAll('[data-testid="travail-boucle-etape"]');
  expect(etapes).toHaveLength(3);
  expect(etapes[0].textContent).toContain("sans-titre");
  expect(etapes[1].textContent).toContain("OUTCOME");
  expect(etapes[2].textContent).toContain("Étape sans titre");
  expect(hote.querySelector('[data-testid="travail-boucle-trace"]').className).toContain("test-classe");

  await act(async () => { racine.unmount(); });
});
