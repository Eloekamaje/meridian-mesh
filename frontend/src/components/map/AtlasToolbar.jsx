import { useState } from "react";
import { Hand, Lasso, Crosshair, Article, PencilSimple, Star, ClockCounterClockwise, SealQuestion, WarningDiamond, Bookmarks } from "@phosphor-icons/react";

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

export default function AtlasToolbar({ outil, setOutil, rfRef, onExpliquer, expliquerOuvert, modeEdition, setModeEdition, vueListe, onOuvrirListe }) {
  const [biblioOuverte, setBiblioOuverte] = useState(false);

  return (
    <div className="absolute left-4 top-1/2 z-10 -translate-y-1/2" data-testid="map-toolbar">
      <div className="glass flex flex-col gap-1 rounded-xl p-1.5">
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
                ? "bg-[#0E7490]/15 text-[#0E7490]"
                : "text-[#71716D] hover:bg-[#F0F0EE] hover:text-[#111110]"
            }`}
          >
            <Icon size={16} />
          </button>
        ))}
        <button
          title="Mode réorganisation — déplacer les robots (positions enregistrées, reclassification jamais automatique)"
          data-testid="outil-edition"
          onClick={() => setModeEdition((m) => !m)}
          className={`mt-1 flex h-8 w-8 items-center justify-center rounded-md border-t border-[#E5E5E3] pt-1 transition-colors ${
            modeEdition ? "bg-[#B45309]/15 text-[#B45309]" : "text-[#71716D] hover:bg-[#F0F0EE] hover:text-[#111110]"
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
            expliquerOuvert ? "bg-[#3730A3]/12 text-[#3730A3]" : "text-[#71716D] hover:bg-[#F0F0EE] hover:text-[#111110]"
          }`}
        >
          <Article size={16} />
        </button>

        {/* Bibliothèque personnelle — un seul icône, les 4 listes en popover */}
        <button
          title="Bibliothèque — favoris, récents, investigations, situations"
          data-testid="outil-bibliotheque"
          onClick={() => setBiblioOuverte((o) => !o)}
          className={`mt-1 flex h-8 w-8 items-center justify-center rounded-md border-t border-[#E5E5E3] pt-1 transition-colors ${
            biblioOuverte || vueListe ? "bg-[#3730A3]/12 text-[#3730A3]" : "text-[#71716D] hover:bg-[#F0F0EE] hover:text-[#111110]"
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
              className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12px] transition-colors hover:bg-[#F0F0EE] ${
                vueListe === id ? "font-semibold text-[#3730A3]" : "text-[#52524F] hover:text-[#111110]"
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

