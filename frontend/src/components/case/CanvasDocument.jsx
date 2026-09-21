import { useState } from "react";
import { 
  X, 
  FileText, 
  Copy, 
  ArrowsOut, 
  ArrowsIn, 
  Check, 
  Sparkle,
  ShieldCheck,
  Coins,
  Clock
} from "@phosphor-icons/react";
import { toast } from "sonner";

export const CONTENU_CASE_101 = `# MÉRIDIAN — Arbitrage Budgétaire & Convergence SI
**Réf :** CASE-101 · **Date :** 20 septembre 2026 · **Comité d'Investissement SI**
**Statut :** Recommandation officielle d'arbitrage · **Instance :** 09h00

---

## 1. Contexte & Problématique Soumise au Comité

Trois directions métier ont déposé indépendamment une demande d'investissement pour le cycle budgétaire 2026 :
1. **Direction Relation Client :** Projet « Suivi des demandes clients » — Budget : 2,0 M€ — Délai : 14 mois
2. **Direction Distribution & Réseau :** Projet « Poste conseiller repensé » — Budget : 2,0 M€ — Délai : 18 mois
3. **Direction Opérations & Gestion :** Projet « Réduction des reprises manuelles » — Budget : 2,6 M€ — Délai : 12 mois

**Total cumulé des demandes en silos : 6,6 M€**

---

## 2. Diagnostic du Mesh Méridian : Triple Redondance

L'audit automatisé des flux et des modèles de données opéré par Flore et les jumeaux numériques révèle que **les trois initiatives visent à résoudre exactement le même besoin fonctionnel** :
> *Disposer d'une information fiable, consolidée et horodatée sur l'état réel d'un dossier.*

* **Projet 1 (Client) :** a besoin de l'état pour l'afficher sur l'espace client web et éviter les appels au service client.
* **Projet 2 (Conseiller) :** a besoin de l'état pour éviter d'interrompre le conseiller et libérer du temps commercial.
* **Projet 3 (Opérations) :** produit et gère cet état lors de l'instruction du dossier.

---

## 3. Révélation d'Architecture : Le Socle Existant à 80%

Le Système d'Information dispose déjà en production des capacités requises :
* **Composant applicatif « Gestion des dossiers » (app-dossiers) :** Contient 80% de la logique métier, la machine à états officielle et le cycle de vie du dossier.
* **Composant d'exposition « Diffusion des statuts » (app-statuts) :** Possède l'infrastructure de publication temps réel (Kafka / Webhook).

Construire trois solutions spécifiques conduirait à une dette technique majeure et à des divergences inévitables entre l'état vu par le client, celui vu par le conseiller et la réalité des opérations.

---

## 4. Recommandation d'Arbitrage & Trajectoire Mutualisée

| Critère d'évaluation | Trajectoire Silos (Rejetée) | Socle Mutualisé CASE-101 (Recommandé) | Écart / Bénéfice |
| :--- | :--- | :--- | :--- |
| **Budget global** | **6,6 M€** (3 projets distincts) | **1,5 M€** (socle commun + 2 connecteurs) | **-5,1 M€ (-77%)** |
| **Délai de mise en service** | 12 à 18 mois | **4 mois** | **-8 à -14 mois** |
| **Effort de développement** | 3 architectures complètes | 2 connecteurs API légers sur socle existant | Risque divisé par 4 |
| **Cohérence des données** | Divergence garantie entre canaux | Source unique de vérité partagée | Alignement 100% |
| **Gouvernance** | Conflits de synchronisation | Contrat d'interface unifié | Responsabilité claire |

---

## 5. Décisions Soumises au Vote du Comité

1. **Geler immédiatement** les 3 développements spécifiques prévus en silos (économie brute de 6,6 M€).
2. **Allouer un budget mutualisé de 1,5 M€** réparti comme suit :
   * Renforcement du socle « Gestion des dossiers » et de son API d'exposition : **0,7 M€**
   * Connecteur d'interface vers le Portail Client Web : **0,4 M€**
   * Connecteur d'interface vers le Poste Conseiller : **0,4 M€**
3. **Valider le calendrier cible :** Mise en service pilote sous **4 mois** (janvier 2027).
`;

