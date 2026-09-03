import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Pulse, Pause, Stack, X, Play, ClockCounterClockwise, ArrowsLeftRight, DotsSixVertical } from "@phosphor-icons/react";
import { toast } from "sonner";
import api from "@/lib/api";
import { COUCHES } from "@/lib/atlasGraph";
import { fmtDate, fmtDateInput } from "@/lib/temps";
import useGlissable from "./useGlissable";

const MODES_TEMPS = [
  ["direct", "Direct", Pulse],
  ["pause", "Pause", Pause],
  ["replay", "Replay", Play],
  ["historique", "Historique", ClockCounterClockwise],
  ["avantapres", "Avant/Après", ArrowsLeftRight],
];

export default function AtlasControle({
  mesh, focus,
  modeTemps, setModeTemps, dateRef, setDateRef, replaying, onRejouer,
  couches, setCouches, rechargerVues,
  couchesRel, setCouchesRel, couchesCarte, setCouchesCarte,
  deplie, setDeplie, conteneurRef,
}) {
  const [nomVue, setNomVue] = useState("");
  // Panneau glissable : poignée en en-tête, position mémorisée (double-clic = ancrage par défaut)
  const { ref, decal, surPoigneeDown, reinitialiser } = useGlissable("calques", conteneurRef);

  useEffect(() => {
    if (modeTemps !== "direct" && modeTemps !== "pause") setDeplie(true);
  }, [modeTemps]);

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

  const choisirMode = (m) => {
    if (m === "replay") {
      setModeTemps("replay");
      onRejouer();
      return;
    }
    if ((m === "historique" || m === "avantapres") && !dateRef) {
      const d = new Date();
      if (m === "avantapres") d.setDate(d.getDate() - 7);
      d.setHours(23, 59, 59, 999);
      setDateRef(d.getTime());
    }
    setModeTemps(m);
  };

  return (
    <div
      ref={ref}
      className={`glass absolute top-4 z-10 rounded-xl p-2 ${deplie ? "w-[340px] max-w-[86vw]" : ""}`}
      style={{ left: deplie ? 74 : 16, transform: `translate(${decal.x}px, ${decal.y}px)`, transition: "left .3s ease" }}
      data-testid="map-mode-switcher"
    >
      <div className="flex items-center gap-1">
        <button
          onPointerDown={surPoigneeDown}
          onDoubleClick={reinitialiser}
          title="Déplacer le panneau (double-clic : repositionner)"
          aria-label="Déplacer le panneau Calques"
          data-testid="calques-grip"
          className="flex h-7 w-5 shrink-0 cursor-grab touch-none items-center justify-center text-[#A3A39E] transition-colors hover:text-[#52524F] active:cursor-grabbing"
        >
          <DotsSixVertical size={13} />
        </button>
        <button
          onClick={() => setDeplie(!deplie)}
          data-testid="controle-toggle"
          title={deplie ? "Replier les réglages" : "Calques et réglages"}
          className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors ${deplie ? "bg-[#0E7490]/15 text-[#0E7490]" : "text-[#71716D] hover:bg-[#F0F0EE] hover:text-[#111110]"}`}
        >
          {deplie ? <X size={14} /> : <Stack size={14} />}
        </button>
        {!deplie && (
          <span className="px-1 font-code text-[10px] uppercase tracking-[0.15em] text-[#71716D]">Calques</span>
        )}
      </div>

      {focus && (
        <Link to="/atlas" className="mt-2 block px-1 font-code text-[10px] text-[#3730A3] hover:underline" data-testid="map-clear-focus">
          ← Retirer le filtre « {focus} »
        </Link>
      )}

      {deplie && (
        <div data-testid="controle-details">
          {mesh?.perimetre?.nb_restreints > 0 && (
            <div className="mt-2 rounded border border-dashed border-[#D4D4D0] px-2 py-1.5 font-code text-[9px] leading-relaxed text-[#71716D]" data-testid="badge-dependances-restreintes">
              {mesh.perimetre.nb_restreints} dépendance(s) restreinte(s) — politique « {mesh.perimetre.politique === "anonymisee" ? "dépendance anonymisée" : mesh.perimetre.politique === "resume" ? "résumé autorisé" : "masquage complet"} »
            </div>
          )}

          {/* Temps : Direct / Pause / Replay / Historique / Avant-Après */}
          <div className="mt-2 border-t border-[#E5E5E3] pt-2.5">
            <span className="px-1 font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Temps</span>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              {MODES_TEMPS.map(([id, label, Icon]) => (
                <button
                  key={id}
                  onClick={() => choisirMode(id)}
                  data-testid={id === "avantapres" ? "avant-apres-btn" : `${id}-btn`}
                  title={label}
                  className={`flex items-center gap-1 rounded px-2 py-1 font-code text-[10px] transition-colors ${
                    modeTemps === id
                      ? id === "direct" ? "bg-[#047857]/15 text-[#047857]"
                        : id === "pause" ? "bg-[#B45309]/15 text-[#B45309]"
                        : "bg-[#3730A3]/12 text-[#3730A3]"
                      : "text-[#71716D] hover:text-[#111110]"
                  }`}
                >
                  <Icon size={12} /> {label}
                </button>
              ))}
            </div>

            {(modeTemps === "historique" || modeTemps === "avantapres") && (
              <div className="mt-2 px-1">
                <input
                  type="date"
                  value={dateRef ? fmtDateInput(dateRef) : ""}
                  max={fmtDateInput(new Date())}
                  onChange={(e) => {
                    if (!e.target.value) return;
                    const d = new Date(`${e.target.value}T23:59:59`);
                    setDateRef(d.getTime());
                  }}
                  data-testid="temps-date-input"
                  className="h-7 w-full rounded border border-[#E5E5E3] bg-white px-2 font-code text-[10px] text-[#3F3F3C] focus:outline-none"
                />
                <p className="mt-1 font-code text-[9px] leading-relaxed text-[#71716D]" data-testid="temps-etat">
                  {modeTemps === "historique"
                    ? `Photographie du Mesh au ${dateRef ? fmtDate(dateRef) : "…"} — les relations plus récentes sont masquées.`
                    : `Référence : ${dateRef ? fmtDate(dateRef) : "…"} — les relations apparues depuis sont mises en évidence.`}
                </p>
              </div>
            )}

            {modeTemps === "replay" && (
              <div className="mt-2 flex items-center gap-2 px-1">
                <button
                  onClick={onRejouer}
                  data-testid="rejouer-btn"
                  className="flex items-center gap-1 rounded border border-[#3730A3]/40 px-2 py-1 font-code text-[10px] text-[#3730A3] transition-colors hover:bg-[#3730A3]/10"
                >
                  <Play size={11} /> Rejouer
                </button>
                <span className="font-code text-[9px] text-[#71716D]" data-testid="replay-etat">
                  {replaying ? `Relecture… ${dateRef ? fmtDate(dateRef) : ""}` : "Relecture terminée — état actuel du Mesh"}
                </span>
              </div>
            )}
          </div>

          {/* Couches de la carte — remplacent les catégories Google Maps :
              modifient visibilité et importance, jamais la position des jumeaux */}
          <div className="mt-2.5 border-t border-[#E5E5E3] pt-2.5">
            <div className="px-1 font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Couches de relations</div>
            <div className="mt-1.5 space-y-0.5">
              {[
                ["bcm", "BCM déclaré", "rgba(17,17,16,0.45)", "solid"],
                ["realite", "Réalité découverte", "#0E7490", "solid"],
                ["ecarts", "Écarts", "#D97706", "dashed"],
              ].map(([id, label, coul, st]) => (
                <button
                  key={id}
                  onClick={() => setCouchesRel((c) => ({ ...c, [id]: !c[id] }))}
                  data-testid={`couche-rel-${id}`}
                  className={`flex w-full items-center gap-2 rounded px-1 py-1 text-left transition-colors hover:bg-[#F0F0EE] ${couchesRel[id] ? "" : "opacity-45"}`}
                >
                  <span className="inline-block w-5 border-t-2" style={{ borderColor: coul, borderTopStyle: st }} />
                  <span className="text-[11px] text-[#52524F]">{label}</span>
                </button>
              ))}
            </div>
            <div className="mt-2 px-1 font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Couches cartographiques</div>
            <div className="mt-1.5 space-y-0.5">
              {[
                ["situations", "Situations", "#6D28D9"],
                ["capacites", "Capacités", "#0369A1"],
                ["transformations", "Transformations", "#B45309"],
              ].map(([id, label, coul]) => (
                <button
                  key={id}
                  onClick={() => setCouchesCarte((c) => ({ ...c, [id]: !c[id] }))}
                  data-testid={`couche-carte-${id}`}
                  className={`flex w-full items-center gap-2 rounded px-1 py-1 text-left transition-colors hover:bg-[#F0F0EE] ${couchesCarte[id] ? "" : "opacity-45"}`}
                >
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: coul }} />
                  <span className="text-[11px] text-[#52524F]">{label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="mt-2.5 border-t border-[#E5E5E3] pt-2.5">
            <div className="px-1 font-code text-[9px] uppercase tracking-[0.2em] text-[#71716D]">Dynamiques visibles</div>
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
                  <span className="text-[11px] text-[#52524F]">{label}</span>
                </label>
              ))}
            </div>
          </div>

          {!mesh?.perimetre?.global && (
            <div className="mt-2 flex gap-1.5 px-1">
              <input
                value={nomVue}
                onChange={(e) => setNomVue(e.target.value)}
                placeholder="Nom de la vue…"
                data-testid="nom-vue-input"
                className="h-7 w-full rounded border border-[#E5E5E3] bg-white px-2 text-[11px] text-[#111110] placeholder:text-[#71716D] focus:outline-none"
              />
              <button
                onClick={enregistrerVue}
                data-testid="enregistrer-vue-btn"
                className="h-7 shrink-0 rounded border border-[#E5E5E3] px-2 text-[10px] text-[#52524F] transition-colors hover:border-[#D4D4D0] hover:text-[#111110]"
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
