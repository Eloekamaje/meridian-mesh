import { useCallback, useRef, useState } from "react";

export default function useNavigationAtlas({
  mesh, jumeauPar, posOverrides, selection, majUrl,
  setDomaineSel, setOnglet, setSelected, setRelFocus, setFocusVisuel, rfRef,
}) {
  const [domaineInterne, setDomaineInterne] = useState(null);
  const [jumeauFocus, setJumeauFocus] = useState(null);
  const [historique, setHistorique] = useState([{ type: "mesh" }]);
  const [indexHist, setIndexHist] = useState(0);
  const histRef = useRef({ h: [{ type: "mesh" }], i: 0 });
  const verrouNav = useRef(0);
  const zoomEntree = useRef(null);

  const appliquerNiveau = useCallback((niveau) => {
    verrouNav.current = Date.now();
    if (niveau.type === "mesh") {
      setDomaineInterne(null);
      setJumeauFocus(null);
      setFocusVisuel(null);
      majUrl({ interne: null, jumeau: null });
      rfRef.current?.fitView({ duration: 800, padding: 0.15 });
    } else if (niveau.type === "domaine") {
      setDomaineInterne(niveau.label);
      setJumeauFocus(null);
      setDomaineSel(niveau.label);
      setOnglet("detail");
      setRelFocus(false);
      setFocusVisuel({ type: "domaine", label: niveau.label });
      majUrl({ domaine: niveau.label, interne: "1", jumeau: null, sel: null });
      const reg = mesh?.regions?.find((r) => r.label === niveau.label);
      const membres = mesh?.jumeaux.filter((j) => j.domaine === niveau.label && !j.anonyme) || [];
      if (membres.length && rfRef.current) {
        // Fit bounds sur les membres réels + portes externes en périphérie, marge ~15 %
        const xs = membres.map((j) => (posOverrides[j.id] || j.position).x);
        const ys = membres.map((j) => (posOverrides[j.id] || j.position).y);
        const x0 = Math.min(Math.min(...xs) - 120, reg ? reg.x - 310 : Infinity) - 70;
        const x1 = Math.max(Math.max(...xs) + 190, reg ? reg.x + reg.w + 40 : -Infinity) + 70;
        const y0 = Math.min(...ys) - 120;
        const y1 = Math.max(...ys) + 150;
        rfRef.current.fitBounds({ x: x0, y: y0, width: x1 - x0, height: y1 - y0 }, { duration: 800, maxZoom: 1.35 });
      }
    } else if (niveau.type === "jumeau") {
      const j = mesh?.jumeaux.find((x) => x.id === niveau.id);
      if (!j) return;
      const pos = posOverrides[j.id] || j.position;
      setDomaineInterne(j.domaine);
      setJumeauFocus(j.id);
      setSelected(j);
      setOnglet("detail");
      setFocusVisuel({ type: "jumeau", label: j.nom, domaine: j.domaine });
      majUrl({ domaine: j.domaine, interne: "1", jumeau: j.id, sel: j.id });
      if (rfRef.current) rfRef.current.fitBounds({ x: pos.x - 450, y: pos.y - 340, width: 1090, height: 740 }, { duration: 800 });
    }
    setTimeout(() => { zoomEntree.current = rfRef.current?.getZoom() ?? null; }, 950);
  }, [mesh, posOverrides, majUrl, setDomaineSel, setOnglet, setSelected, setRelFocus, setFocusVisuel, rfRef]);

  const pousserHist = useCallback((entree) => {
    const base = histRef.current.h.slice(0, histRef.current.i + 1);
    histRef.current = { h: [...base, entree], i: base.length };
    setHistorique(histRef.current.h);
    setIndexHist(histRef.current.i);
  }, []);

  const entrerDomaine = useCallback((label) => {
    appliquerNiveau({ type: "domaine", label });
    pousserHist({ type: "domaine", label });
  }, [appliquerNiveau, pousserHist]);

  const sortirDomaine = useCallback(() => {
    appliquerNiveau({ type: "mesh" });
    pousserHist({ type: "mesh" });
  }, [appliquerNiveau, pousserHist]);

  const entrerJumeau = useCallback((j) => {
    appliquerNiveau({ type: "jumeau", id: j.id });
    pousserHist({ type: "jumeau", id: j.id, label: j.nom, domaine: j.domaine });
  }, [appliquerNiveau, pousserHist]);

  const sortirJumeau = useCallback(() => {
    if (!jumeauFocus) return;
    const j = jumeauPar(jumeauFocus);
    const dom = j?.domaine || domaineInterne;
    if (!dom) return;
    appliquerNiveau({ type: "domaine", label: dom });
    pousserHist({ type: "domaine", label: dom });
  }, [jumeauFocus, jumeauPar, domaineInterne, appliquerNiveau, pousserHist]);

  const allerHist = useCallback((idx) => {
    const entree = histRef.current.h[idx];
    if (!entree) return;
    histRef.current = { ...histRef.current, i: idx };
    setIndexHist(idx);
    appliquerNiveau(entree);
  }, [appliquerNiveau]);

  const revenirSelection = useCallback(() => {
    appliquerNiveau({ type: "mesh" });
    setDomaineSel(null);
    majUrl({ domaine: null });
    pousserHist({ type: "mesh" });
    setTimeout(() => {
      const pts = selection.map((id) => { const j = jumeauPar(id); return j ? posOverrides[id] || j.position : null; }).filter(Boolean);
      if (pts.length && rfRef.current) {
        const xs = pts.map((p) => p.x);
        const ys = pts.map((p) => p.y);
        rfRef.current.fitBounds({ x: Math.min(...xs) - 160, y: Math.min(...ys) - 120, width: Math.max(...xs) - Math.min(...xs) + 350, height: Math.max(...ys) - Math.min(...ys) + 260 }, { duration: 800 });
      }
    }, 850);
  }, [appliquerNiveau, pousserHist, selection, jumeauPar, posOverrides, setDomaineSel, majUrl, rfRef]);

  return {
    domaineInterne, setDomaineInterne,
    jumeauFocus, setJumeauFocus,
    historique, indexHist,
    entrerDomaine, sortirDomaine, entrerJumeau, sortirJumeau, allerHist, revenirSelection,
    verrouNav, zoomEntree,
  };
}