export default function CanvasDocument({
  titre = "CASE_101_ARBITRAGE_CONVERGENCE.md",
  contenu = CONTENU_CASE_101,
  onFermer,
}) {
  const [pleinEcran, setPleinEcran] = useState(false);
  const [copie, setCopie] = useState(false);

  const copierDocument = () => {
    navigator.clipboard?.writeText(contenu);
    setCopie(true);
    toast.success("Document copié dans le presse-papier");
    setTimeout(() => setCopie(false), 2000);
  };

  return (
    <div 
      className={`flex h-full w-full flex-col border-l border-white/[0.1] bg-[#0A1520] shadow-2xl transition-all duration-300 ${
        pleinEcran ? "fixed inset-0 z-50 bg-[#071019]" : ""
      }`}
      data-testid="canvas-document"
    >
      {/* En-tête du volet Canvas — fidèle à l'esthétique ChatGPT Canvas */}
      <div className="flex items-center justify-between border-b border-white/[0.08] bg-[#0D1A27] px-4 py-3">
        <div className="flex items-center gap-2 font-code text-xs">
          <span className="text-[#64748B]">Bibliothèque /</span>
          <span className="font-semibold text-[#F2F6F8]">
            {titre}
          </span>
          <span className="ml-1 rounded bg-[#60A5FA]/20 px-1.5 py-0.5 text-[9px] font-semibold text-[#60A5FA]">
            Document généré
          </span>
        </div>

        {/* Outils d'action : Copier, Plein écran, Fermer */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={copierDocument}
            className="flex h-7 items-center gap-1.5 rounded-lg border border-white/[0.12] bg-[#07111B] px-2.5 font-code text-[11px] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
            title="Copier le document"
            data-testid="btn-copier-doc"
          >
            {copie ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
            <span>{copie ? "Copié" : "Copier"}</span>
          </button>

          <button
            onClick={() => setPleinEcran(!pleinEcran)}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.12] bg-[#07111B] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
            title={pleinEcran ? "Réduire l'affichage" : "Plein écran"}
            data-testid="btn-plein-ecran-canvas"
          >
            {pleinEcran ? <ArrowsIn size={14} /> : <ArrowsOut size={14} />}
          </button>

          {onFermer && (
            <button
              onClick={onFermer}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.12] bg-[#07111B] text-[#94A3B8] transition-colors hover:border-white/30 hover:text-white"
              title="Fermer le Canvas"
              data-testid="btn-fermer-canvas"
            >
              <X size={15} />
            </button>
          )}
        </div>
      </div>

      {/* Contenu Markdown rendu avec élégance */}
      <div className="relative flex-1 overflow-y-auto px-8 py-7 text-[#CBD5E1]">
        <div className="mx-auto max-w-2xl space-y-6 font-sans leading-relaxed">
          {/* Entête type Document Markdown officiel */}
          <div className="border-b border-white/[0.1] pb-5">
            <div className="flex items-center gap-2">
              <span className="rounded bg-[#60A5FA]/20 px-2 py-0.5 font-code text-[10px] font-semibold uppercase tracking-wider text-[#BFDBFE]">
                Dossier de Décision Exécutif
              </span>
              <span className="font-code text-[10px] text-[#64748B]">Réf : CASE-101</span>
            </div>
            <h1 className="mt-3 font-display text-2xl font-bold tracking-tight text-[#F2F6F8]">
              MÉRIDIAN — Arbitrage Budgétaire & Convergence SI
            </h1>
            <p className="mt-1 font-code text-xs text-[#94A3B8]">
              Document officiel pour le Comité d'Investissement SI du 20 septembre 2026 à 09h00
            </p>
            <div className="mt-3.5 flex flex-wrap gap-2 text-[11px] text-[#7C93A8]">
              <span className="rounded-lg bg-[#07111B] px-2.5 py-1 border border-white/[0.08]">
                Périmètre : <strong className="text-[#CBD5E1]">Web, Succursales, Back-Office</strong>
              </span>
              <span className="rounded-lg bg-[#07111B] px-2.5 py-1 border border-white/[0.08]">
                Statut : <strong className="text-emerald-400">Recommandation formelle</strong>
              </span>
            </div>
          </div>

          {/* 1. Contexte & Problématique */}
          <section className="space-y-3">
            <h2 className="font-display text-lg font-semibold text-[#F2F6F8]">
              1. Contexte & Problématique Soumise au Comité
            </h2>
            <p className="text-sm text-[#CBD5E1]">
              Trois directions métier ont déposé indépendamment une demande d'investissement pour le cycle budgétaire 2026 :
            </p>
            <div className="space-y-2 rounded-xl border border-white/[0.08] bg-[#07111B] p-4 text-xs font-code">
              <div className="flex items-center justify-between border-b border-white/[0.05] pb-2 text-[#CBD5E1]">
                <span>1. Direction Relation Client — « Suivi des demandes »</span>
                <span className="text-[#F87171]">2,0 M€ · 14 mois</span>
              </div>
              <div className="flex items-center justify-between border-b border-white/[0.05] pb-2 text-[#CBD5E1]">
                <span>2. Direction Distribution — « Poste conseiller repensé »</span>
                <span className="text-[#F87171]">2,0 M€ · 18 mois</span>
              </div>
              <div className="flex items-center justify-between text-[#CBD5E1]">
                <span>3. Direction Opérations — « Réduction des reprises manuelles »</span>
                <span className="text-[#F87171]">2,6 M€ · 12 mois</span>
              </div>
            </div>
            <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-200">
              ⚠️ <strong>Total cumulé des demandes en silos : 6,6 M€</strong> pour un délai pouvant atteindre 18 mois.
            </div>
          </section>

          {/* 2. Diagnostic du Mesh */}
          <section className="space-y-3">
            <h2 className="font-display text-lg font-semibold text-[#F2F6F8]">
              2. Diagnostic du Mesh Méridian : Triple Redondance
            </h2>
            <p className="text-sm text-[#CBD5E1]">
              L'audit automatisé des flux et des modèles de données opéré par Flore et les jumeaux numériques révèle que <strong>les trois initiatives visent à résoudre exactement le même besoin fonctionnel</strong> :
            </p>
            <blockquote className="border-l-2 border-[#60A5FA] pl-4 py-1 text-sm italic text-[#E2E8F0] bg-[#07111B]/50 rounded-r-lg">
              « Disposer d'une information fiable, consolidée et horodatée sur l'état réel d'un dossier. »
            </blockquote>
          </section>

          {/* 3. Le Socle Existant à 80% */}
          <section className="space-y-3">
            <h2 className="font-display text-lg font-semibold text-[#F2F6F8]">
              3. Révélation d'Architecture : Le Socle Existant à 80%
            </h2>
            <p className="text-sm text-[#CBD5E1]">
              Le Système d'Information dispose déjà en production des capacités requises :
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 text-xs">
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-3.5">
                <div className="flex items-center gap-1.5 font-code text-emerald-400 font-semibold">
                  <ShieldCheck size={14} />
                  <span>Gestion des dossiers (app-dossiers)</span>
                </div>
                <p className="mt-1 text-[11px] text-emerald-200/80">
                  Détient la machine à états officielle et le cycle de vie complet.
                </p>
              </div>
              <div className="rounded-xl border border-sky-500/30 bg-sky-950/20 p-3.5">
                <div className="flex items-center gap-1.5 font-code text-sky-400 font-semibold">
                  <Sparkle size={14} />
                  <span>Diffusion des statuts (app-statuts)</span>
                </div>
                <p className="mt-1 text-[11px] text-sky-200/80">
                  Possède l'infrastructure d'exposition temps réel via connecteurs API / Kafka.
                </p>
              </div>
            </div>
          </section>

          {/* 4. Tableau comparatif des trajectoires */}
          <section className="space-y-3">
            <h2 className="font-display text-lg font-semibold text-[#F2F6F8]">
              4. Comparatif d'Arbitrage & Trajectoire Mutualisée
            </h2>
            <div className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#07111B]">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-white/[0.08] bg-[#0D1A27] font-code text-[10px] uppercase tracking-wider text-[#64748B]">
                    <th className="py-2.5 pl-4 pr-2">Critère d'évaluation</th>
                    <th className="px-2 py-2.5 text-[#F87171]">Trajectoire Silos</th>
                    <th className="py-2.5 pl-2 pr-4 text-emerald-400">Socle Mutualisé (CASE-101)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.05] font-sans">
                  <tr>
                    <td className="py-2.5 pl-4 pr-2 font-medium text-[#CBD5E1]">Budget global</td>
                    <td className="px-2 py-2.5 font-code text-[#F87171]">6,6 M€</td>
                    <td className="py-2.5 pl-2 pr-4 font-code font-semibold text-emerald-300">1,5 M€ (-77%)</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pl-4 pr-2 font-medium text-[#CBD5E1]">Délai de mise en service</td>
                    <td className="px-2 py-2.5 font-code text-[#F87171]">12 à 18 mois</td>
                    <td className="py-2.5 pl-2 pr-4 font-code font-semibold text-emerald-300">4 mois (-14 mois)</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pl-4 pr-2 font-medium text-[#CBD5E1]">Architecture SI</td>
                    <td className="px-2 py-2.5 text-[#94A3B8]">3 développements spécifiques</td>
                    <td className="py-2.5 pl-2 pr-4 text-[#E2E8F0]">2 connecteurs API sur socle existant</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pl-4 pr-2 font-medium text-[#CBD5E1]">Dette technique</td>
                    <td className="px-2 py-2.5 text-[#F87171]">Divergence des états de dossier</td>
                    <td className="py-2.5 pl-2 pr-4 text-emerald-400">Faible (source unique de vérité)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          {/* 5. Décisions à voter */}
          <section className="space-y-3 pb-6">
            <h2 className="font-display text-lg font-semibold text-[#F2F6F8]">
              5. Décisions Soumises au Vote du Comité
            </h2>
            <ol className="list-decimal list-inside space-y-2 text-sm text-[#CBD5E1]">
              <li><strong>Geler immédiatement</strong> les 3 développements spécifiques prévus en silos (économie brute de 6,6 M€).</li>
              <li><strong>Allouer un budget mutualisé de 1,5 M€</strong> pour brancher les connecteurs sur le socle « Gestion des dossiers ».</li>
              <li><strong>Valider le calendrier cible :</strong> Mise en service pilote sous <strong>4 mois</strong> (janvier 2027).</li>
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}
