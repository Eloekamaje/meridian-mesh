import { Hand, Lasso, Path, Crosshair } from "@phosphor-icons/react";

const OUTILS = [
  { id: "deplacement", icon: Hand, label: "Déplacement" },
  { id: "lasso", icon: Lasso, label: "Sélection multiple / lasso" },
  { id: "parcours", icon: Path, label: "Explorer un parcours" },
  { id: "recentrage", icon: Crosshair, label: "Recentrage" },
];

export default function AtlasToolbar({ outil, setOutil, setMode, rfRef }) {
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
            if (id === "parcours") {
              setMode("parcours");
              return;
            }
            setOutil(id);
          }}
          className={`flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
            outil === id && id !== "recentrage" && id !== "parcours"
              ? "bg-[#22D3EE]/15 text-[#22D3EE]"
              : "text-white/45 hover:bg-white/[0.06] hover:text-white"
          }`}
        >
          <Icon size={16} />
        </button>
      ))}
    </div>
  );
}
