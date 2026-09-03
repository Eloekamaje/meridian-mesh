import { useCallback, useRef, useState } from "react";

// Navigation Atlas — modèle « carte continue » (façon Google Maps) :
// - glisser = déplacement pur à zoom constant (natif React Flow) ;
// - zoom uniquement explicite (molette, boutons, double-clic, ajuster à la vue) ;
// - « Explorer » = déplacement animé à zoom STRICTEMENT constant ;
// - « Ajuster au domaine » = fitBounds explicite ;
// - le fil d'Ariane est un contexte passif : domaine sous le centre du viewport,
//   stabilisé 400 ms, sans jamais déplacer la caméra.

export function dansPolygone(p, pts, ox, oy) {
  let dedans = false;
  for (let i = 0, k = pts.length - 1; i < pts.length; k = i++) {
    const xi = pts[i].x + ox;
    const yi = pts[i].y + oy;
    const xj = pts[k].x + ox;
    const yj = pts[k].y + oy;
    if (yi > p.y !== yj > p.y && p.x < ((xj - xi) * (p.y - yi)) / (yj - yi) + xi) dedans = !dedans;
  }
  return dedans;
}

export default function useNavigationAtlas({ mesh, jumeauPar, posOverrides, selection, majUrl, setDomaineSel, setOnglet, setSelected, rfRef }) {
  const [domaineActif, setDomaineActif] = useState(null);
  const stabilisation = useRef({ label: undefined, depuis: 0 });

  // Contexte passif : domaine qui contient le centre du viewport, après 400 ms de stabilité.
  // Entre deux membranes, le contexte précédent est conservé (pas de clignotement).
  const majContexte = useCallback((centre, regions) => {
    let trouve = null;
    for (const r of regions) {
      if (r.points?.length && dansPolygone(centre, r.points, r.ox, r.oy)) { trouve = r.label; break; }
    }
    const now = Date.now();
    if (trouve !== stabilisation.current.label) {
      stabilisation.current = { label: trouve, depuis: now };
    } else if (trouve !== domaineActif && now - stabilisation.current.depuis >= 400) {
      setDomaineActif(trouve);
    }
  }, [domaineActif]);

  // « Explorer » : déplacement animé vers le domaine — zoom STRICTEMENT inchangé.
  // « Ajuster au domaine » : fitBounds explicite (action distincte).
  const explorerDomaine = useCallback((label, { ajuster = false } = {}) => {
    const membres = (mesh?.jumeaux || []).filter((j) => j.domaine === label && !j.anonyme);
    setDomaineSel(label);
    setOnglet("detail");
    majUrl({ domaine: label, sel: null, jumeau: null });
    // Navigation programmée : synchroniser le contexte passif sans attendre un nouvel onMove
    stabilisation.current = { label, depuis: Date.now() };
    setDomaineActif(label);
    if (!membres.length || !rfRef.current) return;
    const pts = membres.map((j) => posOverrides[j.id] || j.position);
    if (ajuster) {
      const xs = pts.map((p) => p.x);
      const ys = pts.map((p) => p.y);
      rfRef.current.fitBounds(
        { x: Math.min(...xs) - 170, y: Math.min(...ys) - 150, width: Math.max(...xs) - Math.min(...xs) + 380, height: Math.max(...ys) - Math.min(...ys) + 340 },
        { duration: 800, maxZoom: 1.6 }
      );
    } else {
      const z = rfRef.current.getZoom();
      const cx = pts.reduce((a, p) => a + p.x, 0) / pts.length + 30;
      const cy = pts.reduce((a, p) => a + p.y, 0) / pts.length + 40;
      rfRef.current.setCenter(cx, cy, { zoom: z, duration: 800 });
    }
  }, [mesh, posOverrides, majUrl, setDomaineSel, setOnglet, rfRef]);

  // Double-clic jumeau : déplacement animé + zoom explicite centré sur lui
  const centrerJumeau = useCallback((j) => {
    const pos = posOverrides[j.id] || j.position;
    setSelected(j);
    setDomaineSel(null);
    setOnglet("detail");
    majUrl({ sel: j.id, jumeau: null });
    stabilisation.current = { label: j.domaine, depuis: Date.now() };
    setDomaineActif(j.domaine);
    const z = rfRef.current?.getZoom() ?? 1;
    rfRef.current?.setCenter(pos.x + 30, pos.y + 40, { zoom: Math.min(Math.max(z * 1.6, 1.5), 2.4), duration: 700 });
  }, [posOverrides, majUrl, setSelected, setDomaineSel, setOnglet, rfRef]);

  // « Mesh global » : ajuster à la vue (action explicite)
  const ajusterVue = useCallback(() => {
    setDomaineSel(null);
    majUrl({ domaine: null, sel: null, jumeau: null });
    stabilisation.current = { label: undefined, depuis: Date.now() };
    setDomaineActif(null);
    rfRef.current?.fitView({ duration: 800, padding: 0.15 });
  }, [majUrl, setDomaineSel, rfRef]);

  // Cadrer la sélection en cours (action explicite depuis le fil d'Ariane)
  const revenirSelection = useCallback(() => {
    const pts = selection.map((id) => { const j = jumeauPar(id); return j ? posOverrides[id] || j.position : null; }).filter(Boolean);
    if (pts.length && rfRef.current) {
      const xs = pts.map((p) => p.x);
      const ys = pts.map((p) => p.y);
      rfRef.current.fitBounds(
        { x: Math.min(...xs) - 160, y: Math.min(...ys) - 120, width: Math.max(...xs) - Math.min(...xs) + 350, height: Math.max(...ys) - Math.min(...ys) + 260 },
        { duration: 800 }
      );
    }
  }, [selection, jumeauPar, posOverrides, rfRef]);

  return { domaineActif, majContexte, explorerDomaine, centrerJumeau, ajusterVue, revenirSelection };
}
