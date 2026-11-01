"""Schémas Mermaid : chaque flèche est une affirmation, gardée seulement si ce qui la fonde tient."""
from meridian.domain import schemas

C = {812: {"statut": "PROPOSED", "verification": {"etat": "verifie"}},
     813: {"statut": "PROPOSED", "verification": {"etat": "selon"}},
     814: {"statut": "PROPOSED", "verification": {"etat": "en_partie"}},
     815: {"statut": "ACCEPTED"},
     816: {"statut": "CONTESTED"},
     817: {"statut": "PROPOSED"}}
R = {"r1": {"etat": "confirmee"}, "r2": {"etat": "obsolete"}}


def bloc(*lignes):
    return "Voici.\n```mermaid\nflowchart LR\n" + "\n".join(lignes) + "\n```\nSuite."


def test_seules_les_fleches_fondees_restent_avec_leur_style_et_une_legende():
    texte = bloc("conduit[Conduit]", "conduit ==>|conserve tout| bdd[(Base)]  %% c:812",
                 "auteurs([Auteurs]) -->|rédigent| conduit  %% c:813",
                 "clients -->|appellent| conduit  %% c:814",       # en partie : pas dessinée
                 "x --> y",                                         # sans fondement
                 "a --> b  %% c:816", "a --> c  %% c:999",          # contestée, inconnue
                 "conduit -->|alerte| fraude  %% r:r1", "conduit --> paie  %% r:r2")
    sortie = schemas.verifier(texte, C, R)
    code = sortie.split("```mermaid\n")[1].split("```")[0]
    assert "c:812" in code and "c:813" in code and "r:r1" in code
    assert "c:814" not in code and "x --> y" not in code and "c:816" not in code and "c:999" not in code
    assert "r:r2" not in code
    assert "linkStyle 0 stroke:#34D399" in code and "linkStyle 1 stroke:#93C5FD" in code and "linkStyle 2 stroke:#34D399" in code
    assert "conduit[Conduit]" in code  # un nœud seul n'est pas une affirmation
    assert "vert = vérifié" in sortie and "bleu = d'après une seule source" in sortie
    assert "5 lien(s) non dessiné(s)" in sortie and sortie.startswith("Voici.") and sortie.endswith("Suite.")


def test_directives_dangereuses_et_styles_du_modele_retires():
    texte = bloc('%%{init: {"securityLevel": "loose"}}%%', 'click conduit "javascript:alert(1)"',
                 "linkStyle 0 stroke:red", "conduit --> bdd  %% c:815")
    code = schemas.verifier(texte, C).split("```mermaid\n")[1].split("```")[0]
    assert "securityLevel" not in code and "click" not in code and "stroke:red" not in code
    assert "linkStyle 0 stroke:#4ADE80,stroke-width:3px" in code  # validée par l'équipe


def test_schema_sans_aucune_fleche_fondee_n_est_pas_affiche():
    sortie = schemas.verifier(bloc("a --> b", "b --> c  %% c:814"), C)
    assert "```mermaid" not in sortie and "Schéma non affiché : 2 lien(s)" in sortie


def test_pas_encore_verifie_dessine_en_gris_et_chaine_refusee():
    sortie = schemas.verifier(bloc("a --> b  %% c:817", "a --> b --> c  %% c:812"), C)
    assert "stroke-dasharray:3 3" in sortie and "1 lien(s) non dessiné(s)" in sortie


def test_bloc_non_flowchart_ou_texte_sans_schema():
    assert schemas.verifier(bloc().replace("flowchart LR", "sequenceDiagram"), C).count("```mermaid") == 0
    assert schemas.verifier("Rien à dessiner.", C) == "Rien à dessiner."


def test_les_marques_de_fondement_ne_restent_pas_dans_le_texte():
    from meridian.adapters.outbound.llm import flore
    assert flore.retirer_citations("Elle échange avec Fraude [r:r1] et conserve tout [c:812].") == \
        "Elle échange avec Fraude et conserve tout."
    assert "%% c:812" in flore.retirer_citations("```mermaid\nflowchart LR\na --> b  %% c:812\n```")


def test_syntaxe_controlee_comme_dans_la_reponse_reelle_de_conduit():
    # Constaté : boîtes avec espaces (illisibles pour mermaid) et fondements sur des lignes à part.
    texte = bloc("Auteurs et lecteurs -->|publient| Appli  %% c:813",
                 "Appli[Conduit — publication] -->|conserve tout| Base[(Base de données)]  %% c:812",
                 "%% c:813")
    code = schemas.verifier(texte, C).split("```mermaid\n")[1].split("```")[0]
    assert "Auteurs et lecteurs" not in code and "Base[(Base de données)]" in code and "\n%% c:813" not in code
    assert schemas.RE_LIGNE_FLECHE.match("lecteurs([Lecteurs]) -->|parcourent| appli[Nom]")
    assert schemas.RE_LIGNE_FLECHE.match("a ==> b") and not schemas.RE_LIGNE_FLECHE.match("a b --> c")


def test_une_boite_gardee_garde_son_libelle_defini_sur_une_fleche_ecartee():
    texte = bloc("lecteurs([Lecteurs]) -->|parcourent| appli[Conduit — publication]  %% c:814",
                 "appli -->|conserve tout| base[(Base de données)]  %% c:812")
    code = schemas.verifier(texte, C).split("```mermaid\n")[1].split("```")[0]
    assert "appli[Conduit — publication]" in code and "lecteurs" not in code


def test_fondements_egares_hors_schema_retires():
    # Constaté : « %% c:3596 » laissé seul dans le texte, sous un schéma rejeté.
    sortie = schemas.verifier("Avant.\n\n%% c:3596\n\n%% c:1393\nAprès.", C)
    assert "%%" not in sortie and sortie.startswith("Avant.") and sortie.endswith("Après.")
    assert "%% c:812" in schemas.verifier(bloc("a --> b  %% c:812"), C)  # dans un schéma, il reste


def test_doublon_ecrit_a_la_main_retire_en_silence_quand_le_harness_a_dessine():
    # Constaté : « (Schéma non affiché : 6 lien(s)…) » sous le vrai schéma, à cause d'un second schéma écrit à la main.
    sortie = schemas.verifier(bloc("a --> b", "b --> c"), C, deja_dessine=True)
    assert "```mermaid" not in sortie and "non affiché" not in sortie and sortie.startswith("Voici.")
