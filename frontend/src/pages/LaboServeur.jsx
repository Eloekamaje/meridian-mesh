import { useState } from "react";
import { Link } from "react-router-dom";
import { Flask } from "@phosphor-icons/react";
import AtlasEchelle from "@/components/map/AtlasEchelle";

// ============================================================================================
// LABORATOIRE — le Mesh servi par vue, isolé de l'Atlas : même composant que l'Atlas (AtlasEchelle),
// avec un sélecteur de taille. En production, l'Atlas y bascule seul au-delà de 300 jumeaux, ou avec ?echelle=N.
// ============================================================================================

const SOURCES = [[null, "Mesh réel"], [10000, "10 000"], [100000, "100 000"], [1000000, "1 000 000"], [5000000, "5 000 000"]];

export default function LaboServeur() {
  const [n, setN] = useState(null);
  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="labo-serveur">
      <div className="flex items-center gap-3 border-b border-white/10 px-5 py-3">
        <Flask size={18} className="text-blue-300" />
        <h1 className="text-sm font-semibold text-slate-100">Laboratoire · le Mesh servi par vue</h1>
        <div className="ml-auto flex items-center gap-1">
          {SOURCES.map(([v, label]) => (
            <button key={String(v)} onClick={() => setN(v)} data-testid={`source-${v}`}
              className={`rounded-md px-2.5 py-1 text-xs ${n === v ? "bg-blue-500/25 text-blue-100" : "text-slate-400 hover:bg-white/5"}`}>{label}</button>
          ))}
          <Link to="/atlas" className="ml-2 text-xs text-slate-400 hover:text-slate-200">Atlas</Link>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <AtlasEchelle key={String(n)} synthetique={n} />
      </div>
    </div>
  );
}
