"""Routage Bedrock : un rôle, un modèle, une région ; le profil AWS reste externe."""
from meridian.adapters.outbound import bedrock_router


def test_les_roles_resolvent_des_modeles_distincts(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODELES", '{"chat":"chat-v1","vision":"vision-v1","embedding":"emb-v1"}')
    assert bedrock_router.modele_id("chat") == "chat-v1"
    assert bedrock_router.modele_id("vision") == "vision-v1"
    assert bedrock_router.modele_id("embedding") == "emb-v1"


def test_un_role_inconnu_retombe_sur_chat(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODELES", '{"chat":"chat-v1"}')
    assert bedrock_router.modele_id("inconnu") == "chat-v1"


def test_la_region_canadienne_est_le_defaut(monkeypatch):
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("AWS_REGION", raising=False)
    assert bedrock_router.region() == "ca-central-1"
