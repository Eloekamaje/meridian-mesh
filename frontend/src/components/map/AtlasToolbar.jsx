import { useState } from "react";
import { Hand, Lasso, Crosshair, Article, PencilSimple, Star, ClockCounterClockwise, SealQuestion, WarningDiamond, Bookmarks, DotsSixVertical } from "@phosphor-icons/react";
import useGlissable from "./useGlissable";

const OUTILS = [
  { id: "deplacement", icon: Hand, label: "Déplacement" },
  { id: "lasso", icon: Lasso, label: "Sélection multiple / lasso" },
  { id: "recentrage", icon: Crosshair, label: "Recentrage" },
];

// Bibliothèque personnelle (popover) : favoris, récents, investigations, situations
const LISTES = [
  { id: "favoris", icon: Star, label: "Favoris" },
  { id: "recents", icon: ClockCounterClockwise, label: "Consultés récemment" },
  { id: "investigations", icon: SealQuestion, label: "Investigations en cours" },
  { id: "situations", icon: WarningDiamond, label: "Situations actives" },
];

export default function AtlasToolbar({ outil, setOutil, rfRef, onExpliquer, expliquerOuvert, modeEdition, setModeEdition, vueListe, onOuvrirListe, conteneurRef }) {
  const [biblioOuverte, setBiblioOuverte] = useState(false);
  // Barre glissable : poignée en tête, position mémorisée entre les sessions.
  // Ancrage FIXE (façon Google Maps) : la barre ne bouge jamais d'elle-même.
  const { ref, decal, surPoigneeDown, reinitialiser } = useGlissable("toolbar", conteneurRef);

  return (
    <div
      ref={ref}
      className="absolute z-10"
      style={{
        left: 16,
        top: "50%",
        transform: `translateY(-50%) translate(${decal.x}px, ${decal.y}px)`,
      }}
      data-testid="map-toolbar"
    >
      <div className="glass flex flex-col gap-1 rounded-xl p-1.5">
        <button
          onPointerDown={surPoigneeDown}
          onDoubleClick={reinitialiser}
          title="Déplacer la barre (double-clic : repositionner)"
          aria-label="Déplacer la barre d'outils"
          data-testid="toolbar-grip"
          className="flex h-5 w-8 shrink-0 cursor-grab touch-none items-center justify-center text-[#5B7089] transition-colors hover:text-[#94A3B8] active:cursor-grabbing"
        >
          <DotsSixVertical size={14} />
        </button>
        {OUTILS.map(({ id, icon: Icon, label }) => (
          <button
            key={id}
            title={label}
            data-testid={`outil-${id}`}
            onClick={() => {
              if (id === "recentrage") {
                rfRef.current?.fitView({ duration: 600, padding: 0.15 });
                return;
              }
              setOutil(id);
            }}
            className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
              outil === id && id !== "recentrage"
                ? "bg-[#25D0C8]/15 text-[#25D0C8]"
                : "text-[#7C93A8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
            }`}
          >
            <Icon size={16} />
          </button>
        ))}
        <button
          title="Mode réorganisation — déplacer les robots (positions enregistrées, reclassification jamais automatique)"
          data-testid="outil-edition"
          onClick={() => setModeEdition((m) => !m)}
          className={`mt-1 flex h-8 w-8 items-center justify-center rounded-md border-t border-[rgba(148,163,184,0.16)] pt-1 transition-colors ${
            modeEdition ? "bg-[#F2B84B]/15 text-[#F2B84B]" : "text-[#7C93A8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
          }`}
        >
          <PencilSimple size={16} />
        </button>
        <button
          title="Expliquer cette carte — description textuelle accessible"
          aria-label="Expliquer cette carte"
          data-testid="expliquer-carte-btn"
          onClick={onExpliquer}
          className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
            expliquerOuvert ? "bg-[#9B87F5]/12 text-[#9B87F5]" : "text-[#7C93A8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
          }`}
        >
          <Article size={16} />
        </button>

        {/* Bibliothèque personnelle — un seul icône, les 4 listes en popover */}
        <button
          title="Bibliothèque — favoris, récents, investigations, situations"
          data-testid="outil-bibliotheque"
          onClick={() => setBiblioOuverte((o) => !o)}
          className={`mt-1 flex h-8 w-8 items-center justify-center rounded-md border-t border-[rgba(148,163,184,0.16)] pt-1 transition-colors ${
            biblioOuverte || vueListe ? "bg-[#9B87F5]/12 text-[#9B87F5]" : "text-[#7C93A8] hover:bg-[rgba(148,163,184,0.10)] hover:text-[#F2F6F8]"
          }`}
        >
          <Bookmarks size={16} weight={biblioOuverte || vueListe ? "fill" : "regular"} />
        </button>
      </div>

      {biblioOuverte && (
        <div className="glass absolute left-12 top-1/2 z-30 w-52 -translate-y-1/2 rounded-xl p-1.5 shadow-xl" data-testid="bibliotheque-menu">
          {LISTES.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              data-testid={`nav-${id}`}
              onClick={() => { onOuvrirListe?.(vueListe === id ? null : id); setBiblioOuverte(false); }}
              className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12px] transition-colors hover:bg-[rgba(148,163,184,0.10)] ${
                vueListe === id ? "font-semibold text-[#9B87F5]" : "text-[#94A3B8] hover:text-[#F2F6F8]"
              }`}
            >
              <Icon size={14} weight={vueListe === id ? "fill" : "regular"} /> {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
