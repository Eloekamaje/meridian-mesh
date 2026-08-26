import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Compass, Sparkle, ArrowRight, Warning, ClockCounterClockwise, Briefcase, Scales, Pulse } from "@phosphor-icons/react";
import api from "@/lib/api";
import { useMesh } from "@/lib/mesh";
import { usePerimetre } from "@/lib/perimetre";
import { couleurDomaine } from "@/lib/domaines";
import { TYPES_CASE, STATUTS_CASE } from "./Cases";

const rel = (iso) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 3600) return `il y a ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  return `il y a ${Math.round(s / 86400)} j`;
};

function Section({ titre, accent, action, children, testid }) {
  return (
    <section className="rounded-xl border border-white/[0.07] bg-white/[0.015] p-4" data-testid={testid}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.2em] text-white/45">
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent }} />
          {titre}
        </div>
        {action}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

export default function Aujourdhui() {
  const navigate = useNavigate();
  const { jumeauPar } = useMesh();
  const { version, info, persona } = usePerimetre();
  const [cases, setCases] = useState([]);
  const [situations, setSituations] = useState([]);
  const [jumeaux, setJumeaux] = useState([]);
  const [journal, setJournal] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [activite, setActivite] = useState([]);

  useEffect(() => {
    api.get("/cases").then((r) => setCases(r.data)).catch(() => {});
    api.get("/situations").then((r) => setSituations(r.data.filter((s) => !["ignorée", "classée", "décidée"].includes(s.statut)))).catch(() => {});
    api.get("/jumeaux").then((r) => setJumeaux(r.data)).catch(() => {});
    api.get("/journal").then((r) => setJournal(r.data)).catch(() => {});
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
    api.get("/aurora/suggestions?contexte=aujourdhui").then((r) => setSuggestions(r.data)).catch(() => {});
  }, [version]);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const { data } = await api.get("/activite");
        if (!stop) setActivite((prev) => [...data, ...prev].slice(0, 6));
      } catch {}
    };
    tick();
    const t = setInterval(tick, 8000);
    return () => { stop = true; clearInterval(t); };
  }, [version]);

  const moi = personas.find((p) => p.id === persona);
  const mesCases = cases.filter((c) => c.responsable === persona);
  const casesMontres = (mesCases.length ? mesCases : cases).slice(0, 4);
  const casesEnCours = cases.filter((c) => c.statut === "en_cours");
  const decisionsAttente = [
    ...situations.filter((s) => s.verbe === "a_decider").map((s) => ({ id: s.id, titre: s.titre, detail: s.detectee, lien: `/investigations/${s.id}`, origine: "Situation" })),
    ...cases.filter((c) => c.statut === "en_cours" && c.nb_options > 0 && c.nb_decisions === 0).map((c) => ({ id: c.id, titre: c.titre, detail: `${c.nb_options} option(s) à trancher`, lien: `/cases/${c.id}`, origine: "Case" })),
  ];
  const decouvertes = situations.filter((s) => s.verbe === "decouvert");
  const alertes = jumeaux.filter(
    (j) => (j.couverture ?? 100) < 60 || ["retard", "obsolete"].includes(j.fraicheur_etat) || (j.sources_detail || []).some((s) => s.statut !== "prete")
  );

  const kpis = [
    { label: "Cases en cours", valeur: casesEnCours.length, couleur: "#FBBF24", testid: "kpi-cases" },
    { label: "Décisions en attente", valeur: decisionsAttente.length, couleur: "#A78BFA", testid: "kpi-decisions" },
    { label: "Nouvelles découvertes", valeur: decouvertes.length, couleur: "#22D3EE", testid: "kpi-decouvertes" },
    { label: "Alertes de connaissance", valeur: alertes.length, couleur: "#F87171", testid: "kpi-alertes" },
  ];

  return (
    <div className="h-full overflow-y-auto px-8 py-8 pb-16" data-testid="aujourdhui-page">
      <header className="rise">
        <div className="font-code text-[10px] uppercase tracking-[0.3em] text-[#22D3EE]">
          {new Date().toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
        </div>
        <h1 className="mt-1 font-display text-4xl font-black text-white" data-testid="aujourdhui-titre">
          Bonjour{moi ? `, ${moi.nom}` : ""}
        </h1>
        <p className="mt-2 text-base text-white/50">Voici ce qui mérite votre attention aujourd'hui.</p>
        {info && !info.espace.global && (
          <div className="mt-3 flex flex-wrap items-center gap-2" data-testid="mon-espace-strip">
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 font-code text-[10px] text-white/55">
              Mon espace · {info.espace.label} — {info.nb_autorises} jumeaux autorisés
            </span>
          </div>
        )}
      </header>

      {/* KPIs */}
      <div className="mt-6 grid grid-cols-2 gap-3 xl:grid-cols-4" data-testid="aujourdhui-kpis">
        {kpis.map((k, i) => (
          <div key={k.testid} className="rise rounded-xl border border-white/[0.07] bg-white/[0.015] px-4 py-3.5" style={{ animationDelay: `${i * 70}ms` }} data-testid={k.testid}>
            <div className="font-display text-2xl font-bold" style={{ color: k.couleur }}>{k.valeur}</div>
            <div className="mt-0.5 font-code text-[10px] uppercase tracking-[0.15em] text-white/40">{k.label}</div>
          </div>
        ))}
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-2">
        <div className="space-y-5">
          {/* Mes cases */}
          <Section
            titre={mesCases.length ? "Mes cases" : "Cases récents"}
            accent="#FBBF24"
            testid="section-mes-cases"
            action={<Link to="/cases" className="flex items-center gap-1 font-code text-[10px] text-white/40 transition-colors hover:text-white" data-testid="voir-cases">Tous les cases <ArrowRight size={11} /></Link>}
          >
            <div className="space-y-2">
              {casesMontres.map((c) => {
                const t = TYPES_CASE[c.type] || [c.type, "#9CA3AF"];
                const s = STATUTS_CASE[c.statut] || [c.statut, "#9CA3AF"];
                return (
                  <div key={c.id} onClick={() => navigate(`/cases/${c.id}`)} data-testid={`case-attention-${c.id}`} className="cursor-pointer rounded-lg border border-white/[0.07] p-3 transition-colors hover:border-white/20 hover:bg-white/[0.02]">
                    <div className="flex items-center gap-2">
                      <span className="rounded border px-1.5 py-0.5 font-code text-[9px] uppercase" style={{ color: t[1], borderColor: `${t[1]}44` }}>{t[0]}</span>
                      <span className="flex items-center gap-1 text-[10px]" style={{ color: s[1] }}><span className="h-1 w-1 rounded-full" style={{ backgroundColor: s[1] }} />{s[0]}</span>
                      {c.a_revoir && <span className="rounded border border-[#F87171]/40 bg-[#F87171]/[0.08] px-1.5 py-0.5 font-code text-[9px] uppercase text-[#F87171]" data-testid={`case-arevoir-${c.id}`}>À revoir</span>}
                      <span className="ml-auto font-code text-[9px] text-white/30">{rel(c.maj_le)}</span>
                    </div>
                    <div className="mt-1.5 text-sm font-semibold text-white/90">{c.titre}</div>
                  </div>
                );
              })}
              {casesMontres.length === 0 && <p className="text-xs text-white/30">Aucun case — créez-en un depuis une conversation avec Flore.</p>}
            </div>
          </Section>

          {/* Décisions en attente */}
          <Section titre="Décisions en attente" accent="#A78BFA" testid="section-decisions-attente">
            <div className="space-y-2">
              {decisionsAttente.map((d) => (
                <div key={`${d.origine}-${d.id}`} onClick={() => navigate(d.lien)} data-testid={`decision-attente-${d.id}`} className="flex cursor-pointer items-center gap-3 rounded-lg border border-white/[0.07] p-3 transition-colors hover:border-[#A78BFA]/40 hover:bg-white/[0.02]">
                  <Scales size={14} className="shrink-0 text-[#A78BFA]" />
                  <div className="min-w-0">
                    <div className="truncate text-sm text-white/85">{d.titre}</div>
                    <div className="font-code text-[9px] text-white/35">{d.origine} · {d.detail}</div>
                  </div>
                </div>
              ))}
              {decisionsAttente.length === 0 && <p className="text-xs text-white/30">Aucune décision en attente.</p>}
            </div>
          </Section>

          {/* Nouvelles découvertes */}
          <Section titre="Nouvelles découvertes" accent="#22D3EE" testid="section-decouvertes">
            <div className="space-y-2">
              {decouvertes.map((s) => (
                <div key={s.id} className="rounded-lg border border-white/[0.07] p-3" data-testid={`decouverte-${s.id}`}>
                  <div className="cursor-pointer text-sm font-semibold text-white/90 hover:text-white" onClick={() => navigate(`/investigations/${s.id}`)}>{s.titre}</div>
                  <div className="mt-1 flex items-center justify-between">
                    <span className="font-code text-[9px] text-white/35">{s.detectee}</span>
                    {(s.jumeaux || []).length > 0 && (
                      <button onClick={() => navigate(`/atlas?situation=${s.id}`)} data-testid={`voir-atlas-${s.id}`} className="flex items-center gap-1 font-code text-[10px] text-white/40 transition-colors hover:text-[#22D3EE]">
                        <Compass size={11} /> Voir dans l'Atlas
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {decouvertes.length === 0 && <p className="text-xs text-white/30">Aucune nouvelle découverte.</p>}
            </div>
          </Section>
        </div>

        <div className="space-y-5">
          {/* Alertes de connaissance */}
          <Section titre="Alertes de connaissance" accent="#F87171" testid="section-alertes">
            <div className="space-y-2">
              {alertes.slice(0, 5).map((j) => (
                <div key={j.id} onClick={() => navigate(`/jumeaux/${j.id}/revue`)} data-testid={`alerte-${j.id}`} className="flex cursor-pointer items-center gap-3 rounded-lg border border-white/[0.07] p-3 transition-colors hover:border-[#F87171]/40 hover:bg-white/[0.02]">
                  <Warning size={14} className="shrink-0 text-[#F87171]" />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm text-white/85">{j.nom}</div>
                    <div className="truncate font-code text-[9px] text-white/40">
                      connaissance {j.couverture} %
                      {(j.sources_detail || []).some((s) => s.statut !== "prete") && " · source(s) à reprendre"}
                      {["retard", "obsolete"].includes(j.fraicheur_etat) && " · fraîcheur en retard"}
                    </div>
                  </div>
                  <span className="font-code text-[9px]" style={{ color: couleurDomaine(j.domaine) }}>{j.domaine}</span>
                </div>
              ))}
              {alertes.length === 0 && <p className="text-xs text-white/30">Aucune alerte — la connaissance du périmètre est saine.</p>}
            </div>
          </Section>

          {/* Activité des jumeaux */}
          <Section titre="Activité des jumeaux" accent="#10B981" testid="section-activite">
            <ul className="space-y-2">
              {activite.map((e, i) => {
                const j = jumeauPar(e.jumeau);
                return (
                  <li key={`${e.jumeau}-${i}`} className="flex items-start gap-2 text-xs" data-testid={`activite-${i}`}>
                    <Pulse size={12} className="mt-0.5 shrink-0 text-[#10B981]" />
                    <span className="text-white/60"><span className="font-code" style={{ color: couleurDomaine(j?.domaine) }}>{j?.nom || e.jumeau}</span> — {e.texte}</span>
                  </li>
                );
              })}
              {activite.length === 0 && <li className="text-xs text-white/30">En écoute du Mesh…</li>}
            </ul>
          </Section>

          {/* Suggestions de Flore */}
          <Section titre="Suggestions de Flore" accent="#3B82F6" testid="section-suggestions-flore">
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => window.dispatchEvent(new CustomEvent("meridian:flore-ask", { detail: s }))}
                  data-testid={`suggestion-flore-${i}`}
                  className="rounded-full border border-[#3B82F6]/30 bg-[#3B82F6]/[0.06] px-3 py-1.5 text-[11px] text-[#7FB3FA] transition-colors hover:bg-[#3B82F6]/15 hover:text-white"
                >
                  <Sparkle size={10} className="mr-1 inline" /> {s}
                </button>
              ))}
            </div>
          </Section>

          {/* Changements sur le périmètre */}
          <Section titre="Changements sur le périmètre" accent="#94A3B8" testid="section-changements">
            <ul className="space-y-2">
              {journal.slice(0, 5).map((j, i) => (
                <li key={i} className="flex items-start gap-2 text-xs" data-testid={`journal-${i}`}>
                  <ClockCounterClockwise size={12} className="mt-0.5 shrink-0 text-white/30" />
                  <span className="text-white/55"><span className="font-code text-white/80">{j.persona}</span> · {j.action} — {j.cible}</span>
                </li>
              ))}
              {journal.length === 0 && <li className="text-xs text-white/30">Aucun changement récent.</li>}
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
