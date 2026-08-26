import { Hand, Lasso, Crosshair, Article } from "@phosphor-icons/react";

const OUTILS = [
  { id: "deplacement", icon: Hand, label: "Déplacement" },
  { id: "lasso", icon: Lasso, label: "Sélection multiple / lasso" },
  { id: "recentrage", icon: Crosshair, label: "Recentrage" },
];

export default function AtlasToolbar({ outil, setOutil, rfRef, onExpliquer, expliquerOuvert }) {
  return (
    <div className="glass absolute left-4 top-1/2 z-10 flex -translate-y-1/2 flex-col gap-1 rounded-xl p-1.5" data-testid="map-toolbar">
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
        title="Expliquer cette carte — description textuelle accessible"
        aria-label="Expliquer cette carte"
        data-testid="expliquer-carte-btn"
        onClick={onExpliquer}
        className={`mt-1 flex h-8 w-8 items-center justify-center rounded-md border-t border-[#E5E5E3] pt-1 transition-colors ${
          expliquerOuvert ? "bg-[#3730A3]/12 text-[#3730A3]" : "text-[#71716D] hover:bg-[#F0F0EE] hover:text-[#111110]"
        }`}
      >
        <Article size={16} />
      </button>
    </div>
  );
}
