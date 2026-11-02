import { act } from "react";
import { createRoot } from "react-dom/client";
import ArtefactPlanification, { artefactDepuisOutil } from "./ArtefactPlanification";

global.IS_REACT_ACT_ENVIRONMENT = true;

async function rendre(artefact) {
  const hote = document.createElement("div");
  document.body.appendChild(hote);
  const racine = createRoot(hote);
  await act(async () => { racine.render(<ArtefactPlanification artefact={artefact} />); });
  return { hote, racine };
}

test("un outil de capacité produit un artefact lisible", async () => {
  const outil = { nom: "planification_capacite", extrait: JSON.stringify({
    type: "planification.capacite", equipes: [{ equipe_id: "A", nom: "Équipe A",
      elements_actifs: 2, charges: [{ unite: "points", connue: 5, capacite: 8, marge: 3 }] }],
  }) };
  const artefact = artefactDepuisOutil(outil);
  const { hote, racine } = await rendre(artefact);
  expect(hote.querySelector('[data-testid="artefact-capacite"]')).not.toBeNull();
  expect(hote.textContent).toContain("Équipe A");
  expect(hote.textContent).toContain("marge 3");
  await act(async () => { racine.unmount(); });
});

test("une prévision affiche P50/P85/P95 et une abstention reste explicite", async () => {
  const { hote, racine } = await rendre({ type: "planification.prevision", prevision: {
    ok: true, p50: "2026-02-01", p85: "2026-02-08", p95: "2026-02-15", confiance: 0.8,
    methode: "velocite_sprint", hypotheses: ["capacité constante"],
  } });
  expect(hote.textContent).toContain("P50");
  expect(hote.textContent).toContain("2026-02-08");
  await act(async () => { racine.unmount(); });
  const vide = await rendre({ type: "planification.prevision", prevision: {
    ok: false, raison: "historique insuffisant",
  } });
  expect(vide.hote.textContent).toContain("historique insuffisant");
  await act(async () => { vide.racine.unmount(); });
});

test("le Canvas peut rendre un planning et un graphe de dépendances", async () => {
  const gantt = await rendre({ type: "planification.gantt", titre: "Planning", lignes: [
    { id: "a", label: "Lot A", debut: "2026-01-01", fin: "2026-01-10" },
    { id: "b", label: "Lot B", debut: "2026-01-05", fin: "2026-01-20" },
  ] });
  expect(gantt.hote.querySelector('[data-testid="artefact-gantt"]')).not.toBeNull();
  expect(gantt.hote.textContent).toContain("Lot A");
  await act(async () => { gantt.racine.unmount(); });

  const deps = await rendre({ type: "planification.dependances", titre: "Dépendances", noeuds: [
    { id: "a", label: "A" }, { id: "b", label: "B" },
  ], aretes: [{ source: "a", cible: "b", type: "bloque" }] });
  expect(deps.hote.querySelector('[data-testid="artefact-dependances"]')).not.toBeNull();
  expect(deps.hote.textContent).toContain("A");
  await act(async () => { deps.racine.unmount(); });
});
