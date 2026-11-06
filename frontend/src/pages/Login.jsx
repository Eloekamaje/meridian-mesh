import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";

export default function Login() {
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const from = params.get("from") || "/travaux";

  const soumettre = async (evenement) => {
    evenement.preventDefault();
    setEnvoi(true);
    try {
      await api.post("/auth/login", { email, mot_de_passe: motDePasse });
      window.location.assign(from);
    } catch (erreur) {
      toast.error(erreur?.response?.data?.detail || "Connexion impossible");
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#071019] px-4 py-10 text-[#F2F6F8]">
      <div className="w-full max-w-md rounded-2xl border border-white/[0.10] bg-[#0C1724] p-7">
        <p className="font-code text-[10px] uppercase tracking-[0.18em] text-[#7C93A8]">Méridian · espace pilote</p>
        <h1 className="mt-2 font-display text-3xl font-semibold">Se connecter</h1>
        <p className="mt-2 text-sm leading-relaxed text-[#94A3B8]">
          Votre poste et votre espace entrent dans le contexte de chaque analyse.
        </p>
        <form onSubmit={soumettre} className="mt-6 space-y-4">
          <label className="block text-xs text-[#94A3B8]">
            Adresse électronique
            <input type="email" autoComplete="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8] outline-none focus:border-[#60A5FA]/70" />
          </label>
          <label className="block text-xs text-[#94A3B8]">
            Mot de passe
            <input type="password" autoComplete="current-password" required value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
              className="mt-1 h-10 w-full rounded-lg border border-white/[0.12] bg-[#071019] px-3 text-sm text-[#F2F6F8] outline-none focus:border-[#60A5FA]/70" />
          </label>
          <button type="submit" disabled={envoi}
            className="h-10 w-full rounded-lg bg-[#60A5FA] text-sm font-semibold text-[#071019] disabled:opacity-50">
            {envoi ? "Connexion…" : "Se connecter"}
          </button>
        </form>
        <p className="mt-5 text-center text-xs text-[#7C93A8]">
          Pas encore de compte ? <Link to="/signup" className="text-[#93C5FD] hover:underline">Créer un compte</Link>
        </p>
      </div>
    </main>
  );
}
