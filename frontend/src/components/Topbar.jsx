import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Users, ShieldCheck, LockSimple, Sparkle, Bell } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useContexte } from "@/lib/contexte";

const POLITIQUES = {
  masquage: "masquage complet",
  anonymisee: "dépendance anonymisée",
  resume: "résumé autorisé",
};

const TYPES_NOTIF = { mention: "#3B82F6", assignation: "#FBBF24", a_revoir: "#F87171" };

export default function Topbar() {
  const { personas, persona, espaces, vues, cible, info, changerPersona, changerCible } = usePerimetre();
  const { selection, floreOuverte, basculerFlore } = useContexte();
  const navigate = useNavigate();
  const [notifs, setNotifs] = useState([]);
  const [nonLues, setNonLues] = useState(0);
  const [panneau, setPanneau] = useState(false);
  const refPanneau = useRef(null);

  const chargerNotifs = () =>
    api.get("/notifications").then((r) => {
      setNotifs(r.data.notifications);
      setNonLues(r.data.non_lues);
    }).catch(() => {});

  useEffect(() => {
    chargerNotifs();
    const t = setInterval(chargerNotifs, 15000);
    return () => clearInterval(t);
  }, [persona]);

  useEffect(() => {
    const fermer = (e) => {
      if (refPanneau.current && !refPanneau.current.contains(e.target)) setPanneau(false);
    };
    document.addEventListener("mousedown", fermer);
    return () => document.removeEventListener("mousedown", fermer);
  }, []);

  const ouvrirNotif = async (n) => {
    setPanneau(false);
    await api.post(`/notifications/${n.id}/lue`).catch(() => {});
    chargerNotifs();
    if (n.lien) navigate(n.lien);
  };

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-white/[0.08] bg-[#0A0A0A] px-4" data-testid="topbar">
      <span className="font-code text-[9px] uppercase tracking-[0.25em] text-white/35">Périmètre</span>
      <select
        value={cible}
        onChange={(e) => changerCible(e.target.value)}
        data-testid="selecteur-perimetre"
        className="rounded-md border border-white/10 bg-black/60 px-2.5 py-1.5 text-xs font-semibold text-white focus:border-[#22D3EE]/60 focus:outline-none"
      >
        <optgroup label="Espaces">
          {espaces.map((e) => (
            <option key={e.id} value={e.id} label={e.global ? `${e.label} (autorisé)` : e.label} />
          ))}
        </optgroup>
        {vues.length > 0 && (
          <optgroup label="Vues enregistrées">
            {vues.map((v) => (
              <option key={v.id} value={`vue:${v.id}`} label={`Vue — ${v.nom}`} />
            ))}
          </optgroup>
        )}
      </select>

      {info && (
        <span
          className="hidden items-center gap-1.5 rounded border px-2 py-1 font-code text-[9px] uppercase tracking-wider md:inline-flex"
          style={
            info.espace.global
              ? { color: "#34D399", borderColor: "#34D39944", backgroundColor: "#34D3990D" }
              : { color: "#FBBF24", borderColor: "#FBBF2444", backgroundColor: "#FBBF240D" }
          }
          data-testid="perimetre-badge"
        >
          {info.espace.global ? <ShieldCheck size={12} /> : <LockSimple size={12} />}
          {info.espace.global
            ? "Vue complète du périmètre autorisé"
            : `Filtré côté serveur · ${info.nb_autorises} jumeaux · ${POLITIQUES[info.espace.politique_dependances] || ""}`}
        </span>
      )}

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={basculerFlore}
          data-testid="flore-btn"
          title="Ouvrir Flore (⌘K)"
          className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${
            floreOuverte
              ? "border-[#3B82F6]/60 bg-[#3B82F6]/15 text-white"
              : "border-white/10 text-white/70 hover:border-[#3B82F6]/50 hover:text-white"
          }`}
        >
          <Sparkle size={13} weight="fill" className="text-[#3B82F6]" />
          Flore
          {selection.length > 0 && (
            <span className="rounded-full bg-[#3B82F6]/25 px-1.5 font-code text-[9px] text-white" data-testid="flore-btn-badge">
              {selection.length}
            </span>
          )}
        </button>

        {/* Notifications */}
        <div className="relative" ref={refPanneau}>
          <button
            onClick={() => setPanneau(!panneau)}
            data-testid="notif-btn"
            title="Notifications"
            className={`relative flex h-8 w-8 items-center justify-center rounded-md border transition-colors ${panneau ? "border-[#FBBF24]/50 bg-[#FBBF24]/10 text-[#FBBF24]" : "border-white/10 text-white/55 hover:text-white"}`}
          >
            <Bell size={14} />
            {nonLues > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#F87171] px-1 font-code text-[9px] font-bold text-black" data-testid="notif-badge">
                {nonLues}
              </span>
            )}
          </button>
          {panneau && (
            <div className="glass absolute right-0 top-10 z-50 w-96 max-w-[90vw] rounded-xl p-2" data-testid="notif-panel">
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="font-code text-[10px] uppercase tracking-[0.2em] text-white/40">Notifications</span>
                {nonLues > 0 && (
                  <button
                    onClick={async () => { await api.post("/notifications/tout-lire").catch(() => {}); chargerNotifs(); }}
                    data-testid="notif-tout-lire"
                    className="font-code text-[10px] text-white/40 transition-colors hover:text-white"
                  >
                    Tout marquer lu
                  </button>
                )}
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notifs.map((n) => (
                  <button
                    key={n.id}
                    onClick={() => ouvrirNotif(n)}
                    data-testid={`notif-item-${n.id}`}
                    className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2.5 text-left transition-colors hover:bg-white/[0.05] ${n.lu ? "opacity-45" : ""}`}
                  >
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: TYPES_NOTIF[n.type] || "#94A3B8" }} />
                    <span className="min-w-0">
                      <span className="block text-xs leading-snug text-white/80">{n.texte}</span>
                      <span className="mt-0.5 block font-code text-[9px] text-white/30">{new Date(n.quand).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                    </span>
                  </button>
                ))}
                {notifs.length === 0 && <p className="px-2 py-4 text-center text-xs text-white/30">Aucune notification.</p>}
              </div>
            </div>
          )}
        </div>

        <Users size={14} className="text-white/40" />
        <select
          value={persona}
          onChange={(e) => changerPersona(e.target.value)}
          data-testid="selecteur-persona"
          className="rounded-md border border-white/10 bg-black/60 px-2.5 py-1.5 text-xs text-white/80 focus:outline-none"
        >
          {personas.map((p) => (
            <option key={p.id} value={p.id} label={`${p.nom} — ${p.role}`} />
          ))}
        </select>
      </div>
    </header>
  );
}
