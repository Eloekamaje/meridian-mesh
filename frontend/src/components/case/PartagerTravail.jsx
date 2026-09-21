import { useEffect, useRef, useState } from "react";
import { ShareNetwork, User, UsersThree, Buildings, Link as LinkIcon, Check } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";

// À qui appartient ce travail ? Trois portées, choisies par le responsable : lui seul, son équipe (l'espace), toute l'entreprise.
// La portée ne donne jamais plus de droits que le périmètre : un jumeau hors des droits de quelqu'un reste invisible pour cette personne.
const OPTIONS = [
  ["personnel", "Moi seul", "Seuls vous et les participants le voient.", User],
  ["equipe", "Mon équipe", "Tous ceux de votre espace le voient et peuvent y répondre.", UsersThree],
  ["entreprise", "Toute l'entreprise", "Tous ceux dont les droits sur ses jumeaux le permettent.", Buildings],
];
const COURT = { personnel: "Moi seul", equipe: "Équipe", entreprise: "Entreprise" };

export default function PartagerTravail({ cas, onChange }) {
  const [ouvert, setOuvert] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!ouvert) return undefined;
    const dehors = (e) => ref.current && !ref.current.contains(e.target) && setOuvert(false);
    const echap = (e) => e.key === "Escape" && setOuvert(false);
    document.addEventListener("mousedown", dehors);
    document.addEventListener("keydown", echap);
    return () => { document.removeEventListener("mousedown", dehors); document.removeEventListener("keydown", echap); };
  }, [ouvert]);

  const copier = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      toast.success(cas.portee === "personnel" ? "Lien copié — seul vous pouvez l'ouvrir tant que le travail est personnel" : "Lien du travail copié");
    } catch {
      toast.error("Copie impossible — " + window.location.href);
    }
  };

  // Jeu de données de démonstration sans portée : le bouton garde son geste d'origine, copier le lien
  if (!cas.portee) {
    return (
      <button onClick={copier} data-testid="travail-partager-btn" title="Partager le travail" className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-xs text-[#CBD5E1] transition-colors hover:border-white/20 hover:text-white">
        <ShareNetwork size={14} /><span className="hidden sm:inline">Partager</span>
      </button>
    );
  }

  const choisir = async (portee) => {
    if (portee === cas.portee || envoi) return;
    setEnvoi(true);
    try {
      const { data } = await api.post(`/cases/${cas.id}/portee`, { portee });
      onChange(data);
      toast.success(portee === "personnel" ? "Travail réservé à vous" : portee === "equipe" ? `Travail partagé avec l'équipe${cas.equipe_label ? ` (${cas.equipe_label})` : ""}` : "Travail partagé avec toute l'entreprise");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Partage impossible");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOuvert((o) => !o)} aria-expanded={ouvert} data-testid="travail-partager-btn" title="Qui voit ce travail ?" className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-xs text-[#CBD5E1] transition-colors hover:border-white/20 hover:text-white">
        <ShareNetwork size={14} />
        <span className="hidden sm:inline" data-testid="travail-portee-libelle">{COURT[cas.portee] || "Partager"}</span>
      </button>
      {ouvert && (
        <div className="glass absolute right-0 top-9 z-50 w-72 rounded-xl border border-white/10 bg-[#0C1724] p-2 shadow-2xl" data-testid="partage-panneau" role="dialog" aria-label="Qui voit ce travail ?">
          <div className="px-2 pb-1.5 pt-1 font-code text-[11px] uppercase tracking-[0.16em] text-[#7C93A8]">Qui voit ce travail ?</div>
          {OPTIONS.map(([id, titre, aide, Icone]) => {
            const actif = cas.portee === id;
            return (
              <button key={id} onClick={() => choisir(id)} disabled={!cas.peut_partager || envoi} aria-pressed={actif} data-testid={`portee-${id}`}
                className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors disabled:cursor-not-allowed ${actif ? "bg-[#60A5FA]/10" : "hover:bg-white/[0.05] disabled:hover:bg-transparent"}`}>
                <Icone size={16} className={`mt-0.5 shrink-0 ${actif ? "text-[#60A5FA]" : "text-[#7C93A8]"}`} />
                <span className="min-w-0 flex-1">
                  <span className={`block text-[13px] font-medium ${actif ? "text-[#BFDBFE]" : "text-[#E6EEF5]"}`}>{titre}{id === "equipe" && cas.equipe_label ? ` · ${cas.equipe_label}` : ""}</span>
                  <span className="block text-xs leading-snug text-[#7C93A8]">{aide}</span>
                </span>
                {actif && <Check size={14} weight="bold" className="mt-0.5 shrink-0 text-[#60A5FA]" />}
              </button>
            );
          })}
          {!cas.peut_partager && <p className="px-2.5 pb-1 pt-1 text-xs text-[#7C93A8]" data-testid="partage-reserve">Seul le responsable du travail décide de qui le voit.</p>}
          <button onClick={copier} data-testid="partage-copier" className="mt-1 flex w-full items-center gap-2 rounded-lg border-t border-white/[0.06] px-2.5 py-2 text-left text-xs text-[#94A3B8] transition-colors hover:text-white">
            <LinkIcon size={13} /> Copier le lien
          </button>
        </div>
      )}
    </div>
  );
}
