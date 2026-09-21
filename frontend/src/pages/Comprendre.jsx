import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "@/lib/api";
import FloreActivite, { delaiMin } from "@/components/FloreActivite";

// Ancienne adresse « Comprendre » : une actualité qu'on ouvre est désormais un TRAVAIL (même page, même conversation que tous les autres).
// Cette route reste pour les liens existants : elle ouvre (ou rouvre) le travail de cette actualité et y redirige, retour vers Actualités en évidence.
export default function Comprendre() {
  const { hid } = useParams();
  const navigate = useNavigate();
  const [erreur, setErreur] = useState(null);

  useEffect(() => {
    let actif = true;
    delaiMin(api.post(`/actualites/histoire/${hid}/travail`, { intention: "comprendre" }), 1300)
      .then((r) => { if (actif) navigate(`/travaux/${r.data.id}`, { replace: true, state: { retour: { label: "Actualités", to: "/actualites" } } }); })
      .catch((e) => { if (actif) setErreur(e.response?.data?.detail || "Actualité introuvable"); });
    return () => { actif = false; };
  }, [hid, navigate]);

  if (erreur) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="comprendre-erreur">
        <p className="text-sm text-[#F87171]">{erreur}</p>
        <Link to="/actualites" data-testid="comprendre-erreur-retour" className="rounded-md border border-[rgba(148,163,184,0.16)] px-3 py-1.5 text-xs text-[#94A3B8] hover:text-[#F2F6F8]">← Retour aux actualités</Link>
      </div>
    );
  }
  return (
    <div className="flex h-full items-center justify-center" data-testid="comprendre-chargement">
      <FloreActivite genre="rapport" testid="comprendre-chargement-activite" />
    </div>
  );
}
