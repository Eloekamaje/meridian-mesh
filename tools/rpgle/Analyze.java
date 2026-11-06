import java.io.IOException;
import java.io.PrintStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.antlr.v4.runtime.ANTLRInputStream;
import org.antlr.v4.runtime.BaseErrorListener;
import org.antlr.v4.runtime.CommonTokenStream;
import org.antlr.v4.runtime.RecognitionException;
import org.antlr.v4.runtime.Recognizer;
import org.antlr.v4.runtime.Token;
import org.antlr.v4.runtime.TokenSource;
import org.antlr.v4.runtime.Vocabulary;
import org.antlr.v4.runtime.misc.Interval;
import org.antlr.v4.runtime.tree.ParseTree;
import org.antlr.v4.runtime.tree.ParseTreeWalker;
import org.antlr.v4.runtime.tree.TerminalNode;
import org.rpgleparser.RpgLexer;
import org.rpgleparser.RpgParser;
import org.rpgleparser.RpgParserBaseListener;
import org.rpgleparser.tokens.PreprocessTokenSource;
import org.rpgleparser.utils.FixedWidthBufferedReader;

/**
 * Analyse RPGLE/ILE RPG (fixed et free) avec le parseur ANTLR rpgleparser.
 *
 * Lit un fichier source et écrit sur stdout un JSON UTF-8 :
 *   fichier, statut, erreurs, tokens, noeuds (parse tree simplifié), symboles.
 *
 * La grammaire rpgleparser 1.0.0 attend un source de largeur fixe et le
 * directive /FREE pour le free-format : les sources **FREE sont normalisées
 * avant l'analyse (marqueur /FREE, indentation minimale de 6 colonnes).
 */
public final class Analyze {

    private static final int MAX_TOKENS = 20000;
    private static final int MAX_NOEUDS = 20000;
    private static final int MAX_SYMBOLES = 5000;
    private static final int MAX_ERREURS = 200;
    private static final int MAX_TEXTE = 300;
    private static final int MAX_TOKEN_TEXTE = 500;

