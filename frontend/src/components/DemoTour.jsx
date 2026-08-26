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
        style={{ color: ["#0E7490", "#6D28D9", "#B45309"][(a.acte - 1) % 3] }}
      >
        Parcours Olympiade — Acte {a.acte} / {actes.length}
      </div>
      <div className="mt-1.5 font-display text-lg font-bold text-[#111110]">{a.titre}</div>
      <p className="mt-1.5 text-sm leading-relaxed text-[#52524F]">{a.texte}</p>
      <div className="mt-4 flex items-center gap-2">
        <Button size="sm" variant="ghost" onClick={precedent} disabled={courant === 0} data-testid="demo-prev-btn" className="text-[#52524F] hover:text-[#111110]">
          <ArrowLeft size={16} />
        </Button>
        <Button size="sm" onClick={suivant} data-testid="demo-next-btn" className="flex-1 bg-[#3730A3] text-white hover:bg-[#4338CA]">
          {dernier ? "Terminer le parcours" : "Acte suivant"}
          <ArrowRight size={16} />
        </Button>
        <Button size="sm" variant="ghost" onClick={quitter} data-testid="demo-quit-btn" className="text-[#52524F] hover:text-[#111110]">
          <X size={16} />
        </Button>
      </div>
    </div>
  );
}
