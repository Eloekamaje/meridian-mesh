import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CaretLeft, CaretRight, Sparkle, Compass, ArrowRight, CalendarBlank } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useMesh } from "@/lib/mesh";
import { couleurDomaine } from "@/lib/domaines";
import { fmtDateLongue, fmtDateInput, finDeJournee } from "@/lib/temps";

const GENRES = {
  relation: ["Relation", "#0E7490"],
  contradiction: ["Contradiction", "#B91C1C"],
  connaissance: ["Connaissance", "#0369A1"],
  changement: ["Changement", "#B45309"],
  incident: ["Incident", "#B91C1C"],
  comportement: ["Comportement", "#6D28D9"],
  travail: ["Travail", "#3730A3"],
  decision: ["Décision", "#6D28D9"],
  gouvernance: ["Gouvernance", "#71716D"],
};

const PORTEES = [
  ["personnel", "Personnel"],
  ["espace", "Mon espace"],
  ["global", "Mesh global"],
];

const PRESETS = [
  ["aujourdhui", "Aujourd'hui"],
  ["hier", "Hier"],
  ["avant-hier", "Il y a 2 jours"],
  ["7j", "7 derniers jours"],
  ["30j", "30 derniers jours"],
];

const heure = (iso) => new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

export default function Actualites() {
  const navigate = useNavigate();
  const { version, persona } = usePerimetre();
  const { mesh } = useMesh();
  const [decalage, setDecalage] = useState(0); // jours avant aujourd'hui
  const [jours, setJours] = useState(1);
  const [portee, setPortee] = useState("personnel");
  const [data, setData] = useState(null);
  const [resumeOuvert, setResumeOuvert] = useState(false);
  const [nouvelles, setNouvelles] = useState(0);

  const dateCible = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - decalage);
    return d;
  }, [decalage]);
  const estAujourdhui = decalage === 0 && jours === 1;

  const charger = useCallback(() => {
    const p = new URLSearchParams({ date: fmtDateInput(dateCible), jours: String(jours), portee });
    return api.get(`/actualites?${p}`).then((r) => setData(r.data)).catch(() => {});
  }, [dateCible, jours, portee]);

  useEffect(() => {
    setResumeOuvert(false);
    setNouvelles(0);
    charger();
  }, [charger, version, persona]);

  // Temps réel calme : les nouvelles actualités attendent un geste de l'utilisateur
  useEffect(() => {
    if (!estAujourdhui) return undefined;
    const t = setInterval(() => {
      const p = new URLSearchParams({ date: fmtDateInput(dateCible), jours: "1", portee });
      api.get(`/actualites?${p}`).then((r) => {
        setData((cur) => {
          if (!cur) return cur;
          const connus = new Set(cur.histoires.map((h) => h.id));
          const fraiches = r.data.histoires.filter((h) => !connus.has(h.id));
          if (fraiches.length) setNouvelles((n) => n + fraiches.length);
          return cur;
        });
      }).catch(() => {});
    }, 15000);
    return () => clearInterval(t);
  }, [estAujourdhui, dateCible, portee]);

  const appliquerPreset = (v) => {
    if (v === "aujourdhui") { setDecalage(0); setJours(1); }
    else if (v === "hier") { setDecalage(1); setJours(1); }
    else if (v === "avant-hier") { setDecalage(2); setJours(1); }
    else if (v === "7j") { setDecalage(0); setJours(7); }
    else if (v === "30j") { setDecalage(0); setJours(30); }
  };

  const presetActif =
    decalage === 0 && jours === 1 ? "aujourdhui"
    : decalage === 1 && jours === 1 ? "hier"
    : decalage === 2 && jours === 1 ? "avant-hier"
    : decalage === 0 && jours === 7 ? "7j"
    : decalage === 0 && jours === 30 ? "30j" : "";

  const titrePage = useMemo(() => {
    if (jours > 1) {
      const debut = new Date(dateCible);
      debut.setDate(debut.getDate() - jours + 1);
      return `Du ${debut.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })} au ${dateCible.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`;
    }
    if (decalage === 0) return `Aujourd'hui · ${fmtDateLongue(dateCible)}`;
    if (decalage === 1) return `Hier · ${fmtDateLongue(dateCible)}`;
    return fmtDateLongue(dateCible);
  }, [decalage, jours, dateCible]);

  const histoires = data?.histoires || [];
  const lienAtlas = `/atlas?date=${fmtDateInput(finDeJournee(dateCible))}`;

  const comprendre = (h) =>
    window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: `Explique-moi : ${h.titre}` }));

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-16" data-testid="actualites-page">
      <div className="mx-auto max-w-4xl">
        {/* En-tête temporel */}
        <header className="rise">
          <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#0E7490]">Actualités du Mesh</div>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <button
              onClick={() => setDecalage((d) => d + 1)}
              data-testid="date-prec-btn"
              title="Période précédente"
              className="flex h-9 w-9 items-center justify-center rounded-md border border-[#E5E5E3] bg-white text-[#52524F] transition-colors hover:text-[#111110]"
            >
              <CaretLeft size={15} />
            </button>
            <h1 className="font-display text-3xl font-black tracking-tight text-[#111110]" data-testid="actualites-titre">{titrePage}</h1>
            <button
              onClick={() => setDecalage((d) => Math.max(0, d - 1))}
              disabled={decalage === 0}
              data-testid="date-suiv-btn"
              title="Période suivante"
              className="flex h-9 w-9 items-center justify-center rounded-md border border-[#E5E5E3] bg-white text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-30"
            >
              <CaretRight size={15} />
            </button>
            <select
              value={presetActif}
              onChange={(e) => e.target.value && appliquerPreset(e.target.value)}
              data-testid="date-preset-select"
              className="h-9 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#3F3F3C] focus:outline-none"
            >
              <option value="" label="Période…" />
              {PRESETS.map(([v, l]) => <option key={v} value={v} label={l} />)}
            </select>
            <label className="flex items-center gap-1.5 text-xs text-[#71716D]">
              <CalendarBlank size={14} />
              <input
                type="date"
                value={fmtDateInput(dateCible)}
                max={fmtDateInput(new Date())}
                onChange={(e) => {
                  if (!e.target.value) return;
                  const d = new Date(`${e.target.value}T12:00:00`);
                  const diff = Math.round((new Date().setHours(12, 0, 0, 0) - d.getTime()) / 86400000);
                  setDecalage(Math.max(0, diff));
                  setJours(1);
                }}
                data-testid="date-input"
                className="h-9 rounded-md border border-[#E5E5E3] bg-white px-2 text-xs text-[#3F3F3C] focus:outline-none"
              />
            </label>
          </div>

          {/* Portées organisationnelles */}
          <div className="mt-4 flex flex-wrap items-center gap-2" data-testid="portees">
            {PORTEES.map(([id, label]) => (
              <button
                key={id}
                onClick={() => setPortee(id)}
                data-testid={`portee-${id}`}
                className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${
                  portee === id ? "border-[#3730A3]/60 bg-[#3730A3] text-white" : "border-[#E5E5E3] bg-white text-[#52524F] hover:text-[#111110]"
                }`}
              >
                {label}
              </button>
            ))}
            <span className="font-code text-[10px] text-[#71716D]" data-testid="portee-note">
              Vue limitée à vos autorisations{data?.espace_label ? ` · ${data.espace_label}` : ""}
            </span>
          </div>
          {data?.note_portee && (
            <p className="mt-2 font-code text-[10px] text-[#B45309]" data-testid="portee-avertissement">{data.note_portee}</p>
          )}
        </header>

        {/* Banniere historique */}
        {!estAujourdhui && (
          <div className="mt-5 flex items-center justify-between rounded-xl border border-[#B45309]/30 bg-[#FFFBEB] px-4 py-2.5" data-testid="banniere-historique">
            <span className="text-xs text-[#B45309]">
              Vous consultez {jours > 1 ? "une période passée" : `le ${dateCible.toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`} — le direct est suspendu.
            </span>
            <button onClick={() => appliquerPreset("aujourdhui")} data-testid="retour-aujourdhui-btn" className="rounded-md border border-[#B45309]/40 px-2.5 py-1 text-[11px] font-semibold text-[#B45309] transition-colors hover:bg-[#B45309]/10">
              Revenir à aujourd'hui
            </button>
          </div>
        )}

        {/* Insertion temps réel sans interruption */}
        {estAujourdhui && nouvelles > 0 && (
          <button
            onClick={() => { charger(); setNouvelles(0); }}
            data-testid="nouvelles-actus-btn"
            className="rise mt-5 flex w-full items-center justify-center gap-2 rounded-xl border border-[#047857]/30 bg-[#E8F5E9] px-4 py-2.5 text-xs font-semibold text-[#1B4332] transition-colors hover:bg-[#D8EEDC]"
          >
            <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#047857]" />
            Mesh vivant — {nouvelles} nouvelle{nouvelles > 1 ? "s" : ""} actualité{nouvelles > 1 ? "s" : ""}
          </button>
        )}

        {/* Actions de lecture */}
        <div className="mt-6 flex flex-wrap items-center gap-2">
          <button
            onClick={() => setResumeOuvert((o) => !o)}
            data-testid="resume-flore-btn"
            className="flex items-center gap-1.5 rounded-full border border-[#3730A3]/30 bg-[#EEECFA] px-3.5 py-1.5 text-xs font-semibold text-[#312E81] transition-colors hover:bg-[#3730A3] hover:text-white"
          >
            <Sparkle size={12} weight="fill" /> Résumé par Flore
          </button>
          <button
            onClick={() => navigate(lienAtlas)}
            data-testid="voir-journee-atlas-btn"
            className="flex items-center gap-1.5 rounded-full border border-[#0E7490]/30 bg-[#0E7490]/[0.06] px-3.5 py-1.5 text-xs font-semibold text-[#0E7490] transition-colors hover:bg-[#0E7490]/15"
          >
            <Compass size={12} /> Voir {jours > 1 ? "la période" : "la journée"} dans l'Atlas
          </button>
        </div>

        {resumeOuvert && data?.resume_flore && (
          <div className="rise mt-3 rounded-xl border border-[#3730A3]/25 bg-[#EEECFA] p-4" data-testid="resume-flore-panel">
            <div className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-[#312E81]">
              <Sparkle size={12} weight="fill" /> Flore — lecture de la période
            </div>
            <p className="mt-2 text-sm leading-relaxed text-[#3F3F3C]">{data.resume_flore.texte}</p>
          </div>
        )}

        {/* Feed narratif */}
        <div className="mt-6 space-y-3" data-testid="feed-actualites">
          {histoires.map((h, i) => {
            const g = GENRES[h.genre] || [h.genre, "#71716D"];
            return (
              <article key={h.id} className="rise rounded-xl border border-[#E5E5E3] bg-white p-4" style={{ animationDelay: `${Math.min(i, 8) * 50}ms` }} data-testid={`histoire-${h.id}`}>
                <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.2em]">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: g[1] }} />
                  <span style={{ color: g[1] }}>{g[0]}</span>
                  <span className="text-[#71716D]">· {heure(h.quand)}</span>
                  {h.restreinte && <span className="rounded border border-[#B45309]/40 px-1 py-0.5 text-[#B45309]">périmètre partiel</span>}
                </div>
                <h3 className="mt-1.5 text-sm font-semibold leading-snug text-[#111110]">{h.titre}</h3>
                {h.recit && <p className="mt-1 text-xs leading-relaxed text-[#52524F]">{h.recit}</p>}
                {(h.jumeaux || []).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {h.jumeaux.slice(0, 5).map((jid) => {
                      const j = mesh?.jumeaux.find((x) => x.id === jid);
                      const nom = j?.nom || jid;
                      const c = couleurDomaine(j?.domaine);
                      return (
                        <span key={jid} className="rounded-full border px-1.5 py-0.5 font-code text-[9px]" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}0D` }}>
                          {nom}
                        </span>
                      );
                    })}
                  </div>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[#F0F0EE] pt-2.5">
                  <button
                    onClick={() => comprendre(h)}
                    data-testid={`histoire-comprendre-${h.id}`}
                    className="flex items-center gap-1 rounded-md bg-[#3730A3] px-2.5 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA]"
                  >
                    <Sparkle size={11} weight="fill" /> Comprendre
                  </button>
                  {h.liens?.atlas && (
                    <button
                      onClick={() => navigate(estAujourdhui ? h.liens.atlas : `${h.liens.atlas}${h.liens.atlas.includes("?") ? "&" : "?"}date=${fmtDateInput(finDeJournee(dateCible))}`)}
                      data-testid={`histoire-atlas-${h.id}`}
                      className="flex items-center gap-1 rounded-md border border-[#E5E5E3] px-2.5 py-1.5 text-[11px] text-[#52524F] transition-colors hover:border-[#0E7490]/50 hover:text-[#0E7490]"
                    >
                      <Compass size={11} /> Voir dans l'Atlas
                    </button>
                  )}
                  {h.liens?.travail && (
                    <button
                      onClick={() => navigate(h.liens.travail)}
                      data-testid={`histoire-travail-${h.id}`}
                      className="flex items-center gap-1 rounded-md border border-[#E5E5E3] px-2.5 py-1.5 text-[11px] text-[#52524F] transition-colors hover:text-[#111110]"
                    >
                      Ouvrir le travail <ArrowRight size={10} />
                    </button>
                  )}
                  {h.liens?.investigation && (
                    <button
                      onClick={() => navigate(h.liens.investigation)}
                      data-testid={`histoire-investigation-${h.id}`}
                      className="flex items-center gap-1 rounded-md border border-[#E5E5E3] px-2.5 py-1.5 text-[11px] text-[#52524F] transition-colors hover:text-[#111110]"
                    >
                      Approfondir <ArrowRight size={10} />
                    </button>
                  )}
                </div>
              </article>
            );
          })}
          {data && histoires.length === 0 && (
            <div className="rounded-xl border border-dashed border-[#D4D4D0] bg-white p-10 text-center" data-testid="feed-vide">
              <p className="text-sm text-[#52524F]">Aucune actualité sur cette période dans votre périmètre.</p>
              <p className="mt-1 font-code text-[10px] text-[#71716D]">Le Mesh est resté calme — essayez une autre date ou une autre portée.</p>
            </div>
          )}
          {!data && <p className="py-10 text-center font-code text-[11px] text-[#71716D]" data-testid="feed-chargement">Lecture du Mesh…</p>}
        </div>
      </div>
    </div>
  );
}
