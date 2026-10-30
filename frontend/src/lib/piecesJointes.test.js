// P4 — les pièces jointes sont des sources réelles du Travail, jamais un bouton décoratif.
const fs = require("fs");
const path = require("path");

const lire = (f) => fs.readFileSync(path.join(__dirname, "..", f), "utf8");

test("le compositeur du Travail peut joindre et lister les pièces, seulement quand c'est autorisé", () => {
  const source = lire("components/case/OngletTravail.jsx");
  expect(source).toContain("BoutonJoindre");
  expect(source).toContain("ListePieces");
  expect(source).toContain("piecesAutorisees");
  // Le trombone n'est monté que si le dépôt est autorisé (pas en démo, ni sur un brouillon,
  // ni pour un lecteur simple — le serveur expose `peut_deposer` = responsable ou participant).
  expect(source).toContain("{piecesAutorisees && <BoutonJoindre");
  expect(source).toContain("cas?.peut_deposer !== false");
  // Les pièces d'un travail de démonstration restent en lecture seule : ni retrait ni dépôt.
  expect(source).toContain("lectureSeule={!piecesAutorisees}");
  expect(lire("components/case/PiecesJointes.jsx")).toContain("lectureSeule");
});

test("l'envoi, le téléchargement et le retrait passent par l'API des pièces", () => {
  const source = lire("components/case/PiecesJointes.jsx");
  expect(source).toContain("new FormData()");
  expect(source).toContain("api.post(`/cases/${cas.id}/pieces`");
  expect(source).toContain('responseType: "blob"');
  expect(source).toContain("api.delete(`/cases/${cas.id}/pieces/${piece.id}`");
});

test("avec des pièces, l'écriture de Flore est une autorisation humaine explicite", () => {
  const source = lire("components/case/OngletTravail.jsx");
  // La case n'apparaît que s'il y a des pièces, décochée par défaut, et se remet à zéro en changeant de travail.
  expect(source).toContain('(cas.pieces || []).length > 0');
  expect(source).toContain("const [autoriserEcriture, setAutoriserEcriture] = useState(false)");
  expect(source).toContain('data-testid="case-autoriser-ecriture"');
  expect(source).toContain("Autoriser Flore à modifier le travail");
  // Le tour porte l'autorisation, au fil de l'eau comme en repli non-flux.
  expect(source).toContain("autoriser_ecriture: (cas.pieces || []).length > 0 && autoriserEcriture");
  expect(source).toContain("demanderEnFlux(`/cases/${idTravail}/messages/flux`, corps");
  expect(source).toContain("api.post(`/cases/${idTravail}/messages`, corps)");
});

test("les pièces sont annoncées comme des sources non vérifiées", () => {
  const source = lire("components/case/PiecesJointes.jsx") + lire("components/case/OngletTravail.jsx");
  expect(source).toMatch(/sources du [Tt]ravail/);
  expect(source).toMatch(/jamais comme des connaissances validées/);
});

test("les formats bureautiques utiles sont acceptés, pas les variantes macro", () => {
  const source = lire("components/case/PiecesJointes.jsx");
  const bloc = source.match(/export const EXTENSIONS_PIECES = \[([\s\S]*?)\];/);
  expect(bloc).not.toBeNull();
  for (const ext of ['".xlsx"', '".pptx"', '".odt"', '".rtf"', '".epub"', '".xls"']) {
    expect(bloc[1]).toContain(ext);
  }
  for (const ext of ['".xlsm"', '".docm"', '".pptm"']) {
    expect(bloc[1]).not.toContain(ext);
  }
});

