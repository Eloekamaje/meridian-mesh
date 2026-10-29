import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell } from "@phosphor-icons/react";
import api from "@/lib/api";
import { useEvenements } from "@/lib/evenements";

const TYPES_NOTIF = { mention: "#60A5FA", assignation: "#F2B84B", a_revoir: "#F87171", investigation_terminee: "#34D399" };

// Cloche de notifications de la barre latérale : un instantané au montage (et à chaque reconnexion SSE),
// puis les nouvelles notifications poussées par le canal de la persona.
export default function Notifications({ persona, cible }) {
  const navigate = useNavigate();
  const [notifs, setNotifs] = useState([]);
  const [nonLues, setNonLues] = useState(0);
  const [panneau, setPanneau] = useState(false);
  const ref = useRef(null);
  const vues = useRef(new Set());

  const charger = useCallback(() => api.get("/notifications")
    .then((r) => {
      const liste = r.data.notifications || [];
      vues.current = new Set([...vues.current, ...liste.map((n) => n.id)]);
      setNotifs((avant) => {
        const ids = new Set(liste.map((n) => n.id));
        return [...avant.filter((n) => !ids.has(n.id)), ...liste];
      });
      setNonLues(r.data.non_lues || 0);
    })
    .catch(() => {}), []);

  useEffect(() => { charger(); }, [charger, persona, cible]);

  useEvenements((e) => {
    if (e.type === "pret") { charger(); return; }
    if (e.type !== "notification.creee" || !e.notification || vues.current.has(e.notification.id)) return;
    vues.current.add(e.notification.id);
    setNotifs((liste) => [e.notification, ...liste]);
    if (!e.notification.lu) setNonLues((count) => count + 1);
  });

  useEffect(() => {
    const fermer = (e) => { if (ref.current && !ref.current.contains(e.target)) setPanneau(false); };
    document.addEventListener("mousedown", fermer);
    return () => document.removeEventListener("mousedown", fermer);
  }, []);

  const ouvrir = async (n) => {
    setPanneau(false);
    await api.post(`/notifications/${n.id}/lue`)
      .then(() => {
        setNotifs((liste) => liste.map((x) => (x.id === n.id ? { ...x, lu: true } : x)));
        setNonLues((count) => Math.max(0, count - 1));
      })
      .catch(() => {});
    if (n.lien) navigate(n.lien);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setPanneau((v) => !v)}
        data-testid="notif-btn"
        aria-label="Notifications"
        title="Notifications"
        className={`relative flex h-7 w-7 items-center justify-center rounded-lg transition-colors ${panneau ? "bg-white/[0.08] text-white" : "text-[#7C93A8] hover:bg-white/[0.06] hover:text-white"}`}
      >
        <Bell size={15} />
        {nonLues > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[#F87171] px-1 font-code text-[9px] font-bold text-[#071019]" data-testid="notif-badge">
            {nonLues}
          </span>
        )}
      </button>
      {panneau && (
        <div className="glass hud absolute left-0 top-9 z-50 w-80 max-w-[calc(100vw-2rem)] rounded-xl p-2" data-testid="notif-panel">
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#7C93A8]">Notifications</span>
            {nonLues > 0 && (
              <button
                onClick={async () => {
                  await api.post("/notifications/tout-lire")
                    .then(() => { setNotifs((l) => l.map((n) => ({ ...n, lu: true }))); setNonLues(0); })
                    .catch(() => {});
                }}
                data-testid="notif-tout-lire"
                className="font-code text-[10px] text-[#7C93A8] transition-colors hover:text-[#F2F6F8]"
              >
                Tout marquer lu
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {notifs.map((n) => (
              <button key={n.id} onClick={() => ouvrir(n)} data-testid={`notif-item-${n.id}`}
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
  );
}
