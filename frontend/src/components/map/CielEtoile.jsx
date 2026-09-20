
export default function CielEtoile() {
  return (
    <svg
      data-testid="ciel-etoile"
      aria-hidden="true"
      className="ciel-deploiement pointer-events-none absolute inset-0 h-full w-full"
      style={{ zIndex: 0 }}
    >
      <defs>
        <pattern id="linear-matrix-grid" width="28" height="28" patternUnits="userSpaceOnUse">
          <circle cx="14" cy="14" r="0.75" fill="#94A3B8" opacity="0.12" />
        </pattern>
        <radialGradient id="linear-ambient-glow" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stopColor="#1E293B" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#070A10" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#linear-ambient-glow)" />
      <rect width="100%" height="100%" fill="url(#linear-matrix-grid)" />
    </svg>
  );
}
