import { useMemo } from "react";

function mulberry32(graine) {
  let a = graine;
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const COULEURS = ["#FFFFFF", "#E8F4F8", "#E8F4F8", "#BFE8F0", "#BFE8F0", "#F8E0B0"];

export default function CielEtoile() {
  const etoiles = useMemo(() => {
    const rand = mulberry32(20260915);
    const liste = [];
    for (let i = 0; i < 170; i++) {
      const x = rand() * 100;
      const y = rand() * 100;
      const tirage = rand();
      const couche = tirage < 0.68 ? 0 : tirage < 0.94 ? 1 : 2;
      const r = couche === 0 ? 0.5 + rand() * 0.4 : couche === 1 ? 0.9 + rand() * 0.45 : 1.3 + rand() * 0.4;
      const opacite = couche === 0 ? 0.14 + rand() * 0.2 : couche === 1 ? 0.28 + rand() * 0.24 : 0.5 + rand() * 0.22;
      const couleur = COULEURS[Math.floor(rand() * COULEURS.length)];
      const scintille = rand() < 0.15;
      liste.push({
        x, y, r, opacite, couleur, scintille,
        duree: 3 + rand() * 4,
        delai: -rand() * 7,
        halo: couche === 2,
      });
    }
    return liste;
  }, []);

  return (
    <svg
      data-testid="ciel-etoile"
      aria-hidden="true"
      className="ciel-deploiement pointer-events-none absolute inset-0 h-full w-full"
      style={{ zIndex: 0 }}
    >
      {etoiles.map((e, i) => (
        <g key={i}>
          {e.halo && (
            <circle cx={`${e.x}%`} cy={`${e.y}%`} r={e.r * 2.4} fill={e.couleur} opacity={e.opacite * 0.07} />
          )}
          <circle
            cx={`${e.x}%`}
            cy={`${e.y}%`}
            r={e.r}
            fill={e.couleur}
            opacity={e.opacite}
            className={e.scintille ? "etoile-scintille" : undefined}
            style={e.scintille ? { "--op-base": e.opacite, animationDuration: `${e.duree}s`, animationDelay: `${e.delai}s` } : undefined}
          />
        </g>
      ))}
    </svg>
  );
}
