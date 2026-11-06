import { useCallback, useEffect, useRef, useState } from "react";

const clamp = (valeur, minimum, maximum) => Math.max(minimum, Math.min(maximum, valeur));

export default function DiagrammeCompile({ diagramme, testid = "diagramme-compile" }) {
  const viewportRef = useRef(null);
  const dragRef = useRef(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [pleinEcran, setPleinEcran] = useState(false);
  const [selection, setSelection] = useState(null);

  const largeur = Number(diagramme?.largeur) || 960;
  const hauteur = Number(diagramme?.hauteur) || 600;
  const svg = diagramme?.svg || "";
  const titre = diagramme?.titre || "Diagramme";

  const fit = useCallback(() => {
    const el = viewportRef.current;
    if (!el) return;
    const largeurDisponible = el.clientWidth || largeur;
    const hauteurDisponible = el.clientHeight || hauteur;
    const suivant = clamp(Math.min(largeurDisponible / largeur, hauteurDisponible / hauteur), 0.1, 1.4);
    setZoom(suivant);
    setPan({
      x: Math.max(0, (largeurDisponible - largeur * suivant) / 2),
      y: Math.max(0, (hauteurDisponible - hauteur * suivant) / 2),
    });
  }, [largeur, hauteur]);

  useEffect(() => { fit(); }, [fit, pleinEcran]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return undefined;
    const surMolette = (evenement) => {
      evenement.preventDefault();
      const rect = el.getBoundingClientRect();
      setZoom((courant) => {
        const suivant = clamp(courant * (evenement.deltaY < 0 ? 1.12 : 0.89), 0.1, 4);
        const rapport = suivant / courant;
        setPan((position) => ({
          x: evenement.clientX - rect.left - (evenement.clientX - rect.left - position.x) * rapport,
          y: evenement.clientY - rect.top - (evenement.clientY - rect.top - position.y) * rapport,
        }));
        return suivant;
      });
    };
    el.addEventListener("wheel", surMolette, { passive: false });
    return () => el.removeEventListener("wheel", surMolette);
  }, []);

  const commencer = (evenement) => {
    if (evenement.target.closest("button")) return;
    dragRef.current = { x0: evenement.clientX, y0: evenement.clientY, x: pan.x, y: pan.y };
    evenement.currentTarget.setPointerCapture?.(evenement.pointerId);
  };
  const glisser = (evenement) => {
    if (!dragRef.current) return;
    setPan({
      x: dragRef.current.x + (evenement.clientX - dragRef.current.x0),
      y: dragRef.current.y + (evenement.clientY - dragRef.current.y0),
    });
  };
  const finir = () => { dragRef.current = null; };
  const cliquer = (evenement) => {
    const noeud = evenement.target.closest?.("[data-node-id]");
    if (noeud) setSelection({
      id: noeud.getAttribute("data-node-id"),
      libelle: noeud.textContent || noeud.getAttribute("data-node-id"),
    });
  };

  if (!svg) return null;

  return (
    <div
      className={pleinEcran
        ? "fixed inset-0 z-50 flex flex-col overflow-hidden bg-[#071019] p-4"
        : "my-2 w-full overflow-hidden"}
      data-testid={testid}
      data-mode="design-diagram"
    >
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 truncate font-code text-[10px] text-[#64748B]">
          {selection ? `Nœud : ${selection.libelle}` : "Molette pour zoomer · glisser pour déplacer · cliquer un nœud"}
        </span>
        <div className="flex items-center gap-1" role="group" aria-label="Contrôles du diagramme">
          <button type="button" onClick={() => setZoom((z) => Math.max(0.1, z / 1.2))} aria-label="Dézoomer"
            className="h-7 w-7 rounded-md border border-white/[0.12] font-code text-xs text-[#93C5FD] hover:bg-[#60A5FA]/10">−</button>
          <span className="w-10 text-center font-code text-[10px] text-[#7C93A8]">{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => setZoom((z) => Math.min(4, z * 1.2))} aria-label="Zoomer"
            className="h-7 w-7 rounded-md border border-white/[0.12] font-code text-xs text-[#93C5FD] hover:bg-[#60A5FA]/10">+</button>
          <button type="button" onClick={fit} data-testid={`${testid}-fit`}
            className="rounded-md border border-white/[0.12] px-2 py-1 font-code text-[10px] text-[#93C5FD] hover:bg-[#60A5FA]/10">Ajuster</button>
          <button type="button" onClick={() => setPleinEcran((v) => !v)} data-testid={`${testid}-plein-ecran`}
            className="rounded-md border border-white/[0.12] px-2 py-1 font-code text-[10px] text-[#93C5FD] hover:bg-[#60A5FA]/10">
            {pleinEcran ? "Fermer" : "Plein écran"}
          </button>
        </div>
      </div>
      <div
        ref={viewportRef}
        onPointerDown={commencer}
        onPointerMove={glisser}
        onPointerUp={finir}
        onPointerCancel={finir}
        onClick={cliquer}
        className={pleinEcran
          ? "min-h-0 flex-1 cursor-grab overflow-hidden active:cursor-grabbing"
          : "h-[56vh] max-h-[520px] min-h-[320px] cursor-grab overflow-hidden rounded-md border border-white/[0.08] bg-[#0A131C]/40 active:cursor-grabbing"}
        style={{ touchAction: "none" }}
        data-testid={`${testid}-viewport`}
        aria-label={titre}
      >
        <div
          style={{
            width: `${largeur}px`, height: `${hauteur}px`,
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            transformOrigin: "0 0",
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}
