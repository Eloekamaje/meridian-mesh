"""Systèmes branchés par connexion + périmètre (hors GitHub). Chaque module fournit PREFIXE (des identifiants de
connexion), SERVICE (nom affiché), identifiants, compte_du_jeton, perimetres, tester et source_de, et enregistre sa
fabrique de lecteur ; en ajouter un, c'est l'inscrire ici."""
from jumeau import confluence, jira

SYSTEMES = {"confluence": confluence, "jira": jira}
