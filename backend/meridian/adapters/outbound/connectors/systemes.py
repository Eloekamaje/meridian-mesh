"""Systèmes branchés par connexion + périmètre (hors GitHub). Chaque module fournit PREFIXE (des identifiants de
connexion), SERVICE (nom affiché), identifiants, compte_du_jeton, perimetres, tester et source_de, et enregistre sa
fabrique de lecteur ; en ajouter un, c'est l'inscrire ici."""
from meridian.adapters.outbound.connectors import confluence
from meridian.adapters.outbound.connectors import datadog
from meridian.adapters.outbound.connectors import jira
from meridian.adapters.outbound.connectors import servicenow

SYSTEMES = {"confluence": confluence, "jira": jira, "servicenow": servicenow, "datadog": datadog}
