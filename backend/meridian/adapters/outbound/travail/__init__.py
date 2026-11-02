"""Fabrique des sources de travail : le domaine ne connaît que le port SourceTravail."""
from __future__ import annotations

from meridian.adapters.outbound.travail.azure import AzureDevOpsTravail
from meridian.adapters.outbound.travail.linear import LinearTravail
from meridian.adapters.outbound.travail.csv import CsvFinance, CsvIncidents, CsvPeople, CsvTravail
from meridian.adapters.outbound.travail.jira import JiraTravail

PROVIDERS = ("jira", "azure_devops", "linear", "csv")


def source_travail(source: dict):
    provider = str(source.get("provider") or "").strip().lower()
    configuration = dict(source.get("configuration") or {})
    if provider == "jira":
        return JiraTravail(configuration, secret_ref=source.get("secret_ref"))
    if provider in {"azure", "azure_devops", "azure-devops"}:
        return AzureDevOpsTravail(configuration, secret_ref=source.get("secret_ref"))
    if provider == "linear":
        return LinearTravail(configuration, secret_ref=source.get("secret_ref"))
    if provider == "csv":
        return CsvTravail(configuration)
    raise ValueError(f"provider de travail inconnu : {provider!r}")


def source_incidents(source: dict):
    provider = str(source.get("provider") or "").strip().lower()
    if provider in {"csv", "incidents-csv"}:
        return CsvIncidents(source.get("configuration") or {})
    raise ValueError(f"provider incidents inconnu : {provider!r}")


def source_people(source: dict):
    provider = str(source.get("provider") or "").strip().lower()
    if provider in {"csv", "people-csv"}:
        return CsvPeople(source.get("configuration") or {})
    raise ValueError(f"provider people inconnu : {provider!r}")


def source_finance(source: dict):
    provider = str(source.get("provider") or "").strip().lower()
    if provider in {"csv", "finance-csv"}:
        return CsvFinance(source.get("configuration") or {})
    raise ValueError(f"provider finance inconnu : {provider!r}")
