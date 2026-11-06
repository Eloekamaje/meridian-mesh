import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";

const POSTES_REPLI = [
  ["analyste", "Analyste"], ["architecte", "Architecte"], ["product_owner", "Product Owner"],
  ["developpeur", "Développeur"], ["scrum_master", "Scrum Master"],
  ["chef_projet", "Chef de projet / PMO"], ["directeur", "Directeur"],
  ["finance", "Finance"], ["support", "Ops / Support"], ["risque", "Risque / Conformité"],
  ["data_steward", "Data Steward"],
];

export default function Signup() {
  const [params] = useSearchParams();
  const [nom, setNom] = useState("");
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [poste, setPoste] = useState("architecte");
  const [invitation, setInvitation] = useState(params.get("invitation") || "");
  const [postes, setPostes] = useState(POSTES_REPLI);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    api.get("/auth/postes").then(({ data }) => {
      if (Array.isArray(data) && data.length) setPostes(data.map((p) => [p.id, p.libelle]));
    }).catch(() => {});
  }, []);

  const soumettre = async (evenement) => {
    evenement.preventDefault();
    setEnvoi(true);
    try {
      await api.post("/auth/signup", {
        nom, email, mot_de_passe: motDePasse, poste,
        invitation: invitation.trim() || null,
      });
      window.location.assign("/travaux");
    } catch (erreur) {
      toast.error(erreur?.response?.data?.detail || "Création du compte impossible");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#071019] px-4 py-10 text-[#F2F6F8]">
      <div className="w-full max-w-lg rounded-2xl border border-white/[0.10] bg-[#0C1724] p-7">
        <p className="font-code text-[10px] uppercase tracking-[0.18em] text-[#7C93A8]">Méridian · espace pilote</p>
        <h1 className="mt-2 font-display text-3xl font-semibold">Créer un compte</h1>
        <p className="mt-2 text-sm leading-relaxed text-[#94A3B8]">
          Le poste décrit votre rôle de travail. Il ne donne pas à lui seul un droit de décision.
        </p>
        <form onSubmit={soumettre} className="mt-6 grid gap-4 sm:grid-cols-2">
          <label className="block text-xs text-[#94A3B8] sm:col-span-2">
            Nom affiché
            <input required value={nom} onChange={(e) => setNom(e.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8] outline-none focus:border-[#60A5FA]/70" />
          </label>
          <label className="block text-xs text-[#94A3B8] sm:col-span-2">
            Adresse électronique
            <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8] outline-none focus:border-[#60A5FA]/70" />
          </label>
          <label className="block text-xs text-[#94A3B8]">
            Mot de passe
            <input type="password" autoComplete="new-password" minLength={8} required value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8] outline-none focus:border-[#60A5FA]/70" />
          </label>
          <label className="block text-xs text-[#94A3B8]">
            Poste
            <select value={poste} onChange={(e) => setPoste(e.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8] outline-none focus:border-[#60A5FA]/70">
              {postes.map(([id, libelle]) => <option key={id} value={id}>{libelle}</option>)}
            </select>
          </label>
          <label className="block text-xs text-[#94A3B8] sm:col-span-2">
            Code d’invitation <span className="text-[#64748B]">(facultatif pour un espace de démonstration)</span>
            <input value={invitation} onChange={(e) => setInvitation(e.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8] outline-none focus:border-[#60A5FA]/70" />
          </label>
          <button type="submit" disabled={envoi}
            className="h-10 rounded-lg bg-[#60A5FA] text-sm font-semibold text-[#071019] disabled:opacity-50 sm:col-span-2">
            {envoi ? "Création…" : "Créer mon compte"}
          </button>
        </form>
        <p className="mt-5 text-center text-xs text-[#7C93A8]">
          Déjà un compte ? <Link to="/login" className="text-[#93C5FD] hover:underline">Se connecter</Link>
        </p>
      </div>
    </main>
  );
}
