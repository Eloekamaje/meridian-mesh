export const COUCHES = [
  ["operationnelle", "Opérationnelle", "#3730A3"],
  ["connaissance", "Connaissance", "#0E7490"],
  ["mesh", "Mesh", "#6D28D9"],
];

export const NIVEAUX_ZOOM = { 1: "Entreprise", 2: "Domaine", 3: "Jumeau" };

export const styleParEtat = (r) => {
  switch (r.etat) {
    case "observee":
      return { stroke: "rgba(17,17,16,0.3)", strokeWidth: 1 };
    case "supposee":
      return { stroke: "#0E7490", strokeWidth: 1.3, strokeDasharray: "4 5", opacity: 0.8 };
    case "validation":
      return { stroke: "#6D28D9", strokeWidth: 1.8, strokeDasharray: "8 6" };
    case "contestee":
      return { stroke: "#B91C1C", strokeWidth: 1.8, strokeDasharray: "12 3 3 3" };
    case "obsolete":
      return { stroke: "rgba(17,17,16,0.4)", strokeWidth: 1, strokeDasharray: "2 6", opacity: 0.25 };
    default:
      return { stroke: r.active ? "#3730A3" : "rgba(17,17,16,0.45)", strokeWidth: 1.5, opacity: r.active ? 0.9 : 0.55 };
  }
};

export const makeEdge = (r, niveau) => ({
  id: r.id,
  source: r.source,
  target: r.cible,
  animated: !!r.active || r.etat === "validation",
  data: { etat: r.etat, restreinte: !!r.restreinte },
  style: r.restreinte ? { ...styleParEtat(r), opacity: 0.35, strokeDasharray: "3 5" } : styleParEtat(r),
  label:
    r.etat === "validation"
      ? `validation A2A${r.confiance ? ` — ${r.confiance} %` : ""}`
      : r.etat === "contestee"
        ? "contestée — contradiction"
        : niveau >= 3 && r.label
          ? r.label
          : undefined,
  labelStyle: { fill: r.etat === "validation" ? "#6D28D9" : r.etat === "contestee" ? "#B91C1C" : "rgba(17,17,16,0.6)", fontSize: 10, fontFamily: "IBM Plex Mono" },
  labelBgStyle: { fill: "rgba(255,255,255,0.92)" },
});

const NOUVELLE_STYLE = { stroke: "#0E7490", strokeWidth: 2.6, strokeDasharray: "2 4", opacity: 1 };

// Projection temporelle des relations : historique/replay masquent le futur,
// avant-après met en évidence ce qui est apparu depuis la date de référence.
export function appliquerTemps(edges, temps) {
  if (!temps?.mode) return edges;
  const { mode, dateTs, relTs } = temps;
  const tsDe = (id) => relTs?.[String(id).replace(/-porte$/, "")];
  if (mode === "avantapres") {
    return edges.map((e) => {
      const ts = tsDe(e.id);
      const nouvelle = ts && dateTs && ts > dateTs;
      if (nouvelle) {
        return {
          ...e,
          animated: true,
          data: { ...e.data, nouvelle: true },
          style: { ...NOUVELLE_STYLE },
          label: `${e.label ? `${e.label} · ` : ""}nouvelle`,
          labelStyle: { fill: "#0E7490", fontSize: 10, fontFamily: "IBM Plex Mono" },
          labelBgStyle: { fill: "rgba(255,255,255,0.92)" },
        };
      }
      return { ...e, animated: false, style: { ...e.style, opacity: 0.15 } };
    });
  }
  return edges.filter((e) => {
    const ts = tsDe(e.id);
    return !ts || !dateTs || ts <= dateTs;
  });
}