    private static final Pattern RE_FREE_MARKER = Pattern.compile("^\\s*(?:\\*\\*FREE\\b|/FREE\\b)", Pattern.CASE_INSENSITIVE);
    private static final Pattern RE_FREE_DEBUT = Pattern.compile(
            "^(?:DCL-|CTL-OPT\\b|CALLP\\b|EXSR\\b|CHAIN\\b|READ\\b|READE\\b|READP\\b|READPE\\b|READC\\b|"
                    + "WRITE\\b|UPDATE\\b|DELETE\\b|SELECT\\b|BEGSR\\b|EXEC\\s+SQL\\b)",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern RE_CMD = Pattern.compile("^\\s*([A-Za-z]+)");
    private static final Pattern RE_FROM = Pattern.compile("\\bFROM\\s+([A-Za-z0-9_#@$./]+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern RE_INTO = Pattern.compile("\\bINTO\\s+([A-Za-z0-9_#@$./]+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern RE_UPDATE = Pattern.compile("^\\s*UPDATE\\s+([A-Za-z0-9_#@$./]+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern RE_DELETE = Pattern.compile("^\\s*DELETE\\s+FROM\\s+([A-Za-z0-9_#@$./]+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern RE_IDENT = Pattern.compile("^\\s*([A-Za-z0-9_#@$]+)");
    private static final Pattern RE_CALLP_NOSPACE = Pattern.compile(
            "(?i)(\\bCALLP(?:\\([^)]*\\))?\\s+[A-Za-z0-9_#@$]+)\\(");

    private Analyze() {
    }

    public static void main(String[] args) {
        PrintStream sortie = new PrintStream(System.out, true, StandardCharsets.UTF_8);
        String fichier = args.length > 0 ? args[0] : "";
        Map<String, Object> resultat = new LinkedHashMap<>();
        resultat.put("fichier", fichier);
        try {
            if (fichier.isEmpty()) {
                throw new IllegalArgumentException("chemin de fichier manquant");
            }
            Path chemin = Paths.get(fichier);
            String texte = lire(chemin);
            Map<String, Object> analyse = analyser(texte);
            resultat.putAll(analyse);
            resultat.put("fichier", fichier);
        } catch (Throwable erreur) {
            resultat.put("statut", "erreur");
            resultat.put("tokens", new ArrayList<>());
            resultat.put("noeuds", new ArrayList<>());
            resultat.put("symboles", new ArrayList<>());
            List<Object> erreurs = new ArrayList<>();
            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put("ligne", 0);
            detail.put("colonne", 0);
            detail.put("message", erreur.getClass().getSimpleName() + ": " + String.valueOf(erreur.getMessage()));
            erreurs.add(detail);
            resultat.put("erreurs", erreurs);
            resultat.put("tronque", false);
        }
        sortie.println(json(resultat));
        sortie.flush();
    }

    private static String lire(Path chemin) throws IOException {
        byte[] donnees = Files.readAllBytes(chemin);
        for (String nom : new String[]{"UTF-8", "windows-1252", "ISO-8859-1"}) {
            try {
                CharsetDecoder decodeur = Charset.forName(nom).newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT);
                CharBuffer tampon = decodeur.decode(ByteBuffer.wrap(donnees));
                String texte = tampon.toString();
                if (!texte.isEmpty() && texte.charAt(0) == '\uFEFF') {
                    texte = texte.substring(1);
                }
                return texte;
            } catch (CharacterCodingException | RuntimeException ignored) {
                // Essaie le prochain encodage.
            }
        }
        return new String(donnees, StandardCharsets.ISO_8859_1);
    }

    private static Map<String, Object> analyser(String texte) throws IOException {
        boolean free = estLibre(texte);
        String normalise = normaliser(texte, free);

        List<Map<String, Object>> erreurs = new ArrayList<>();
        final RpgLexer lexer = new RpgLexer(new ANTLRInputStream(new FixedWidthBufferedReader(normalise)));
        TokenSource source = new PreprocessTokenSource(lexer);
        final CommonTokenStream tokens = new CommonTokenStream(source);
        final RpgParser parser = new RpgParser(tokens);
        BaseErrorListener ecouteur = new BaseErrorListener() {
            @Override
            public void syntaxError(Recognizer<?, ?> recognizer, Object symbole, int ligne,
                                    int colonne, String message, RecognitionException exception) {
                if (erreurs.size() >= MAX_ERREURS) {
                    return;
                }
                Map<String, Object> detail = new LinkedHashMap<>();
                detail.put("ligne", ligne);
                detail.put("colonne", colonne);
                detail.put("message", message);
                detail.put("source", recognizer == parser ? "parser" : "lexer");
                erreurs.add(detail);
            }
        };
        lexer.removeErrorListeners();
        parser.removeErrorListeners();
        lexer.addErrorListener(ecouteur);
        parser.addErrorListener(ecouteur);

        ParseTree arbre = null;
        try {
            arbre = parser.r();
        } catch (Throwable erreur) {
            Map<String, Object> detail = new LinkedHashMap<>();
            detail.put("ligne", 0);
            detail.put("colonne", 0);
            detail.put("message", "parse interrompu: " + erreur.getClass().getSimpleName()
                    + ": " + String.valueOf(erreur.getMessage()));
            detail.put("source", "parser");
            erreurs.add(detail);
        }

        tokens.fill();
        List<Map<String, Object>> listeTokens = new ArrayList<>();
        Vocabulary vocabulaire = lexer.getVocabulary();
        int compteur = 0;
        for (Token token : tokens.getTokens()) {
            if (token.getType() == Token.EOF) {
                continue;
            }
            if (compteur++ >= MAX_TOKENS) {
                break;
            }
            Map<String, Object> entree = new LinkedHashMap<>();
            String type = vocabulaire.getSymbolicName(token.getType());
            if (type == null || type.isEmpty()) {
                type = vocabulaire.getDisplayName(token.getType());
            }
            entree.put("type", type == null ? "" : type);
            entree.put("texte", tronquer(token.getText(), MAX_TOKEN_TEXTE));
            entree.put("ligne", token.getLine());
            entree.put("colonne", token.getCharPositionInLine());
            entree.put("canal", token.getChannel());
            listeTokens.add(entree);
        }

        List<Map<String, Object>> noeuds = new ArrayList<>();
        List<Map<String, Object>> symboles = new ArrayList<>();
        if (arbre != null) {
            final boolean[] tronque = {false};
            ParseTreeWalker.DEFAULT.walk(new RpgParserBaseListener() {
                @Override
                public void enterEveryRule(org.antlr.v4.runtime.ParserRuleContext ctx) {
                    String regle = nomRegle(ctx);
                    if (noeuds.size() < MAX_NOEUDS) {
                        Map<String, Object> noeud = new LinkedHashMap<>();
                        noeud.put("regle", regle);
                        noeud.put("debut", ligneDebut(ctx));
                        noeud.put("fin", ligneFin(ctx));
                        noeud.put("texte", tronquer(texteSource(ctx), MAX_TEXTE));
                        noeuds.add(noeud);
                    } else {
                        tronque[0] = true;
                    }
                    if (symboles.size() < MAX_SYMBOLES && estSymbole(regle)) {
                        Map<String, Object> symbole = extraireSymbole(ctx, regle);
                        if (symbole != null) {
                            symboles.add(symbole);
                        }
                    }
                }
            }, arbre);
            if (tronque[0]) {
                erreurs.add(erreurSimple("analyse tronquée après " + MAX_NOEUDS + " noeuds"));
            }
        }

        String statut = arbre == null ? "erreur" : (erreurs.isEmpty() ? "ok" : "partiel");
        Map<String, Object> resultat = new LinkedHashMap<>();
        resultat.put("statut", statut);
        resultat.put("free", free);
        resultat.put("tokens", listeTokens);
        resultat.put("noeuds", noeuds);
        resultat.put("symboles", symboles);
        resultat.put("erreurs", erreurs);
        resultat.put("tronque", listeTokens.size() >= MAX_TOKENS || noeuds.size() >= MAX_NOEUDS
                || symboles.size() >= MAX_SYMBOLES);
        return resultat;
    }

    private static Map<String, Object> erreurSimple(String message) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("ligne", 0);
        detail.put("colonne", 0);
        detail.put("message", message);
        detail.put("source", "analyse");
        return detail;
    }

    private static boolean estLibre(String texte) {
        String[] lignes = texte.split("\\r\\n|\\r|\\n", -1);
        for (String ligne : lignes) {
            String nue = ligne.stripLeading();
            if (nue.isEmpty() || nue.startsWith("//")) {
                continue;
            }
            if (RE_FREE_MARKER.matcher(ligne).find()) {
                return true;
            }
            if (nue.startsWith("*") && !nue.startsWith("**FREE")) {
                continue;
            }
            return RE_FREE_DEBUT.matcher(nue).find();
        }
        return false;
    }

    private static String normaliser(String texte, boolean free) {
        if (!free) {
            return texte;
        }
        String[] lignes = texte.split("\\r\\n|\\r|\\n", -1);
        boolean aMarqueur = false;
        for (String ligne : lignes) {
            if (RE_FREE_MARKER.matcher(ligne).find()) {
                aMarqueur = true;
                break;
            }
        }
        StringBuilder sortie = new StringBuilder(texte.length() + lignes.length * 6);
        boolean marqueur = false;
        boolean dansLibre = !aMarqueur;
        for (int i = 0; i < lignes.length; i++) {
            String ligne = lignes[i];
            String nue = ligne.stripLeading();
            if (RE_FREE_MARKER.matcher(ligne).find()) {
                if (!marqueur) {
                    sortie.append("      /FREE");
                    marqueur = true;
                }
                dansLibre = true;
            } else if (!dansLibre) {
                sortie.append(ligne);
            } else if (nue.isEmpty()) {
                sortie.append("");
            } else {
                sortie.append(RE_CALLP_NOSPACE.matcher(indenter6(ligne)).replaceAll("$1 ("));
            }
            if (i < lignes.length - 1) {
                sortie.append('\n');
            }
        }
        return sortie.toString();
    }

    private static String indenter6(String ligne) {
        int espaces = 0;
        while (espaces < ligne.length() && (ligne.charAt(espaces) == ' ' || ligne.charAt(espaces) == '\t')) {
            espaces++;
        }
        if (espaces >= 6) {
            return ligne;
        }
        return "      ".substring(espaces) + ligne;
    }

    private static String nomRegle(org.antlr.v4.runtime.ParserRuleContext ctx) {
        int index = ctx.getRuleIndex();
        if (index >= 0 && index < RpgParser.ruleNames.length) {
            return RpgParser.ruleNames[index];
        }
        return "?";
    }

    private static boolean estSymbole(String regle) {
        switch (regle) {
            case "fspec":
            case "fspec_fixed":
            case "dcl_pr":
            case "freeBeginProcedure":
            case "psBegin":
            case "dspec":
            case "dspec_fixed":
            case "dcl_ds":
            case "dcl_ds_field":
            case "op_callp":
            case "op_exsr":
            case "csCALLP":
            case "csEXSR":
            case "csCALL":
            case "cspec_fixed_x2":
            case "op_chain":
            case "op_read":
            case "op_readc":
            case "op_reade":
            case "op_readp":
            case "op_readpe":
            case "op_write":
            case "op_update":
            case "op_delete":
            case "op_select":
            case "csCHAIN":
            case "csREAD":
            case "csREADC":
            case "csREADE":
            case "csREADP":
            case "csREADPE":
            case "csWRITE":
            case "csUPDATE":
            case "csDELETE":
            case "csSELECT":
            case "exec_sql":
            case "cspec_fixed_sql":
                return true;
            default:
                return false;
        }
    }

    private static Map<String, Object> extraireSymbole(org.antlr.v4.runtime.ParserRuleContext ctx, String regle) {
        String cible = cible(ctx, regle);
        String operation = "";
        String table = "";
        String sql = "";
        if ("exec_sql".equals(regle) || "cspec_fixed_sql".equals(regle)) {
            sql = texteSql(ctx, regle);
            operation = commandeSql(sql);
            table = tableSql(operation, sql);
            cible = table.isEmpty() ? operation : table;
        } else if (estOperation(regle)) {
            operation = operation(ctx, regle);
            if (cible.isEmpty()) {
                cible = operation;
            }
        }
        if (!"exec_sql".equals(regle) && !"cspec_fixed_sql".equals(regle)) {
            cible = sansIndex(cible);
        }
        String proc = procedure(ctx);
        if ("freeBeginProcedure".equals(regle) || "psBegin".equals(regle) || "dcl_pr".equals(regle)) {
            proc = cible;
        }
        if (cible.isEmpty() && !"op_select".equals(regle) && !"csSELECT".equals(regle)) {
            return null;
        }
        Map<String, Object> symbole = new LinkedHashMap<>();
        symbole.put("regle", regle);
        symbole.put("cible", cible);
        symbole.put("debut", ligneDebut(ctx));
        symbole.put("fin", ligneFin(ctx));
        symbole.put("texte", tronquer(texteSource(ctx), MAX_TEXTE));
        symbole.put("tokens", jetons(ctx));
        symbole.put("proc", proc);
        if (!operation.isEmpty()) {
            symbole.put("operation", operation);
        }
        if (!table.isEmpty()) {
            symbole.put("table", table);
        }
        return symbole;
    }

    private static boolean estOperation(String regle) {
        switch (regle) {
            case "op_chain":
            case "op_read":
            case "op_readc":
            case "op_reade":
            case "op_readp":
            case "op_readpe":
            case "op_write":
            case "op_update":
            case "op_delete":
            case "op_select":
            case "csCHAIN":
            case "csREAD":
            case "csREADC":
            case "csREADE":
            case "csREADP":
            case "csREADPE":
            case "csWRITE":
            case "csUPDATE":
            case "csDELETE":
            case "csSELECT":
                return true;
            default:
                return false;
        }
    }

    private static String operation(org.antlr.v4.runtime.ParserRuleContext ctx, String regle) {
        switch (regle) {
            case "op_chain":
            case "csCHAIN":
                return "CHAIN";
            case "op_read":
            case "csREAD":
                return "READ";
            case "op_readc":
            case "csREADC":
                return "READC";
            case "op_reade":
            case "csREADE":
                return "READE";
            case "op_readp":
            case "csREADP":
                return "READP";
            case "op_readpe":
            case "csREADPE":
                return "READPE";
            case "op_write":
            case "csWRITE":
                return "WRITE";
            case "op_update":
            case "csUPDATE":
                return "UPDATE";
            case "op_delete":
            case "csDELETE":
                return "DELETE";
            case "op_select":
            case "csSELECT":
                return "SELECT";
            default:
                return "";
        }
    }

    private static String cible(org.antlr.v4.runtime.ParserRuleContext ctx, String regle) {
        switch (regle) {
            case "fspec":
                return ctx instanceof RpgParser.FspecContext
                        ? texte(((RpgParser.FspecContext) ctx).filename()) : "";
            case "fspec_fixed":
                return cibleFspecFixe((RpgParser.Fspec_fixedContext) ctx);
            case "dcl_pr":
                return nomProcedure(ctx, texte(((RpgParser.Dcl_prContext) ctx).identifier()));
            case "freeBeginProcedure":
                return nomProcedure(ctx, texte(((RpgParser.FreeBeginProcedureContext) ctx).identifier()));
            case "psBegin":
                return texte(((RpgParser.PsBeginContext) ctx).ps_name());
            case "dspec":
                return cibleDspec((RpgParser.DspecContext) ctx);
            case "dspec_fixed":
                return texte(((RpgParser.Dspec_fixedContext) ctx).ds_name());
            case "dcl_ds":
                return cibleDclDs((RpgParser.Dcl_dsContext) ctx);
            case "dcl_ds_field":
                return premierIdentifiant(((RpgParser.Dcl_ds_fieldContext) ctx).identifier());
            case "op_callp":
                return identifiantDepuisTexte(texte(((RpgParser.Op_callpContext) ctx).identifier()));
            case "op_exsr":
                return texte(((RpgParser.Op_exsrContext) ctx).identifier());
            case "csCALLP":
                return identifiantDepuisTexte(texte(((RpgParser.CsCALLPContext) ctx).c_free()));
            case "csEXSR":
                return facteur2(((RpgParser.CsEXSRContext) ctx).cspec_fixed_standard_parts());
            case "csCALL":
                return nettoyerFacteur(facteur2(((RpgParser.CsCALLContext) ctx).cspec_fixed_standard_parts()));
            case "cspec_fixed_x2":
                return cibleCspecX2((RpgParser.Cspec_fixed_x2Context) ctx);
            case "op_chain":
                return dernierIdentifiant(((RpgParser.Op_chainContext) ctx).identifier());
            case "op_read":
                return premierIdentifiant(((RpgParser.Op_readContext) ctx).identifier());
            case "op_readc":
                return premierIdentifiant(((RpgParser.Op_readcContext) ctx).identifier());
            case "op_reade":
                return premierIdentifiant(((RpgParser.Op_readeContext) ctx).identifier());
            case "op_readp":
                return premierIdentifiant(((RpgParser.Op_readpContext) ctx).identifier());
            case "op_readpe":
                return premierIdentifiant(((RpgParser.Op_readpeContext) ctx).identifier());
            case "op_write":
                return premierIdentifiant(((RpgParser.Op_writeContext) ctx).identifier());
            case "op_update":
                return premierIdentifiant(((RpgParser.Op_updateContext) ctx).identifier());
            case "op_delete":
                return texte(((RpgParser.Op_deleteContext) ctx).identifier());
            case "op_select":
                return "";
            case "csCHAIN":
                return facteur2(((RpgParser.CsCHAINContext) ctx).cspec_fixed_standard_parts());
            case "csREAD":
                return facteur2(((RpgParser.CsREADContext) ctx).cspec_fixed_standard_parts());
            case "csREADC":
                return facteur2(((RpgParser.CsREADCContext) ctx).cspec_fixed_standard_parts());
            case "csREADE":
                return facteur2(((RpgParser.CsREADEContext) ctx).cspec_fixed_standard_parts());
            case "csREADP":
                return facteur2(((RpgParser.CsREADPContext) ctx).cspec_fixed_standard_parts());
            case "csREADPE":
                return facteur2(((RpgParser.CsREADPEContext) ctx).cspec_fixed_standard_parts());
            case "csWRITE":
                return facteur2(((RpgParser.CsWRITEContext) ctx).cspec_fixed_standard_parts());
            case "csUPDATE":
                return facteur2(((RpgParser.CsUPDATEContext) ctx).cspec_fixed_standard_parts());
            case "csDELETE":
                return facteur2(((RpgParser.CsDELETEContext) ctx).cspec_fixed_standard_parts());
            case "csSELECT":
                return "";
            default:
                return "";
        }
    }

    private static String cibleCspecX2(RpgParser.Cspec_fixed_x2Context ctx) {
        String texte = texteSource(ctx);
        if (texte == null || !texte.stripLeading().toUpperCase(Locale.ROOT).startsWith("CALLP")) {
            return "";
        }
        return identifiantDepuisTexte(texte(ctx.c_free()));
    }

    private static String cibleFspecFixe(RpgParser.Fspec_fixedContext ctx) {
        if (ctx.FS_RecordName() != null) {
            String nom = ctx.FS_RecordName().getText();
            if (nom != null && !nom.trim().isEmpty()) {
                return nom.trim();
            }
        }
        String texte = texteSource(ctx);
        if (texte.length() > 6) {
            int fin = Math.min(16, texte.length());
            return texte.substring(6, fin).trim();
        }
        return "";
    }

    private static String cibleDspec(RpgParser.DspecContext ctx) {
        if (ctx.DS_Standalone() != null) {
            return texte(ctx.identifier());
        }
        if (ctx.DEF_TYPE_S() != null) {
            return texte(ctx.ds_name());
        }
        return "";
    }

    private static String cibleDclDs(RpgParser.Dcl_dsContext ctx) {
        if (ctx.identifier() != null) {
            return texte(ctx.identifier());
        }
        return texte(ctx.ds_name());
    }

    private static String facteur2(RpgParser.Cspec_fixed_standard_partsContext parties) {
        if (parties == null || parties.factor() == null) {
            return "";
        }
        String valeur = texteSource(parties.factor()).trim();
        if (valeur.isEmpty() || "*BLANKS".equalsIgnoreCase(valeur)) {
            return "";
        }
        return valeur;
    }

    private static String nettoyerFacteur(String valeur) {
        String resultat = valeur == null ? "" : valeur.trim();
        if (resultat.length() >= 2
                && ((resultat.startsWith("'") && resultat.endsWith("'"))
                || (resultat.startsWith("\"") && resultat.endsWith("\"")))) {
            resultat = resultat.substring(1, resultat.length() - 1);
        }
        return resultat;
    }

    private static String sansIndex(String valeur) {
        if (valeur == null) {
            return "";
        }
        int position = valeur.indexOf('(');
        return position > 0 ? valeur.substring(0, position).trim() : valeur;
    }

    private static String identifiantDepuisTexte(String texte) {
        if (texte == null) {
            return "";
        }
        Matcher trouve = RE_IDENT.matcher(texte);
        return trouve.find() ? trouve.group(1) : "";
    }

    private static String premierIdentifiant(List<RpgParser.IdentifierContext> identifiants) {
        for (RpgParser.IdentifierContext identifiant : identifiants) {
            String valeur = texte(identifiant);
            if (!valeur.isEmpty()) {
                return valeur;
            }
        }
        return "";
    }

    private static String dernierIdentifiant(List<RpgParser.IdentifierContext> identifiants) {
        for (int i = identifiants.size() - 1; i >= 0; i--) {
            String valeur = texte(identifiants.get(i));
            if (!valeur.isEmpty()) {
                return valeur;
            }
        }
        return "";
    }

    private static String texte(org.antlr.v4.runtime.ParserRuleContext ctx) {
        if (ctx == null) {
            return "";
        }
        return unir(ctx.getText());
    }

    private static String texte(org.antlr.v4.runtime.tree.TerminalNode noeud) {
        if (noeud == null || noeud.getSymbol() == null) {
            return "";
        }
        return unir(noeud.getText());
    }

    private static String texteSql(org.antlr.v4.runtime.ParserRuleContext ctx, String regle) {
        StringBuilder brut = new StringBuilder();
        if ("exec_sql".equals(regle) && ctx instanceof RpgParser.Exec_sqlContext) {
            for (TerminalNode mot : ((RpgParser.Exec_sqlContext) ctx).WORDS()) {
                brut.append(mot.getText()).append(' ');
            }
        } else if (ctx instanceof RpgParser.Cspec_fixed_sqlContext) {
            for (TerminalNode mot : ((RpgParser.Cspec_fixed_sqlContext) ctx).CSQL_TEXT()) {
                brut.append(mot.getText()).append(' ');
            }
        }
        if (brut.length() == 0) {
            brut.append(texteSource(ctx));
        }
        String valeur = brut.toString();
        valeur = valeur.replaceAll("(?is)^\\s*C?/\\s*EXEC\\s+SQL\\s*", " ");
        valeur = valeur.replaceAll("(?is)^\\s*EXEC\\s+SQL\\s*", " ");
        valeur = valeur.replaceAll("(?is)\\bEND-EXEC\\b.*$", " ");
        valeur = valeur.replaceAll("(?m)^\\s*C\\+\\s*", " ");
        return unir(valeur);
    }

    private static String commandeSql(String sql) {
        Matcher trouve = RE_CMD.matcher(sql == null ? "" : sql);
        return trouve.find() ? trouve.group(1).toUpperCase(Locale.ROOT) : "";
    }

    private static String tableSql(String commande, String sql) {
        if (sql == null || sql.isEmpty()) {
            return "";
        }
        Matcher trouve;
        if ("SELECT".equals(commande) || "DELETE".equals(commande)) {
            trouve = RE_FROM.matcher(sql);
        } else if ("INSERT".equals(commande) || "MERGE".equals(commande)) {
            trouve = RE_INTO.matcher(sql);
        } else if ("UPDATE".equals(commande)) {
            trouve = RE_UPDATE.matcher(sql);
        } else {
            return "";
        }
        if (!trouve.find()) {
            return "";
        }
        String table = trouve.group(1);
        return table == null ? "" : table;
    }

    private static String procedure(org.antlr.v4.runtime.ParserRuleContext ctx) {
        for (org.antlr.v4.runtime.ParserRuleContext parent = ctx.getParent(); parent != null; parent = parent.getParent()) {
            if (parent instanceof RpgParser.FreeBeginProcedureContext) {
                return nomProcedure(parent, texte(((RpgParser.FreeBeginProcedureContext) parent).identifier()));
            }
            if (parent instanceof RpgParser.PsBeginContext) {
                return texte(((RpgParser.PsBeginContext) parent).ps_name());
            }
            if (parent instanceof RpgParser.Dcl_prContext) {
                return nomProcedure(parent, texte(((RpgParser.Dcl_prContext) parent).identifier()));
            }
            if (parent instanceof RpgParser.ProcedureContext) {
                RpgParser.BeginProcedureContext debut = ((RpgParser.ProcedureContext) parent).beginProcedure();
                if (debut != null && debut.freeBeginProcedure() != null) {
                    return nomProcedure(debut.freeBeginProcedure(),
                            texte(debut.freeBeginProcedure().identifier()));
                }
                if (debut != null && debut.psBegin() != null) {
                    return texte(debut.psBegin().ps_name());
                }
            }
        }
        return "";
    }

    private static String nomProcedure(org.antlr.v4.runtime.ParserRuleContext ctx, String nom) {
        if (nom != null && !nom.isEmpty()) {
            return nom;
        }
        Pattern motif = Pattern.compile("(?i)\\bDCL-(?:PROC|PI)\\s+([A-Za-z0-9_#@$]+)");
        Matcher trouve = motif.matcher(texteSource(ctx));
        if (trouve.find()) {
            return trouve.group(1);
        }
        for (org.antlr.v4.runtime.ParserRuleContext parent = ctx.getParent();
             parent != null; parent = parent.getParent()) {
            if (parent instanceof RpgParser.ProcedureContext) {
                trouve = motif.matcher(texteSource(parent));
                if (trouve.find()) {
                    return trouve.group(1);
                }
            }
        }
        return "";
    }

    private static int ligneDebut(org.antlr.v4.runtime.ParserRuleContext ctx) {
        return ctx.getStart() == null ? 0 : Math.max(0, ctx.getStart().getLine());
    }

    private static int ligneFin(org.antlr.v4.runtime.ParserRuleContext ctx) {
        if (ctx.getStop() != null) {
            return Math.max(ligneDebut(ctx), ctx.getStop().getLine());
        }
        return ligneDebut(ctx);
    }

    private static String texteSource(org.antlr.v4.runtime.ParserRuleContext ctx) {
        if (ctx.getStart() == null || ctx.getStop() == null) {
            return ctx.getText();
        }
        if (ctx.getStart().getInputStream() == null) {
            return ctx.getText();
        }
        int debut = ctx.getStart().getStartIndex();
        int fin = ctx.getStop().getStopIndex();
        if (debut < 0 || fin < debut) {
            return ctx.getText();
        }
        try {
            return ctx.getStart().getInputStream().getText(Interval.of(debut, fin));
        } catch (RuntimeException ignored) {
            return ctx.getText();
        }
    }

    private static List<String> jetons(org.antlr.v4.runtime.ParserRuleContext ctx) {
        List<String> resultat = new ArrayList<>();
        collecterJetons(ctx, resultat, 200);
        return resultat;
    }

    private static void collecterJetons(ParseTree arbre, List<String> resultat, int maximum) {
        if (resultat.size() >= maximum) {
            return;
        }
        if (arbre instanceof TerminalNode) {
            TerminalNode terminal = (TerminalNode) arbre;
            Token token = terminal.getSymbol();
            if (token == null || token.getType() == Token.EOF) {
                return;
            }
            String valeur = terminal.getText();
            if (valeur != null && !valeur.trim().isEmpty()) {
                resultat.add(tronquer(valeur, MAX_TOKEN_TEXTE));
            }
            return;
        }
        for (int i = 0; i < arbre.getChildCount(); i++) {
            collecterJetons(arbre.getChild(i), resultat, maximum);
        }
    }

    private static String unir(String valeur) {
        return valeur == null ? "" : valeur.replaceAll("\\s+", " ").trim();
    }

    private static String tronquer(String valeur, int maximum) {
        if (valeur == null) {
            return "";
        }
        return valeur.length() <= maximum ? valeur : valeur.substring(0, maximum);
    }

    private static String json(Object valeur) {
        StringBuilder sortie = new StringBuilder();
        ecrireJson(valeur, sortie);
        return sortie.toString();
    }

    @SuppressWarnings("unchecked")
    private static void ecrireJson(Object valeur, StringBuilder sortie) {
        if (valeur == null) {
            sortie.append("null");
        } else if (valeur instanceof String) {
            sortie.append('"').append(echapper((String) valeur)).append('"');
        } else if (valeur instanceof Boolean || valeur instanceof Number) {
            sortie.append(valeur);
        } else if (valeur instanceof Map) {
            sortie.append('{');
            boolean premier = true;
            for (Map.Entry<String, Object> entree : ((Map<String, Object>) valeur).entrySet()) {
                if (!premier) {
                    sortie.append(',');
                }
                premier = false;
                sortie.append('"').append(echapper(entree.getKey())).append("\":");
                ecrireJson(entree.getValue(), sortie);
            }
            sortie.append('}');
        } else if (valeur instanceof Iterable) {
            sortie.append('[');
            boolean premier = true;
            for (Object element : (Iterable<Object>) valeur) {
                if (!premier) {
                    sortie.append(',');
                }
                premier = false;
                ecrireJson(element, sortie);
            }
            sortie.append(']');
        } else {
            sortie.append('"').append(echapper(String.valueOf(valeur))).append('"');
        }
    }

    private static String echapper(String valeur) {
        StringBuilder sortie = new StringBuilder(valeur.length() + 16);
        for (int i = 0; i < valeur.length(); i++) {
            char caractere = valeur.charAt(i);
            switch (caractere) {
                case '"':
                    sortie.append("\\\"");
                    break;
                case '\\':
                    sortie.append("\\\\");
                    break;
                case '\n':
                    sortie.append("\\n");
                    break;
                case '\r':
                    sortie.append("\\r");
                    break;
                case '\t':
                    sortie.append("\\t");
                    break;
                default:
                    if (caractere < 0x20) {
                        sortie.append(String.format("\\u%04x", (int) caractere));
                    } else {
                        sortie.append(caractere);
                    }
            }
        }
        return sortie.toString();
    }
}
