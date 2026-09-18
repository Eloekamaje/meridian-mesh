// Contrôles du lecteur Polaris (§6.3) : pause, reprise, séquence suivante, relecture.
import { Pause, Play, SkipForward, ArrowCounterClockwise, House, FastForward } from "@phosphor-icons/react";

const BTN =
  "flex min-h-[44px] items-center gap-2 rounded-lg border border-[rgba(148,163,184,0.2)] bg-[#0F1D28] px-3.5 py-2 font-code text-[11px] text-[#D8E2EA] transition-colors hover:border-[#25D0C8]/50 hover:text-[#25D0C8] disabled:cursor-not-allowed disabled:opacity-40";

export default function PolarisControls({ etat, onPause, onReprendre, onSuivant, onRevoir, onAccueil, onLectureAuto }) {
  const { status, playMode, stepIndex } = etat;
  const enCours = status === "playing";
  const enPause = status === "paused";
  const auCheckpoint = status === "awaiting_continue";
  const fini = status === "completed";

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="polaris-controles">
      {enCours && (
        <button onClick={() => onPause()} className={BTN} data-testid="polaris-pause-btn" title="Suspendre la lecture (délai conservé)">
          <Pause size={14} weight="fill" /> Pause
        </button>
      )}
      {enPause && (
        <button onClick={onReprendre} className={`${BTN} !border-[#25D0C8]/60 !text-[#25D0C8]`} data-testid="polaris-reprendre-btn">
          <Play size={14} weight="fill" /> Reprendre
        </button>
      )}
      {(enCours || enPause || auCheckpoint) && (
        <button onClick={onSuivant} className={BTN} data-testid="polaris-suivant-btn" title="Termine la séquence en cours, puis avance séquence par séquence">
          <SkipForward size={14} /> Suivant
        </button>
      )}
      {playMode === "manual" && (auCheckpoint || fini) === false && (
        <button onClick={onLectureAuto} className={BTN} data-testid="polaris-auto-btn" title="Reprendre la lecture automatique">
          <FastForward size={14} /> Lecture auto
        </button>
      )}
      {(fini || auCheckpoint) && stepIndex >= 0 && (
        <button onClick={onRevoir} className={BTN} data-testid="polaris-revoir-btn" title="Rejouer la découverte depuis son checkpoint">
          <ArrowCounterClockwise size={14} /> Revoir la découverte
        </button>
      )}
      <button onClick={onAccueil} className={BTN} data-testid="polaris-accueil-btn">
        <House size={14} /> {fini ? "Choisir un autre rôle" : "Accueil"}
      </button>
      {(enPause || etat.motif) && (
        <span className="font-code text-[10px] uppercase tracking-[0.2em] text-[#F2B84B]" data-testid="polaris-statut-pause">
          Lecture en pause{etat.motif ? ` — ${etat.motif}` : ""}
        </span>
      )}
    </div>
  );
}
