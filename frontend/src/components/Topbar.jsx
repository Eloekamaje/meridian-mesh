import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, LockSimple, Bell, Flag, Users, Sparkle } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { parseQuand } from "@/lib/temps";

const TYPES_NOTIF = { mention: "#9B87F5", assignation: "#F2B84B", a_revoir: "#F87171" };

// En-tête contextuel permanent : espace actif · état du Mesh · sollicitations · Flore · identité
export default function Topbar() {
  const { personas, persona, espaces, vues, cible, info, changerPersona, changerCible } = usePerimetre();
  const { mesh } = useMesh();
  const { floreOuverte, basculerFlore } = useContexte();
  const navigate = useNavigate();
  const [notifs, setNotifs] = useState([]);
  const [nonLues, setNonLues] = useState(0);
  const [aTraiter, setATraiter] = useState(0);
  const [panneau, setPanneau] = useState(false);
  const refPanneau = useRef(null);

  const actifs = mesh?.jumeaux.filter((j) => j.statut === "actif").length ?? 0;

  // Fraîcheur du Mesh : la mise à jour la plus récente parmi les jumeaux
  const fraicheurMesh = (() => {
    let meilleur = null;
    for (const j of mesh?.jumeaux || []) {
      const d = parseQuand(j.fraicheur);
      if (d && (!meilleur || d > meilleur.d)) meilleur = { d, texte: j.fraicheur };
    }
    return meilleur?.texte || null;
  })();

  const chargerNotifs = () =>
    api.get("/notifications").then((r) => {
      setNotifs(r.data.notifications);
      setNonLues(r.data.non_lues);
    }).catch(() => {});

  useEffect(() => {
    chargerNotifs();
    api.get("/initiatives/compteurs").then((r) => setATraiter(r.data.a_traiter)).catch(() => {});
    const t = setInterval(() => {
      chargerNotifs();
      api.get("/initiatives/compteurs").then((r) => setATraiter(r.data.a_traiter)).catch(() => {});
    }, 20000);
    return () => clearInterval(t);
  }, [persona, cible]);

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
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-4" data-testid="topbar">
      {/* Espace actif */}
      <div className="flex min-w-0 items-center gap-2">
        <select
          value={cible}
          onChange={(e) => changerCible(e.target.value)}
          data-testid="selecteur-perimetre"
          title="Équipe / espace actif"
          className="h-8 max-w-44 truncate rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs font-semibold text-[#F2F6F8] focus:border-[#9B87F5]/60 focus:outline-none"
        >
          <optgroup label="Espaces">
            {espaces.map((e) => (
              <option key={e.id} value={e.id} label={e.global ? `${e.label} · autorisé` : e.label} />
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
            className="hidden items-center gap-1.5 rounded border px-2 py-1 font-code text-[9px] uppercase tracking-wider xl:inline-flex"
            style={
              info.espace.global
                ? { color: "#34D399", borderColor: "#34D39944", backgroundColor: "#34D3990D" }
                : { color: "#F2B84B", borderColor: "#F2B84B44", backgroundColor: "#F2B84B0D" }
            }
            data-testid="perimetre-badge"
          >
            {info.espace.global ? <ShieldCheck size={12} /> : <LockSimple size={12} />}
            {info.espace.global ? "Vue complète du périmètre autorisé" : `Filtré côté serveur · ${info.nb_autorises} jumeaux`}
          </span>
        )}
      </div>

      <div className="flex-1" />

      {/* État du Mesh + sollicitations + identité */}
      <div className="flex shrink-0 items-center gap-2.5">
        {(
          <span className="hidden items-center gap-1.5 font-code text-[10px] uppercase tracking-[0.15em] text-[#94A3B8] lg:flex" data-testid="mesh-status">
            <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#34D399]" />
            Mesh vivant · {actifs} jumeaux
          </span>
        )}
        {fraicheurMesh && (
          <span className="hidden font-code text-[10px] text-[#7C93A8] xl:inline" data-testid="mesh-fraicheur" title="Dernière observation reçue par Méridian">
            À jour · {fraicheurMesh}
          </span>
        )}

        <button
          onClick={() => navigate("/actualites?vue=a_traiter")}
          data-testid="a-traiter-pill"
          title="Sollicitations du Mesh en attente"
          className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
            aTraiter > 0 ? "border-[#F2B84B]/40 bg-[rgba(242,184,75,0.10)] text-[#F2B84B] hover:bg-[#F2B84B]/10" : "border-[rgba(148,163,184,0.16)] text-[#7C93A8]"
          }`}
        >
          <Flag size={12} /> {aTraiter} à traiter
        </button>

        {/* Flore — présence conversationnelle globale de Méridian (⌘K) */}
        <button
          onClick={basculerFlore}
          data-testid="btn-parler-flore"
          title="Parler à Flore (⌘K) — disponible partout, comprend le contexte de ce que vous regardez"
          className={`flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-semibold transition-colors ${
            floreOuverte
              ? "border-[#9B87F5] bg-[#9B87F5] text-[#071019]"
              : "border-[#9B87F5]/40 bg-[#9B87F5]/[0.06] text-[#9B87F5] hover:bg-[#9B87F5]/12"
          }`}
        >
          <Sparkle size={13} weight="fill" />
          <span className="hidden sm:inline">Parler à Flore</span>
        </button>

        {/* Notifications */}
        <div className="relative" ref={refPanneau}>
          <button
            onClick={() => setPanneau(!panneau)}
            data-testid="notif-btn"
            title="Notifications"
            className={`relative flex h-8 w-8 items-center justify-center rounded-md border transition-colors ${panneau ? "border-[#F2B84B]/50 bg-[rgba(242,184,75,0.10)] text-[#F2B84B]" : "border-[rgba(148,163,184,0.16)] text-[#94A3B8] hover:text-[#F2F6F8]"}`}
          >
            <Bell size={14} />
            {nonLues > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#F87171] px-1 font-code text-[9px] font-bold text-[#071019]" data-testid="notif-badge">
                {nonLues}
              </span>
            )}
          </button>
          {panneau && (
            <div className="glass absolute right-0 top-10 z-50 w-96 max-w-[90vw] rounded-xl p-2" data-testid="notif-panel">
              <div className="flex items-center justify-between px-2 py-1.5">
                <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Notifications</span>
                {nonLues > 0 && (
                  <button
                    onClick={async () => { await api.post("/notifications/tout-lire").catch(() => {}); chargerNotifs(); }}
                    data-testid="notif-tout-lire"
                    className="font-code text-[10px] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"
                  >
                    Tout marquer lu
                  </button>
                )}
              </div>
              <div className="max-h-80 overflow-y-auto">
                {notifs.map((n) => (
                  <button key={n.id} onClick={() => ouvrirNotif(n)} data-testid={`notif-item-${n.id}`}
                    className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2.5 text-left transition-colors hover:bg-[rgba(148,163,184,0.10)] ${n.lu ? "opacity-45" : ""}`}>
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: TYPES_NOTIF[n.type] || "#7C93A8" }} />
                    <span className="min-w-0">
                      <span className="block text-xs leading-snug text-[#D8E2EA]">{n.texte}</span>
                      <span className="mt-0.5 block font-code text-[9px] text-[#7C93A8]">{new Date(n.quand).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</span>
                    </span>
                  </button>
                ))}
                {notifs.length === 0 && <p className="px-2 py-4 text-center text-xs text-[#7C93A8]">Aucune notification.</p>}
              </div>
            </div>
          )}
        </div>

        {/* Identité */}
        <div className="flex items-center gap-1.5 border-l border-[rgba(148,163,184,0.16)] pl-2.5">
          <Users size={14} className="text-[#7C93A8]" />
          <select
            value={persona}
            onChange={(e) => changerPersona(e.target.value)}
            data-testid="selecteur-persona"
            title="Profil actif"
            className="h-8 max-w-40 rounded-md border border-[rgba(148,163,184,0.16)] bg-[#0F1D28] px-2 text-xs text-[#D8E2EA] focus:outline-none"
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id} label={`${p.nom} — ${p.role}`} />
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
