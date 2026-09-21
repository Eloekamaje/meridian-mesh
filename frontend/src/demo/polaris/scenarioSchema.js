// Validation des scénarios Polaris avant lecture (contrat §11.2 : erreur de validation
// avant lecture, diagnostic précis — jamais de découverte fabriquée).

export function validerScenario(scenario, fixtures) {
  const erreurs = [];
  const scenes = fixtures.scenes || {};
  const resultats = fixtures.resultats || {};
  const preuves = fixtures.preuves || {};
  const entites = new Set([
    ...(fixtures.entites || []).map((e) => e.id),
    ...(fixtures.applications || []).map((a) => a.id),
  ]);
  const relations = new Set((fixtures.relations || []).map((r) => r.id));

  (fixtures.relations || []).forEach((r) => {
    if (!entites.has(r.sourceId)) erreurs.push(`relation ${r.id} : source inconnue ${r.sourceId}`);
    if (!entites.has(r.targetId)) erreurs.push(`relation ${r.id} : cible inconnue ${r.targetId}`);
  });

  const etapes = new Set();
  (scenario.steps || []).forEach((step) => {
    etapes.add(step.id);
    (step.beats || []).forEach((beat, i) => {
      const rep = `${step.id}/beat ${i} (${beat.type})`;
      if (beat.type === "apply_scene" && !scenes[beat.sceneId]) erreurs.push(`${rep} : scène absente ${beat.sceneId}`);
      if (beat.type === "upsert_result" && !resultats[beat.resultId]) erreurs.push(`${rep} : résultat absent ${beat.resultId}`);
      if (beat.type === "upsert_result" && !["naissance", "diagnostic", "enrichissement", "final"].includes(beat.phase))
        erreurs.push(`${rep} : phase du résultat invalide (${beat.phase})`);
      (beat.evidenceIds || []).forEach((p) => {
        if (!preuves[p]) erreurs.push(`${rep} : preuve absente ${p}`);
      });
    });
  });

  Object.values(scenes).forEach((scene) => {
    const idsNoeuds = new Set(scene.noeuds.map((n) => n.id));
    scene.noeuds.forEach((n) => {
      if (!entites.has(n.id)) erreurs.push(`scène ${scene.id} : nœud sans entité ${n.id}`);
    });
    scene.liens.forEach((l) => {
      const rel = (fixtures.relations || []).find((r) => r.id === l.id);
      if (!rel) {
        erreurs.push(`scène ${scene.id} : lien sans relation ${l.id}`);
        return;
      }
      if (!idsNoeuds.has(rel.sourceId) || !idsNoeuds.has(rel.targetId)) {
        erreurs.push(`scène ${scene.id} : lien ${l.id} référence un nœud absent de la scène`);
      }
    });
  });

  if (scenario.discoveryStepId && !etapes.has(scenario.discoveryStepId)) {
    erreurs.push(`discoveryStepId inconnu : ${scenario.discoveryStepId}`);
  }
  return erreurs;
}
