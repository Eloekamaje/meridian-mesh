"""Le graphe d'appels et la preuve de ses flèches (plan de remédiation L0bis.1).

Avant la correction, `ligne_d_appel` retenait la **première ligne qui nommait** la fonction, en n'écartant que les
lignes de commentaire en début de ligne : une chaîne de caractères ou une mention sans appel devenaient le
« fondement » d'une arête. L'arête était juste, la preuve ne prouvait rien.
"""
from jumeau import appels

# Corps d'une fonction : la ligne 1 est l'en-tête, l'appel attendu est ligne 5.
CORPS = [
    "def run():",                                    # 1
    '    note = "load"',                             # 2  une chaîne, pas un appel
    "    # load later",                              # 3  un commentaire
    "    /* load */",                                # 4  un commentaire bloc
    "    return load(x)",                            # 5  le vrai appel
    "    # encore load( ici",                        # 6
]


def test_une_chaine_ou_un_commentaire_ne_fonde_pas_une_fleche():
    assert appels.ligne_d_appel(CORPS, 2, 6, "load") is None or appels.ligne_d_appel(CORPS, 2, 6, "load") == 5
    # isolé : sans appel réel, aucune ligne n'est retenue
    assert appels.ligne_d_appel(CORPS[1:4], 1, 3, "load") is None


def test_l_appel_reel_est_trouve():
    assert appels.ligne_d_appel(CORPS, 1, 6, "load") == 5


def test_un_appel_de_methode_est_un_appel():
    assert appels.ligne_d_appel(["    self.load(id)"], 1, 1, "load") == 1
    assert appels.ligne_d_appel(["    repo::load(id)"], 1, 1, "load") == 1


def test_une_mention_sans_appel_ne_fonde_rien():
    assert appels.ligne_d_appel(["    callback = load"], 1, 1, "load") is None
    assert appels.ligne_d_appel(["    return maybe"], 1, 1, "load") is None


def test_une_chaine_qui_nomme_la_fonction_est_masquee():
    lignes = ['    url = "load(id)"', "    pass"]
    assert appels.ligne_d_appel(lignes, 1, 2, "load") is None


def test_la_sonde_d_index_absent_repond_faux_sans_lever():
    from jumeau import cbm

    def en_panne(*a, **k):
        raise RuntimeError("projet inconnu")
    assert cbm.indexe({"index_code": "proj"}, appeler=en_panne) is False
    assert cbm.indexe({"index_code": "proj"}, appeler=lambda *a, **k: "{}") is True
    assert cbm.indexe({"index_code": ""}) is False