export function statsDuDomaine(mesh, situations, domDe, label) {
  if (!mesh || !label) return null;
  const twins = mesh.jumeaux.filter((j) => !j.anonyme && j.domaine === label);
  const couv = twins.length ? Math.round(twins.reduce((a, j) => a + (j.couverture || 0), 0) / twins.length) : 0;
  const ext = {};
  mesh.relations.forEach((r) => {
    const a = domDe[r.source] === label;
    const b = domDe[r.cible] === label;
    if (a === b) return;
    const autre = a ? domDe[r.cible] : domDe[r.source];
    if (!autre) return;
    ext[autre] = (ext[autre] || 0) + 1;
  });
  const sits = situations.filter((s) => (s.jumeaux || []).some((j) => domDe[j] === label));
  const equipes = [...new Set(twins.map((j) => j.proprietaire).filter(Boolean))];
  const reg = (mesh.regions || []).find((r) => r.label === label);
  return { twins, couv, ext, sits, equipes, reg };
}

export function construireGraphe({
  mesh, situation, focus, vueActive, perimetreTravail,
  jumeauFocus, domaineInterne, posOverrides, compteurs, halo, selection,
  zoomNiveau, relFocus, focusCarte, domDe, statsRegions, temps,
}) {
  if (!mesh) return { nodes: [], edges: [] };
  const implique = situation?.jumeaux || [];

  const dims = new Set();
  if (focus) {
    const deps = new Set([focus]);
    mesh.relations.forEach((r) => {
      if (r.source === focus && r.active) deps.add(r.cible);
      if (r.cible === focus && r.active) deps.add(r.source);
    });
    mesh.jumeaux.forEach((j) => { if (!deps.has(j.id)) dims.add(j.id); });
  } else if (situation && implique.length) {
    mesh.jumeaux.forEach((j) => { if (!implique.includes(j.id)) dims.add(j.id); });
  }
  if (vueActive?.type === "selection") {
    mesh.jumeaux.forEach((j) => { if (!j.anonyme && !vueActive.jumeaux.includes(j.id)) dims.add(j.id); });
  }
  if (vueActive?.type === "vigilance") {
    mesh.jumeaux.forEach((j) => { if ((j.couverture ?? 100) >= 70) dims.add(j.id); });
  }
  if (perimetreTravail) {
    mesh.jumeaux.forEach((j) => { if (!j.anonyme && j.domaine !== perimetreTravail) dims.add(j.id); });
  }

  // Focus jumeau : le jumeau au centre, ses voisins en portes périphériques
  if (jumeauFocus) {
    const jf = mesh.jumeaux.find((j) => j.id === jumeauFocus);
    if (!jf) return { nodes: [], edges: [] };
    const posF = posOverrides[jf.id] || jf.position;
    const cFx = posF.x + 95;
    const cFy = posF.y + 32;
    const relsV = (mesh.relations || []).filter((r) => r.source === jf.id || r.cible === jf.id);
    const voisins = [...new Set(relsV.map((r) => (r.source === jf.id ? r.cible : r.source)))]
      .map((id) => mesh.jumeaux.find((j) => j.id === id))
      .filter(Boolean);
    const rayF = Math.max(300, 150 + voisins.length * 26);
    const nsF = [{
      id: jf.id, type: "twin", position: posF, initialWidth: 190, initialHeight: 64,
      data: { jumeau: jf, focusCentral: true, evenements: compteurs[jf.id] || 0, halo: halo === jf.id },
      draggable: false, selectable: false, zIndex: 5,
    }];
    voisins.forEach((v, i) => {
      const ang = -Math.PI / 2 + (i * 2 * Math.PI) / voisins.length;
      const rel = relsV.find((r) => r.source === v.id || r.cible === v.id);
      nsF.push({
        id: `voisin-${v.id}`, type: "twin",
        position: { x: cFx + Math.cos(ang) * rayF - 95, y: cFy + Math.sin(ang) * rayF - 35 },
        initialWidth: 190, initialHeight: 70,
        data: { jumeau: v, voisinRel: rel },
        draggable: false, selectable: false, zIndex: 4,
      });
    });
    const esF = relsV.map((r) => {
      const e = makeEdge(r, 3);
      return {
        ...e,
        source: r.source === jf.id ? jf.id : `voisin-${r.source}`,
        target: r.cible === jf.id ? jf.id : `voisin-${r.cible}`,
        animated: true,
        style: { ...e.style, strokeWidth: 2.4, opacity: 1 },
      };
    });
    return { nodes: nsF, edges: appliquerTemps(esF, temps) };
  }

  // Vue interne d'un domaine : jumeaux du domaine + portes externes
  if (domaineInterne) {
    const internes = mesh.jumeaux.filter((j) => !j.anonyme && j.domaine === domaineInterne);
    const reg = (mesh.regions || []).find((r) => r.label === domaineInterne);
    const cx = reg ? reg.x + reg.w / 2 : 600;
    const cy = reg ? reg.y + reg.h / 2 : 350;
    const ray = reg ? Math.max(reg.w, reg.h) / 2 + 130 : 260;
    const extCount = {};
    mesh.relations.forEach((r) => {
      const a = domDe[r.source] === domaineInterne;
      const b = domDe[r.cible] === domaineInterne;
      if (a === b) return;
      const ext = a ? domDe[r.cible] : domDe[r.source];
      if (!ext) return;
      if (!extCount[ext]) extCount[ext] = { n: 0 };
      extCount[ext].n += 1;
    });
    const porteIds = {};
    const portes = Object.keys(extCount);
    let nsInt = reg
      ? [{ id: reg.id, type: "region", position: { x: reg.x, y: reg.y }, initialWidth: reg.w, initialHeight: reg.h, data: { ...reg, investigations: statsRegions[reg.label]?.investigations ?? 0, decouvertes: statsRegions[reg.label]?.decouvertes ?? 0, halo: false }, draggable: false, selectable: false, zIndex: -10 }]
      : [];
    portes.forEach((dom, i) => {
      const regExt = (mesh.regions || []).find((r) => r.label === dom);
      const ang = regExt
        ? Math.atan2(regExt.y + regExt.h / 2 - cy, regExt.x + regExt.w / 2 - cx)
        : (i / portes.length) * 2 * Math.PI;
      const pid = `porte-${dom}`;
      porteIds[dom] = pid;
      nsInt.push({
        id: pid,
        type: "twin",
        position: { x: cx + Math.cos(ang) * ray - 90, y: cy + Math.sin(ang) * ray },
        initialWidth: 190,
        initialHeight: 70,
        data: {
          jumeau: { id: pid, nom: `Vers ${dom} · ${extCount[dom].n} relation${extCount[dom].n > 1 ? "s" : ""}`, domaine: dom, porte: true, statut: "porte" },
          porte: dom,
          apercuPorte: {
            domaine: dom,
            domaineFocus: domaineInterne,
            jumeaux: mesh.jumeaux.filter((t) => !t.anonyme && t.domaine === dom).length,
            restreint: mesh.jumeaux.filter((t) => !t.anonyme && t.domaine === dom).length === 0,
            relations: extCount[dom].n,
            decouvertes: statsRegions[dom]?.decouvertes ?? 0,
          },
        },
        draggable: false,
        selectable: false,
      });
    });
    nsInt = nsInt.concat(
      internes.map((j) => ({
        id: j.id,
        type: "twin",
        position: posOverrides[j.id] || j.position,
        initialWidth: 190,
        initialHeight: 64,
        data: { jumeau: j, dim: false, halo: halo === j.id, evenements: compteurs[j.id] || 0, etape: null },
        selected: selection.includes(j.id),
      }))
    );
    const esInt = [];
    mesh.relations.forEach((r) => {
      const a = domDe[r.source] === domaineInterne;
      const b = domDe[r.cible] === domaineInterne;
      if (a && b) {
        esInt.push(makeEdge(r, zoomNiveau));
      } else if (a !== b) {
        const ext = a ? domDe[r.cible] : domDe[r.source];
        const pid = porteIds[ext];
        if (!pid) return;
        const e = makeEdge({ ...r, id: `${r.id}-porte`, source: a ? r.source : r.cible, cible: pid }, zoomNiveau);
        esInt.push(e);
      }
    });
    return { nodes: nsInt, edges: appliquerTemps(esInt, temps) };
  }

  // Focus contextuel : sélection → voisins éclairés, reste translucide
  if (selection.length > 0 && !focus) {
    const voisins = new Set(selection);
    mesh.relations.forEach((r) => {
      if (selection.includes(r.source)) voisins.add(r.cible);
      if (selection.includes(r.cible)) voisins.add(r.source);
    });
    mesh.jumeaux.forEach((j) => { if (!voisins.has(j.id)) dims.add(j.id); });
  }

  let ns = (mesh.regions || []).map((r) => ({
    id: r.id, type: "region", position: { x: r.x, y: r.y },
    initialWidth: r.w,
    initialHeight: r.h,
    data: { ...r, investigations: statsRegions[r.label]?.investigations ?? 0, decouvertes: statsRegions[r.label]?.decouvertes ?? 0, halo: !!halo && domDe[halo] === r.label },
    draggable: false, selectable: false, zIndex: -10,
  }));

  const twins = mesh.jumeaux;
  const entreprise = zoomNiveau === 1;

  ns = ns.concat(
    twins.map((j) => {
      const position = posOverrides[j.id] || j.position;
      return {
        id: j.id,
        type: "twin",
        position,
        initialWidth: 190,
        initialHeight: 64,
        hidden: entreprise && !j.anonyme ? true : entreprise,
        data: { jumeau: j, dim: dims.has(j.id), halo: halo === j.id, evenements: compteurs[j.id] || 0, etape: null },
        selected: selection.includes(j.id),
      };
    })
  );

  let es = [];
  if (entreprise) {
    // Zoom Entreprise : corridors agrégés inter-domaines
    const regParDom = {};
    (mesh.regions || []).forEach((r) => { regParDom[r.label] = r.id; });
    const corridors = {};
    mesh.relations.forEach((r) => {
      const a = domDe[r.source];
      const b = domDe[r.cible];
      if (!a || !b || a === b || !regParDom[a] || !regParDom[b]) return;
      const [x, y] = [a, b].sort();
      const key = `${x}::${y}`;
      if (!corridors[key]) corridors[key] = { a: x, b: y, n: 0, actif: false };
      corridors[key].n += 1;
      if (r.active) corridors[key].actif = true;
    });
    es = Object.values(corridors).map((c) => ({
      id: `corridor-${c.a}-${c.b}`,
      source: regParDom[c.a],
      target: regParDom[c.b],
      animated: c.actif,
      style: { stroke: "rgba(17,17,16,0.3)", strokeWidth: 2.5, opacity: 0.8 },
      label: `${c.a} ↔ ${c.b} · ${c.n} relation${c.n > 1 ? "s" : ""}${c.actif ? " · activité élevée" : ""}`,
      labelStyle: { fill: "rgba(17,17,16,0.7)", fontSize: 10, fontFamily: "IBM Plex Mono" },
      labelBgStyle: { fill: "rgba(255,255,255,0.92)" },
    }));
  } else {
    es = mesh.relations
      .filter((r) => (situation && implique.length ? implique.includes(r.source) && implique.includes(r.cible) : true))
      .filter((r) => !focus || r.source === focus || r.cible === focus)
      .map((r) => makeEdge(r, zoomNiveau));
    if (vueActive?.type === "relations_non_confirmees") {
      es = es.map((e) =>
        e.data?.etat === "confirmee" ? { ...e, animated: false, style: { ...e.style, opacity: 0.1 } } : e
      );
    }
    if (relFocus && selection.length > 1) {
      es = es.filter((e) => selection.includes(e.source) && selection.includes(e.target));
    }
    if (focusCarte?.type === "relations" && focusCarte.ids?.length) {
      es = es.map((e) =>
        focusCarte.ids.includes(e.id)
          ? { ...e, animated: true, style: { ...e.style, opacity: 1, strokeWidth: 2.6 } }
          : { ...e, animated: false, style: { ...e.style, opacity: 0.08 } }
      );
    }
  }
  return { nodes: ns, edges: appliquerTemps(es, temps) };
}