test("une pièce sans texte est annoncée comme non utilisée par Flore, jamais comme lue", () => {
  const source = lire("components/case/PiecesJointes.jsx");
  expect(source).toMatch(/vide: \["aucun texte"/);
  expect(source).toMatch(/piece\.etat === "vide"/);
  expect(source).toContain("non utilisée par Flore");
});

test("le découpage en sections est lisible, avec un sommaire borné et sans surcharge", () => {
  const source = lire("components/case/PiecesJointes.jsx");
  // Compteur fourni par le serveur, avec repli sur la liste si `sections_count` manque.
  expect(source).toContain("piece?.sections_count ?? (piece?.sections || []).length");
  // Libellé français correct : « 1 section », « 2 sections », rien quand il n'y en a pas.
  expect(source).toContain('`${n} section${n > 1 ? "s" : ""}`');
  expect(source).toMatch(/Number\.isFinite\(n\) && n > 0/);
  // Le nombre est présent dans le résumé (donc dans le title de la puce compacte)…
  const resumeBloc = source.slice(source.indexOf("function resume"), source.indexOf("function peutRetirer"));
  expect(resumeBloc).toContain("libelleSections(sections)");
  expect(source).toContain("title={`${texte} · ${etat[0]}");
  // …et dans la ligne complète, avec un data-testid et le sommaire en title, borné aux 8 premiers titres.
  expect(source).toContain("data-testid={`piece-sections-${piece.id}`}");
  expect(source).toContain("title={sommaireSections(piece) || undefined}");
  expect(source).toContain("MAX_TITRES_SOMMAIRE = 8");
  expect(source).toContain('`Sommaire : ${titres.join(" · ")}`');
  // Rien n'est rendu pour un document sans section.
  expect(source).toMatch(/sections > 0 && \(/);
});

test("les tableaux détectés sont comptés, nommés et jamais linkifiés", () => {
  const pieces = lire("components/case/PiecesJointes.jsx");
  // Compteur fourni par le serveur, avec repli sur la liste comme pour les sections.
  expect(pieces).toContain("piece?.tables_count ?? (piece?.tables || []).length");
  // Libellé français correct : « 1 tableau », « 2 tableaux », rien quand il n'y en a pas.
  expect(pieces).toContain('`${n} tableau${n > 1 ? "x" : ""}`');
  expect(pieces).toMatch(/Number\.isFinite\(n\) && n > 0/);
  const resumeBloc = pieces.slice(pieces.indexOf("function resume"), pieces.indexOf("function peutRetirer"));
  expect(resumeBloc).toContain("libelleTableaux(tableaux)");
  // La ligne complète porte un data-testid et un title borné aux 8 premiers titres de tableaux.
  expect(pieces).toContain("data-testid={`piece-tables-${piece.id}`}");
  expect(pieces).toContain("title={sommaireTableaux(piece) || undefined}");
  expect(pieces).toContain("MAX_TITRES_TABLEAUX = 8");
  expect(pieces).toContain('`Tableaux : ${titres.join(" · ")}`');
  expect(pieces).toMatch(/tableaux > 0 && \(/);

  // Une citation de tableau reste du texte : elle ne devient jamais un lien de section.
  const markdown = lire("components/MarkdownFlore.jsx");
  expect(markdown).toContain('chaine[decalage + _m.length] === ":"');
});

test("la réinitialisation de la démo n'est proposée qu'en mode démo", () => {
  const source = lire("pages/Administration.jsx");
  expect(source).toContain('authMode === "demo"');
  expect(source).toContain('data-testid="reset-demo-btn"');
});

test("les actions d'écriture ne sont proposées qu'aux contributeurs", () => {
  const source = lire("pages/TravailDetail.jsx");
  expect(source).toContain("const peutDeposer = cas?.peut_deposer === true;");
  // Clore/Rouvrir reste réservé au responsable, et exige aussi le droit de déposer.
  const clore = source.indexOf('data-testid="travail-clore-btn"');
  expect(clore).toBeGreaterThan(-1);
  const ouvertureClore = source.lastIndexOf("{cas.peut_partager && peutDeposer && (", clore);
  expect(ouvertureClore).toBeGreaterThan(-1);
  expect(source.slice(ouvertureClore, clore)).not.toContain(")}");
  // « Marquer comme revu » et « Consigner une décision » sont réservés aux contributeurs.
  for (const testid of ['data-testid="travail-marquer-revu-btn"', 'data-testid="travail-consigner-decision-btn"']) {
    const bouton = source.indexOf(testid);
    expect(bouton).toBeGreaterThan(-1);
    const garde = source.slice(Math.max(0, bouton - 220), bouton);
    expect(garde).toContain("peutDeposer");
  }
  // Le bandeau « à revoir » cache aussi son bouton à un lecteur.
  const banniere = source.indexOf('data-testid="travail-marquer-revu-banner-btn"');
  expect(banniere).toBeGreaterThan(-1);
  expect(source.slice(Math.max(0, banniere - 120), banniere)).toContain("{peutDeposer && (");
  // Plus aucune action : le menu disparaît.
  expect(source).toContain("const actionsMenu = peutDeposer");
  expect(source).toContain("{actionsMenu && (");
  expect(source).toContain('data-testid="travail-menu-btn"');
  expect(source.indexOf("{actionsMenu && (")).toBeLessThan(source.indexOf('data-testid="travail-menu-btn"'));
});


test("le lien de partage ne promet pas plus que les droits", () => {
  const source = lire("components/case/PartagerTravail.jsx");
  expect(source).toContain("window.location.href");
  expect(source).toContain('data-testid="partage-lien-droits"');
  expect(source).toContain("n'ouvre rien à qui n'a pas déjà les droits");
});


test("le volet Sources & Jumeaux reprend aussi les jumeaux réellement consultés", () => {
  const source = lire("components/case/OngletTravail.jsx");
  expect(source).toContain("participantsMessages");
  expect(source).toContain("jumeaux_participants");
  expect(source).toContain("jumeauxVisibles");
});


test("le volet affiche les sources du jumeau consulté", () => {
  const source = lire("components/case/OngletTravail.jsx");
  expect(source).toContain("sources_detail");
  expect(source).toContain("source-detail-");
  expect(source).toContain("sources-jumeau-");
});


test("le volet s'ouvre une fois quand un jumeau consulté a des sources", () => {
  const source = lire("pages/TravailDetail.jsx");
  expect(source).toContain("participantsMessages");
  expect(source).toContain("voletAutoOuvert");
  expect(source).toContain("setVoletSourcesOuvert(true)");
});
