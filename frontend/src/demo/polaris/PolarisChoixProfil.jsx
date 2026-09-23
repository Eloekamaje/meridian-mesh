// Choix du profil de la démonstration Polaris — page de la VRAIE application (route /demo),
// rendue dans la zone de contenu : la sidebar reste là. Choisir un profil ramène sur l'Atlas réel.
import { Sparkle, UserFocus, ChartLineUp, Compass, Lifebuoy, Code, ArrowRight, ChartPieSlice, Archive, MagnifyingGlass } from "@phosphor-icons/react";
import { PROFILS } from "./scenarios";
import { useKiosque } from "./KiosqueProvider";

const ICONES = {
  vp: ChartPieSlice,
  directeur: Archive,
  analyste: MagnifyingGlass,
  "ligne-affaires": ChartLineUp,
  architecte: Compass,
  "support-ti": Lifebuoy,
  developpeur: Code,
};

export default function PolarisChoixProfil() {
  const { demarrer } = useKiosque();
  const disponibles = PROFILS.filter((p) => p.disponible);
  const bientot = PROFILS.filter((p) => !p.disponible);
  return (
    <div className="h-full overflow-y-auto px-4 py-8 text-[#D8E2EA] sm:px-6 sm:py-12" data-testid="polaris-welcome">
      <div className="mx-auto max-w-[1000px]">
        <div className="mb-2 flex items-center gap-2 font-code text-[10px] uppercase tracking-[0.3em] text-[#60A5FA]">
          <Sparkle size={13} weight="fill" /> Démonstration Polaris
        </div>
        <h1 className="font-display text-3xl font-bold tracking-tight text-[#F2F6F8] sm:text-4xl" data-testid="polaris-titre">
          {disponibles.length > 1 ? "Choisissez votre parcours." : "Voir Méridian travailler."}
        </h1>
        <p className="mt-3 max-w-[640px] text-sm leading-relaxed text-[#94A3B8]">
          Chaque parcours est une conversation guidée avec Flore, l'assistante de Méridian : elle observe, découvre et prépare — puis montre ses preuves.
        </p>

        {/* Parcours disponibles : cartes pleines, l'action est évidente */}
        <div className={`mt-8 grid grid-cols-1 gap-4 ${disponibles.length > 1 ? "md:grid-cols-2" : ""}`}>
          {disponibles.map((p) => {
            const Icone = ICONES[p.id] || UserFocus;
            return (
              <button
                key={p.id}
                onClick={() => demarrer(p.id)}
                data-testid={`polaris-profil-${p.id}`}
                title={p.phrase}
                className="group flex min-h-[44px] flex-col gap-4 rounded-xl border border-[#60A5FA]/40 bg-[#0F1D28] p-5 text-left shadow-[0_8px_32px_rgba(96,165,250,0.08)] transition-all hover:-translate-y-0.5 hover:border-[#60A5FA]/70 sm:p-6 xl:flex-row xl:items-center"
              >
                {/* Icône + texte restent toujours côte à côte — seul le bouton, en dessous ou aligné
                    à droite selon la largeur, change de position (jamais de place pour les deux en
                    ligne sur une carte étroite : le texte finirait à un mot par ligne). Le seuil est
                    xl (1280px), pas lg (1024px) : à 1024px la barre latérale bureau passe de 56px à
                    256px (voir SidebarGauche.jsx), ce qui réduirait justement la largeur gagnée — un
                    iPad 13" en portrait (1024px) est exactement ce cas-là. */}
                <span className="flex min-w-0 items-center gap-4">
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-[#60A5FA]/12 text-[#60A5FA]"><Icone size={26} /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-display text-xl font-semibold text-[#F2F6F8]">{p.titre}</span>
                    <span className="mt-1 block text-[13px] leading-snug text-[#94A3B8]">{p.phrase}</span>
                  </span>
                </span>
                <span className="flex shrink-0 items-center justify-center gap-1.5 self-start rounded-md bg-[#60A5FA] px-3.5 py-2 text-xs font-semibold text-[#071019] transition-colors group-hover:bg-[#93C5FD] xl:ml-auto xl:self-auto">
                  Lancer le parcours <ArrowRight size={13} weight="bold" />
                </span>
              </button>
            );
          })}
        </div>

        {/* Parcours à venir : discrets, en fin de page — ils ne prennent pas la vedette */}
        {bientot.length > 0 && (
          <div className="mt-8" data-testid="polaris-bientot">
            <div className="font-code text-[11px] uppercase tracking-[0.2em] text-[#7C93A8]">Prochains parcours</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {bientot.map((p) => {
                const Icone = ICONES[p.id] || UserFocus;
                return (
                  <span key={p.id} data-testid={`polaris-profil-${p.id}`} aria-disabled="true" title={p.phrase} className="flex items-center gap-2 rounded-full border border-[rgba(148,163,184,0.16)] bg-[#0F1D28]/50 px-3 py-1.5 text-xs text-[#94A3B8]">
                    <Icone size={14} /> {p.titre}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        <p className="mt-10 text-center font-code text-[10px] text-[#7C93A8]" data-testid="polaris-mention-fictif">
          Démonstration sur données fictives — aucune connexion à un environnement réel.
        </p>
      </div>
    </div>
  );
}
