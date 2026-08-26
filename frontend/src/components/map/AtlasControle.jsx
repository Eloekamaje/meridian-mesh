import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Pulse, Pause, Stack, X } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { MODES, COUCHES } from "@/lib/atlasGraph";

export default function AtlasControle({
  mode, setMode, situations, situationId, setSituationId,
  parcoursId, setParcoursId, mesh, focus, direct, setDirect,
  couches, setCouches, rechargerVues,
}) {
  const [nomVue, setNomVue] = useState("");
  // Façon Google Maps : par défaut seule la barre de modes est visible ; les réglages se rangent derrière un bouton « calques »
  const [deplie, setDeplie] = useState(() => typeof window !== "undefined" && window.innerWidth >= 1500);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1500px)");
    const maj = (e) => { if (!e.matches) setDeplie(false); };
    mq.addEventListener("change", maj);
    return () => mq.removeEventListener("change", maj);
  }, []);

  const modeInfo = MODES.find((m) => m.id === mode);

  const enregistrerVue = async () => {
    if (!nomVue.trim()) return;
    try {
      await api.post("/vues", { nom: nomVue.trim(), type: "selection", jumeaux: (mesh?.jumeaux || []).filter((j) => !j.anonyme).map((j) => j.id) });
      setNomVue("");
      rechargerVues();
      toast.success("Vue enregistrée — disponible dans le sélecteur de périmètre");
    } catch {
      toast.error("Enregistrement impossible");
    }
  };

  return (
    <div className="glass absolute left-4 top-4 z-10 rounded-xl p-2" data-testid="map-mode-switcher">
      <div className="flex items-center gap-1">
        {MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => setMode(m.id)}
            data-testid={`map-mode-${m.id}`}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors duration-200 ${
              mode === m.id ? "bg-[#3B82F6] text-white" : "text-white/55 hover:bg-white/[0.06] hover:text-white"
            }`}
          >
            {m.label}
          </button>
        ))}
        <button
          onClick={() => setDeplie(!deplie)}
          data-testid="controle-toggle"
          title={deplie ? "Replier les réglages" : "Calques et réglages"}
          className={`ml-1 flex h-7 w-7 items-center justify-center rounded-md transition-colors ${deplie ? "bg-[#22D3EE]/15 text-[#22D3EE]" : "text-white/45 hover:bg-white/[0.06] hover:text-white"}`}
        >
          {deplie ? <X size={14} /> : <Stack size={14} />}
        </button>
      </div>

      {/* Sélecteurs de contexte : toujours visibles quand le mode l'exige */}
      {mode === "situation" && (
        <select
          value={situationId}
          onChange={(e) => setSituationId(e.target.value)}
          data-testid="map-situation-select"
          className="mt-2 w-full rounded-md border border-white/10 bg-black/60 px-2 py-1.5 text-xs text-white focus:outline-none"
        >
          {situations.filter((s) => (s.jumeaux || []).length > 0).map((s) => (
            <option key={s.id} value={s.id} label={s.titre} />
          ))}
        </select>
      )}
      {mode === "parcours" && (
        <select
          value={parcoursId}
          onChange={(e) => setParcoursId(e.target.value)}
          data-testid="map-parcours-select"
          className="mt-2 w-full rounded-md border border-white/10 bg-black/60 px-2 py-1.5 text-xs text-white focus:outline-none"
        >
          {(mesh?.parcours || []).map((p) => (
            <option key={p.id} value={p.id} label={p.nom} />
          ))}
        </select>
      )}
      {focus && (
        <Link to="/atlas" className="mt-2 block px-1 font-code text-[10px] text-[#3B82F6] hover:underline" data-testid="map-clear-focus">
          ← Retirer le filtre « {focus} »
        </Link>
      )}

      {deplie && (
        <div data-testid="controle-details">
          <p className="mt-2 px-1 font-code text-[10px] text-white/40">{modeInfo?.question}</p>

          {mesh?.perimetre?.nb_restreints > 0 && (
            <div className="mt-2 rounded border border-dashed border-white/15 px-2 py-1.5 font-code text-[9px] leading-relaxed text-white/45" data-testid="badge-dependances-restreintes">
              {mesh.perimetre.nb_restreints} dépendance(s) restreinte(s) — politique « {mesh.perimetre.politique === "anonymisee" ? "dépendance anonymisée" : mesh.perimetre.politique === "resume" ? "résumé autorisé" : "masquage complet"} »
            </div>
          )}

          {/* Direct / Pause */}
          <div className="mt-3 flex items-center gap-1 border-t border-white/[0.08] pt-2.5">
            <span className="px-1 font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Temps réel</span>
            <button
              onClick={() => setDirect(true)}
              data-testid="direct-btn"
              className={`flex items-center gap-1 rounded px-2 py-1 font-code text-[10px] transition-colors ${direct ? "bg-[#10B981]/15 text-[#10B981]" : "text-white/45 hover:text-white"}`}
            >
              <Pulse size={12} /> Direct
            </button>
            <button
              onClick={() => setDirect(false)}
              data-testid="pause-btn"
              className={`flex items-center gap-1 rounded px-2 py-1 font-code text-[10px] transition-colors ${!direct ? "bg-[#F59E0B]/15 text-[#F59E0B]" : "text-white/45 hover:text-white"}`}
            >
              <Pause size={12} /> Pause
            </button>
          </div>

          <div className="mt-2.5 border-t border-white/[0.08] pt-2.5">
            <div className="px-1 font-code text-[9px] uppercase tracking-[0.2em] text-white/35">Dynamiques visibles</div>
            <div className="mt-1.5 space-y-1">
              {COUCHES.map(([id, label, c]) => (
                <label key={id} className="flex cursor-pointer items-center gap-2 px-1 py-0.5" data-testid={`couche-${id}`}>
                  <input
                    type="checkbox"
                    checked={couches[id]}
                    onChange={(e) => setCouches({ ...couches, [id]: e.target.checked })}
                    className="h-3 w-3"
                    style={{ accentColor: c }}
                  />
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: c }} />
                  <span className="text-[11px] text-white/60">{label}</span>
                </label>
              ))}
            </div>
          </div>

          {mode === "territoire" && !mesh?.perimetre?.global && (
            <div className="mt-2 flex gap-1.5 px-1">
              <input
                value={nomVue}
                onChange={(e) => setNomVue(e.target.value)}
                placeholder="Nom de la vue…"
                data-testid="nom-vue-input"
                className="h-7 w-full rounded border border-white/10 bg-black/50 px-2 text-[11px] text-white placeholder:text-white/25 focus:outline-none"
              />
              <button
                onClick={enregistrerVue}
                data-testid="enregistrer-vue-btn"
                className="h-7 shrink-0 rounded border border-white/15 px-2 text-[10px] text-white/60 transition-colors hover:border-white/40 hover:text-white"
              >
                Enregistrer
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
