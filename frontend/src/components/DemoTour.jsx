import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, X } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { useDemo } from "@/lib/demo";

export default function DemoTour() {
  const { actes, courant, suivant, precedent, quitter } = useDemo();
  const navigate = useNavigate();

  useEffect(() => {
    if (courant >= 0 && actes[courant]) navigate(actes[courant].route);
  }, [courant, actes, navigate]);

  if (courant < 0 || !actes[courant]) return null;
  const a = actes[courant];
  const dernier = courant === actes.length - 1;

  return (
    <div className="glass rise fixed bottom-6 left-[276px] z-50 w-[340px] rounded-xl p-5" data-testid="demo-panel">
      <div
        className="font-code text-[10px] uppercase tracking-[0.25em]"
        style={{ color: ["#22D3EE", "#A78BFA", "#FBBF24"][(a.acte - 1) % 3] }}
      >
        Parcours Olympiade — Acte {a.acte} / {actes.length}
      </div>
      <div className="mt-1.5 font-display text-lg font-bold text-white">{a.titre}</div>
      <p className="mt-1.5 text-sm leading-relaxed text-white/65">{a.texte}</p>
      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" variant="ghost" onClick={precedent} disabled={courant === 0} data-testid="demo-prev-btn" className="text-white/60 hover:text-white">
          <ArrowLeft size={16} />
        </Button>
        <Button size="sm" onClick={suivant} data-testid="demo-next-btn" className="flex-1 bg-[#3B82F6] text-white hover:bg-[#2F6FDB]">
          {dernier ? "Terminer le parcours" : "Acte suivant"}
          <ArrowRight size={16} />
        </Button>
        <Button size="sm" variant="ghost" onClick={quitter} data-testid="demo-quit-btn" className="text-white/60 hover:text-white">
          <X size={16} />
        </Button>
      </div>
    </div>
  );
}
