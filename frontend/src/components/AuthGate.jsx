import { Navigate, Outlet, useLocation } from "react-router-dom";
import { usePerimetre } from "@/lib/perimetre";

export default function AuthGate() {
  const perimetre = usePerimetre() || {};
  const { authMode, utilisateur, charge } = perimetre;
  const location = useLocation();
  if (charge === false) {
    return <div className="flex h-screen items-center justify-center bg-[#071019] text-sm text-[#7C93A8]">Chargement de l’identité…</div>;
  }
  if (authMode === "local" && !utilisateur) {
    const from = `${location.pathname}${location.search || ""}`;
    return <Navigate to={`/login?from=${encodeURIComponent(from)}`} replace />;
  }
  return <Outlet />;
}
