import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CaretLeft, CaretRight, Sparkle, Compass, ArrowRight, CalendarBlank, DotsThree, Eye, ArrowSquareOut, ArrowsLeftRight } from "@phosphor-icons/react";
import api from "@/lib/api";
import { usePerimetre } from "@/lib/perimetre";
import { useMesh } from "@/lib/mesh";
import { useContexte } from "@/lib/contexte";
import { couleurDomaine } from "@/lib/domaines";
import { fmtDateLongue, fmtDateInput, finDeJournee, fmtDate } from "@/lib/temps";

const GENRES = {
  relation: ["Découverte", "#0E7490"],
  contradiction: ["Contradiction", "#B91C1C"],
  connaissance: ["Connaissance", "#0369A1"],
  changement: ["Transformation", "#B45309"],
  incident: ["Incident", "#B91C1C"],
  comportement: ["Comportement", "#6D28D9"],
  phenomene: ["Phénomène possible", "#6D28D9"],
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

// Flore répond directement dans l'actualité — la conversation reste dans son contexte
function FilComprendre({ histoire }) {
  const [fil, setFil] = useState([]);
  const [q, setQ] = useState("");
  const [charge, setCharge] = useState(false);
  const [preuves, setPreuves] = useState(false);

  const demander = async (question) => {
    if (charge) return;
    setCharge(true);
    setFil((f) => [...f, { role: "moi", texte: question }]);
    try {
      const { data } = await api.post("/aurora/demander", {
        contexte: "actualites",
        question,
        selection: histoire.jumeaux || [],
      });
      setFil((f) => [...f, { role: "flore", data }]);
    } catch {
      setFil((f) => [...f, { role: "flore", data: { reponse: "Flore est indisponible pour le moment." } }]);
    } finally {
      setCharge(false);
    }
  };

  const init = useRef(false);
  useEffect(() => {
    if (init.current) return;
    init.current = true;
    demander(`Pourquoi est-ce important : ${histoire.titre} ?`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mt-3 space-y-2.5 border-t border-[#F0F0EE] pt-3" data-testid={`fil-comprendre-${histoire.id}`}>
      {fil.map((m, i) =>
        m.role === "moi" ? (
          <p key={i} className="text-right text-xs italic text-[#52524F]">« {m.texte} »</p>
        ) : (
          <div key={i} className="rounded-lg bg-[#EEECFA] p-3" data-testid={`fil-reponse-${histoire.id}-${i}`}>
            <div className="flex items-center gap-1.5 font-code text-[9px] uppercase tracking-[0.2em] text-[#312E81]">
              <Sparkle size={10} weight="fill" /> Flore
            </div>
            <p className="mt-1 text-xs leading-relaxed text-[#3F3F3C]">{m.data.reponse || m.data.texte}</p>
            {(m.data.contributions || []).length > 0 && (
              <>
                <button
                  onClick={() => setPreuves((p) => !p)}
                  data-testid={`fil-preuves-${histoire.id}-${i}`}
                  className="mt-2 flex items-center gap-1 font-code text-[10px] text-[#3730A3] hover:underline"
                >
                  <Eye size={11} /> {preuves ? "Masquer les preuves" : "Afficher les preuves"}
                </button>
                {preuves && (
                  <ul className="mt-1.5 space-y-1 border-l-2 border-[#3730A3]/25 pl-2.5">
                    {m.data.contributions.map((c, k) => (
                      <li key={k} className="font-code text-[10px] leading-snug text-[#52524F]">
                        <span className="font-semibold text-[#312E81]">{c.jumeau}</span> — {c.texte}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        )
      )}
      {charge && <p className="font-code text-[10px] text-[#71716D]">Flore consulte le Mesh…</p>}
      <form
        onSubmit={(e) => { e.preventDefault(); if (q.trim()) { demander(q.trim()); setQ(""); } }}
        className="flex gap-1.5"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Continuer : « Est-ce aussi vrai pour… ? »"
          data-testid={`fil-input-${histoire.id}`}
          className="h-8 w-full rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#111110] placeholder:text-[#71716D] focus:border-[#3730A3]/50 focus:outline-none"
        />
      </form>
    </div>
  );
}

function CarteHistoire({ h, vedette, dateCible, estAujourdhui, navigate, mesh }) {
  const [menu, setMenu] = useState(false);
  const [comprendre, setComprendre] = useState(false);
  const g = GENRES[h.genre] || [h.genre, "#71716D"];
  const lienAtlas = estAujourdhui ? h.liens?.atlas : h.liens?.atlas ? `${h.liens.atlas}${h.liens.atlas.includes("?") ? "&" : "?"}date=${fmtDateInput(finDeJournee(dateCible))}` : null;

  const actionPrincipale = () => {
    if (h.genre === "travail" || h.genre === "decision") {
      return (
        <button onClick={() => navigate(h.liens.travail)} data-testid={`histoire-reprendre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA]">
          Reprendre <ArrowRight size={11} />
        </button>
      );
    }
    if (h.incertain) {
      return (
        <button onClick={() => setComprendre(true)} data-testid={`histoire-suivre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#6D28D9] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#7C3AED]">
          Suivre la vérification
        </button>
      );
    }
    return (
      <button onClick={() => setComprendre((c) => !c)} data-testid={`histoire-comprendre-${h.id}`} className="flex items-center gap-1.5 rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA]">
        <Sparkle size={11} weight="fill" /> Comprendre
      </button>
    );
  };

  return (
    <article
      className={`rise rounded-xl border bg-white p-5 transition-colors ${vedette ? "border-[#3730A3]/25 shadow-sm" : "border-[#E5E5E3] hover:border-[#D4D4D0]"}`}
      data-testid={`histoire-${h.id}`}
    >
      <div className="flex items-center gap-2 font-code text-[9px] uppercase tracking-[0.2em]">
        <span className={`h-1.5 ${h.incertain ? "w-2.5 rounded-sm border border-dashed" : "w-1.5 rounded-full"}`} style={{ backgroundColor: h.incertain ? "transparent" : g[1], borderColor: g[1] }} />
        <span style={{ color: g[1] }}>{vedette ? `${g[0]} principale` : g[0]}</span>
        <span className="text-[#71716D]">· {heure(h.quand)}</span>
        {h.restreinte && <span className="rounded border border-[#B45309]/40 px-1 py-0.5 text-[#B45309]">périmètre partiel</span>}
      </div>
      <h3 className={`mt-2 font-semibold leading-snug text-[#111110] ${vedette ? "font-display text-lg" : "text-sm"}`}>{h.titre}</h3>
      {h.recit && <p className={`mt-1.5 leading-relaxed text-[#52524F] ${vedette ? "text-sm" : "text-xs"}`}>{h.recit}</p>}

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        {(h.jumeaux || []).slice(0, 5).map((jid) => {
          const j = mesh?.jumeaux.find((x) => x.id === jid);
          const c = couleurDomaine(j?.domaine);
          return (
            <span key={jid} className="rounded-full border px-1.5 py-0.5 font-code text-[9px]" style={{ color: c, borderColor: `${c}44`, backgroundColor: `${c}0D` }}>
              {j?.nom || jid}
            </span>
          );
        })}
        {h.confiance && <span className="ml-auto font-code text-[9px] text-[#71716D]">Confiance : {h.confiance}</span>}
      </div>

      <div className="mt-3 flex items-center gap-2 border-t border-[#F0F0EE] pt-3">
        {actionPrincipale()}
        <div className="relative">
          <button onClick={() => setMenu((m) => !m)} data-testid={`histoire-menu-${h.id}`} title="Autres actions" className="flex h-7 w-7 items-center justify-center rounded-md border border-[#E5E5E3] text-[#71716D] transition-colors hover:text-[#111110]">
            <DotsThree size={15} weight="bold" />
          </button>
          {menu && (
            <div className="glass absolute left-0 top-8 z-30 w-52 rounded-xl p-1.5" data-testid={`histoire-menu-panel-${h.id}`}>
              {lienAtlas && (
                <button onClick={() => navigate(lienAtlas)} data-testid={`histoire-atlas-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]">
                  <Compass size={12} /> Voir dans l'Atlas
                </button>
              )}
              {h.liens?.travail && (
                <button onClick={() => navigate(h.liens.travail)} data-testid={`histoire-travail-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]">
                  <ArrowSquareOut size={12} /> Ouvrir le travail
                </button>
              )}
              {h.liens?.investigation && (
                <button onClick={() => navigate(h.liens.investigation)} data-testid={`histoire-investigation-${h.id}`} className="flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-[11px] text-[#52524F] hover:bg-[#F0F0EE] hover:text-[#111110]">
                  <ArrowRight size={12} /> Approfondir
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {comprendre && <FilComprendre histoire={h} />}
    </article>
  );
}

export default function Actualites() {
  const navigate = useNavigate();
  const { version, persona } = usePerimetre();
  const { mesh } = useMesh();
  const { ouvrirFlore } = useContexte();
  const [decalage, setDecalage] = useState(0);
  const [jours, setJours] = useState(1);
  const [portee, setPortee] = useState("personnel");
  const [data, setData] = useState(null);
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
          setNouvelles((n) => n + r.data.histoires.filter((h) => !connus.has(h.id)).length);
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
  const sections = data?.sections || [];
  const vedetteId = sections.find((s) => s.id === "essentiel")?.histoires[0]?.id || histoires[0]?.id;
  const lienAtlasJournee = `/atlas?date=${fmtDateInput(finDeJournee(dateCible))}`;

  return (
    <div className="h-full overflow-y-auto px-6 py-8 pb-20 sm:px-8" data-testid="actualites-page">
      <div className="mx-auto max-w-3xl">
        {/* En-tête temporel */}
        <header className="rise">
          <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#3730A3]">Actualités</div>
          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <button onClick={() => setDecalage((d) => d + 1)} data-testid="date-prec-btn" title="Période précédente" className="flex h-9 w-9 items-center justify-center rounded-md border border-[#E5E5E3] bg-white text-[#52524F] transition-colors hover:text-[#111110]">
              <CaretLeft size={15} />
            </button>
            <h1 className="font-display text-3xl font-black tracking-tight text-[#111110]" data-testid="actualites-titre">{titrePage}</h1>
            <button onClick={() => setDecalage((d) => Math.max(0, d - 1))} disabled={decalage === 0} data-testid="date-suiv-btn" title="Période suivante" className="flex h-9 w-9 items-center justify-center rounded-md border border-[#E5E5E3] bg-white text-[#52524F] transition-colors hover:text-[#111110] disabled:opacity-30">
              <CaretRight size={15} />
            </button>
            <select value={presetActif} onChange={(e) => e.target.value && appliquerPreset(e.target.value)} data-testid="date-preset-select" className="h-9 rounded-md border border-[#E5E5E3] bg-white px-2.5 text-xs text-[#3F3F3C] focus:outline-none">
              <option value="" label="Période…" />
              {PRESETS.map(([v, l]) => <option key={v} value={v} label={l} />)}
            </select>
            <label className="flex items-center gap-1.5 text-xs text-[#71716D]">
              <CalendarBlank size={14} />
              <input type="date" value={fmtDateInput(dateCible)} max={fmtDateInput(new Date())}
                onChange={(e) => {
                  if (!e.target.value) return;
                  const d = new Date(`${e.target.value}T12:00:00`);
                  setDecalage(Math.max(0, Math.round((new Date().setHours(12, 0, 0, 0) - d.getTime()) / 86400000)));
                  setJours(1);
                }}
                data-testid="date-input" className="h-9 rounded-md border border-[#E5E5E3] bg-white px-2 text-xs text-[#3F3F3C] focus:outline-none" />
            </label>
          </div>

          {/* Trois portées très lisibles */}
          <div className="mt-4 flex flex-wrap items-center gap-2" data-testid="portees">
            {PORTEES.map(([id, label]) => (
              <button key={id} onClick={() => setPortee(id)} data-testid={`portee-${id}`}
                className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${portee === id ? "border-[#3730A3] bg-[#3730A3] text-white" : "border-[#E5E5E3] bg-white text-[#52524F] hover:text-[#111110]"}`}>
                {label}
              </button>
            ))}
            <span className="font-code text-[10px] text-[#71716D]" data-testid="portee-note">
              Vue limitée à vos autorisations{data?.espace_label ? ` · ${data.espace_label}` : ""}
            </span>
          </div>
          {data?.note_portee && <p className="mt-2 font-code text-[10px] text-[#B45309]" data-testid="portee-avertissement">{data.note_portee}</p>}
        </header>

        {/* Consultation historique : le direct est suspendu visuellement */}
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
        {estAujourdhui && nouvelles > 0 && (
          <button onClick={() => { charger(); setNouvelles(0); }} data-testid="nouvelles-actus-btn" className="rise mt-5 flex w-full items-center justify-center gap-2 rounded-xl border border-[#047857]/30 bg-[#E8F5E9] px-4 py-2.5 text-xs font-semibold text-[#1B4332] transition-colors hover:bg-[#D8EEDC]">
            <span className="pulse-soft h-1.5 w-1.5 rounded-full bg-[#047857]" />
            Mesh vivant — {nouvelles} nouvelle{nouvelles > 1 ? "s" : ""} actualité{nouvelles > 1 ? "s" : ""}
          </button>
        )}

        {/* Le briefing de Flore — rédigé, adapté au rôle */}
        {data?.briefing && (
          <section className="rise mt-7" data-testid="briefing-flore">
            <h2 className="font-display text-xl font-bold text-[#111110]">{data.briefing.salutation}</h2>
            <div className="mt-1 flex items-center gap-2">
              <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#3730A3]">{data.briefing.titre}</span>
              <span className="rounded-full border border-[#E5E5E3] px-2 py-0.5 font-code text-[9px] text-[#71716D]">{data.briefing.lecture}</span>
            </div>
            <p className="mt-2.5 text-sm leading-relaxed text-[#3F3F3C]">{data.briefing.texte}</p>
            {data.briefing.points.length > 0 && (
              <ul className="mt-2 space-y-1">
                {data.briefing.points.map((p, i) => (
                  <li key={i} className="flex gap-2 text-xs text-[#52524F]" data-testid={`briefing-point-${i}`}>
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[#3730A3]" />{p}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-3.5 flex flex-wrap gap-2">
              <button
                onClick={() => { window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: `Résume-moi ${jours > 1 ? "cette période" : "cette journée"} dans le Mesh.` })); ouvrirFlore(); }}
                data-testid="briefing-explorer-btn"
                className="flex items-center gap-1.5 rounded-full bg-[#3730A3] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA]"
              >
                <Sparkle size={12} weight="fill" /> Explorer {jours > 1 ? "la période" : "la journée"} avec Flore
              </button>
              <button onClick={() => navigate(lienAtlasJournee)} data-testid="voir-journee-atlas-btn" className="flex items-center gap-1.5 rounded-full border border-[#0E7490]/30 bg-[#0E7490]/[0.06] px-4 py-2 text-xs font-semibold text-[#0E7490] transition-colors hover:bg-[#0E7490]/15">
                <Compass size={12} /> Voir {jours > 1 ? "la période" : "la journée"} dans l'Atlas
              </button>
            </div>
          </section>
        )}

        {/* Synthèse de période : pas sept feeds collés */}
        {data?.synthese && (
          <section className="rise mt-7 rounded-xl border border-[#E5E5E3] bg-white p-5" data-testid="synthese-periode">
            <div className="font-code text-[10px] uppercase tracking-[0.2em] text-[#71716D]">Synthèse de la période</div>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[["relations", "nouvelles relations"], ["transformations", "transformations"], ["decisions", "décisions prises"], ["surveillance", "points à surveiller"]].map(([k, l]) => (
                <div key={k}>
                  <div className="font-display text-2xl font-black text-[#111110]" data-testid={`synthese-${k}`}>{data.synthese[k]}</div>
                  <div className="font-code text-[9px] uppercase tracking-wider text-[#71716D]">{l}</div>
                </div>
              ))}
            </div>
            {data.synthese.tendance && (
              <p className="mt-3 border-l-2 border-[#3730A3]/30 pl-3 text-xs italic text-[#3F3F3C]" data-testid="synthese-tendance">
                <span className="font-code text-[9px] not-italic uppercase tracking-wider text-[#3730A3]">Tendance principale — </span>{data.synthese.tendance}
              </p>
            )}
            <div className="mt-4 flex gap-2">
              <button onClick={() => navigate(`/atlas?avant-apres=${data.synthese.debut}`)} data-testid="comparer-atlas-btn" className="flex items-center gap-1.5 rounded-md bg-[#3730A3] px-3 py-1.5 text-[11px] font-semibold text-white transition-colors hover:bg-[#4338CA]">
                <ArrowsLeftRight size={12} /> Comparer le {fmtDate(data.synthese.debut)} et le {fmtDate(data.synthese.fin)}
              </button>
            </div>
          </section>
        )}

        {/* Feed organisé par signification */}
        <div className="mt-8 space-y-8" data-testid="feed-actualites">
          {sections.map((s) => (
            <section key={s.id} data-testid={`section-${s.id}`}>
              <h2 className="font-code text-[10px] uppercase tracking-[0.25em] text-[#52524F]">{s.titre}</h2>
              <div className="mt-3 space-y-4">
                {s.histoires.map((h) => (
                  <CarteHistoire key={h.id} h={h} vedette={h.id === vedetteId} dateCible={dateCible} estAujourdhui={estAujourdhui} navigate={navigate} mesh={mesh} />
                ))}
              </div>
            </section>
          ))}

          {data && histoires.length === 0 && (
            <div className="rounded-xl border border-dashed border-[#D4D4D0] bg-white p-10 text-center" data-testid="feed-vide">
              <p className="font-display text-base font-bold text-[#111110]">Rien d'important ne nécessite votre attention.</p>
              <p className="mt-2 text-xs leading-relaxed text-[#52524F]">
                Le Mesh reste actif : {data.mesh?.jumeaux_actifs ?? "—"} jumeaux actualisés dans votre périmètre, aucune transformation significative sur la période.
              </p>
              <button onClick={() => navigate("/atlas")} data-testid="explorer-mesh-btn" className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-[#3730A3] px-4 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#4338CA]">
                <Compass size={12} /> Explorer le Mesh
              </button>
            </div>
          )}
          {!data && <p className="py-10 text-center font-code text-[11px] text-[#71716D]" data-testid="feed-chargement">Flore prépare votre briefing…</p>}
        </div>
      </div>
    </div>
  );
}
