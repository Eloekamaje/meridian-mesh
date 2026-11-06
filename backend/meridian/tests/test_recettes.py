"""Recettes déterministes (harness v3 §2.1) : pures, sans base, sans réseau, sans modèle."""
import pytest

from meridian.domain.recettes import PREDICATS, recette

V, N = "verifie", "non_appuye"


def test_predicats_et_predicat_sans_recette():
    assert PREDICATS == {
        "DECLARE_DEPENDANCE", "DEPEND_DE", "EXPOSE", "LIT_VARIABLE", "EXECUTE_IMAGE",
        "APPELLE", "COPIE", "EXECUTE", "LIT_DATASET", "REFERENCE",
        "TABLE", "STOCKE_DANS", "COMPOSANT_JEE", "INJECTE", "INTERFACE_UTILISATEUR",
    }
    assert recette("CONNAIT", "x", ["x"]) is None


@pytest.mark.parametrize("predicat", sorted(PREDICATS))
def test_lignes_vides_ou_absentes(predicat):
    assert recette(predicat, "x", []) == N
    assert recette(predicat, "x", ["", "   "]) == N
    assert recette(predicat, "x", None) == N


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("fastapi", ["fastapi==0.110.1"], V),
    ("fastapi", ["FastAPI>=0.1"], V),
    ("uvicorn", ["uvicorn[standard]>=0.29"], V),
    ("python-dotenv", ["python_dotenv==1.0"], V),
    ("react", ['    "react": "^18",'], V),
    ("@types/node", ['"@types/node": "^20"'], V),
    ("fastapi", ["fastapi = \"^0.110\""], V),
    ("github.com/gin-gonic/gin", ["\tgithub.com/gin-gonic/gin v1.9.1"], V),
    ("spring-boot-starter-web", ["<artifactId>spring-boot-starter-web</artifactId>"], V),
    ("fastapi", ["fastapi-users==12"], N),
    ("fastapi", ["my-fastapi==1"], N),
    ("fastapi", ["fastapi_utils==1"], N),
    ("fastapi", ["# fastapi==0.110"], N),
    ("fastapi", ["flask==3.0"], N),
])
def test_depend_de(objet, lignes, attendu):
    assert recette("DEPEND_DE", objet, lignes) == attendu
    assert recette("DECLARE_DEPENDANCE", objet, lignes) == attendu


GET_CX = "GET /connexions/{systeme}/{cxid}/perimetres"


@pytest.mark.parametrize("objet,lignes,attendu", [
    (GET_CX, ['@api_router.get("/connexions/{systeme}/{cxid}/perimetres")'], V),
    (GET_CX, ['@api_router.post("/connexions/{systeme}/{cxid}/perimetres")'], N),
    (GET_CX, ['@api_router.get("/connexions/{systeme}/{cxid}/autre")'], N),
    ("get /a/b", ['@router.get("/a/b")'], V),
    ("DELETE /items/{id}", ["router.delete('/items/:id', handler)"], V),
    ("GET /items/{id}", ['@app.route("/items/<int:id>")'], V),
    ("POST /items", ['@app.route("/items", methods=["GET", "POST"])'], V),
    ("PUT /items", ['@app.route("/items", methods=["GET", "POST"])'], N),
    ("GET /items", ['@app.route("/items")'], V),
    ("PATCH /items", ['@PatchMapping("/items")'], V),
    ("GET /items", ['@PostMapping("/items")'], N),
    ("GET /items", ['@RequestMapping(value = "/items", method = RequestMethod.GET)'], V),
    # préfixe de routeur absent de la ligne : le chemin cité est plus long, la fin correspond
    ("GET /api/v1/users/{id}", ['@router.get("/users/{uid}")'], V),
    ("GET /api/v1/users", ['@router.get("/accounts")'], N),
    # fin alignée sur un segment entier, pas sur une sous-chaîne
    ("GET /api/superusers", ['@router.get("/users")'], N),
    # une ligne dont le chemin est « / » n'appuie rien (trop ambigu), sauf la racine préfixée
    ("GET /api/users", ['@router.get("/")'], N),
    ("GET /api/", ['@api_router.get("/")'], V),
    # chemin de la ligne plus long que le chemin cité : non appuyé
    ("GET /users", ['@router.get("/api/users")'], N),
    # décorateur sur plusieurs lignes
    ("POST /items", ["@app.route(", '    "/items",', '    methods=["POST"])'], V),
    ("GET", ['@router.get("/x")'], N),
])
def test_expose(objet, lignes, attendu):
    assert recette("EXPOSE", objet, lignes) == attendu


@pytest.mark.parametrize("lignes,attendu", [
    (["      - SMTP_USER=${SMTP_USER}"], V),
    (["      SMTP_USER: ${SMTP_USER}"], V),
    (["SMTP_USER=bob"], V),
    (['  - "SMTP_USER=bob"'], V),
    (['user = os.environ["SMTP_USER"]'], V),
    (["user = os.environ.get('SMTP_USER', '')"], V),
    (['user = os.getenv("SMTP_USER")'], V),
    (["const u = process.env.SMTP_USER;"], V),
    (['const u = process.env["SMTP_USER"];'], V),
    (['u := os.Getenv("SMTP_USER")'], V),
    (["      SMTP_USERNAME: x"], N),
    (["      MY_SMTP_USER: x"], N),
    (["      smtp_user: x"], N),
    (["process.env.SMTP_USERNAME"], N),
    (["# SMTP_USER est lu ailleurs"], N),
])
def test_lit_variable(lignes, attendu):
    assert recette("LIT_VARIABLE", "SMTP_USER", lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("docker.io/library/traefik", ["    image: traefik:v3.1"], V),
    ("docker.io/library/traefik", ["    image: 'docker.io/library/traefik:v3.1'"], V),
    ("traefik", ["image: library/traefik"], V),
    ("docker.io/library/python", ["FROM python:3.11-slim"], V),
    ("python", ["from --platform=linux/amd64 python:3.11 AS build"], V),
    ("ghcr.io/org/app", ["image: ghcr.io/org/app@sha256:abc123"], V),
    ("localhost:5000/app", ["image: localhost:5000/app:2"], V),
    ("docker.io/library/traefik", ["    image: traefik-forward-auth:1"], N),
    ("docker.io/library/traefik", ["    image: nginx:1.25"], N),
    ("docker.io/library/traefik", ["    # image: traefik:v3"], N),
    ("ghcr.io/org/app", ["image: docker.io/org/app:1"], N),
    ("python", ["RUN pip install python"], N),
])
def test_execute_image(objet, lignes, attendu):
    assert recette("EXECUTE_IMAGE", objet, lignes) == attendu


def test_expose_la_racine_seulement_pour_la_racine():
    assert recette("EXPOSE", "GET /", ['@api_router.get("/")']) == "verifie"
    assert recette("EXPOSE", "GET /dossiers", ['@api_router.get("/")']) == "non_appuye"


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("SUBPROG", ["           CALL 'SUBPROG'."], V),
    ("SUBPROG", ['CALL "SUBPROG" USING SUBPROG-DATA'], V),
    ("subprog", ["call 'subprog'"], V),
    ("SUBPROG", ["CALL 'AUTRE'"], N),
    ("SUBPROG", ["CALL 'SUBPROG2'"], N),
    ("SUBPROG", ["RECALL 'SUBPROG'"], N),
    ("SUBPROG", ["* CALL 'SUBPROG'"], N),
    ("SUBPROG", ["      //* CALL 'SUBPROG'"], N),
    ("SUBPROG", ["-- CALL 'SUBPROG'"], N),
    ("SUBPROG", ["# CALL 'SUBPROG'"], N),
])
def test_appelle(objet, lignes, attendu):
    assert recette("APPELLE", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("COMMON", ["       COPY COMMON."], V),
    ("COMMON", ["COPY COMMON REPLACING ==A== BY ==B=="], V),
    ("common", ["copy common"], V),
    ("COMMON", ["COPY AUTRE"], N),
    ("COMMON", ["COPY COMMON-EXTRA"], N),
    ("COMMON", ["* COPY COMMON"], N),
    ("COMMON", ["      //* COPY COMMON"], N),
    ("COMMON", ["-- COPY COMMON"], N),
    ("COMMON", ["# COPY COMMON"], N),
])
def test_copie(objet, lignes, attendu):
    assert recette("COPIE", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("MAINPROG", ["//STEP1 EXEC PGM=MAINPROG"], V),
    ("CLEANUP", ["//STEP2 EXEC PROC=CLEANUP"], V),
    ("MAINPROG", ["       PROGRAM-ID. MAINPROG."], V),
    ("mainprog", ["program-id. mainprog."], V),
    ("MAINPROG", ["//STEP1 EXEC PGM=AUTRE"], N),
    ("MAINPROG", ["//STEP1 EXEC PGM=MAINPROG2"], N),
    ("MAINPROG", ["* EXEC PGM=MAINPROG"], N),
    ("MAINPROG", ["//* EXEC PGM=MAINPROG"], N),
    ("MAINPROG", ["-- EXEC PGM=MAINPROG"], N),
    ("MAINPROG", ["# EXEC PGM=MAINPROG"], N),
])
def test_execute(objet, lignes, attendu):
    assert recette("EXECUTE", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("ACME.CLIENTS", ["//IN DD DSN=ACME.CLIENTS,DISP=SHR"], V),
    ("ACME.CLIENTS", ["SELECT CLIENT-FILE ASSIGN TO ACME.CLIENTS."], V),
    ("acme.clients", ["//IN DD DSN=acme.clients,DISP=SHR"], V),
    ("ACME.CLIENTS", ["//IN DD DSN=OTHER.CLIENTS,DISP=SHR"], N),
    ("ACME.CLIENTS", ["//IN DD DSN=ACME.CLIENTS2,DISP=SHR"], N),
    ("ACME.CLIENTS", ["//IN DD DSN=ACME.CLIENTS.ARCHIVE,DISP=SHR"], N),
    ("ACME.CLIENTS", ["* DSN=ACME.CLIENTS"], N),
    ("ACME.CLIENTS", ["//* DSN=ACME.CLIENTS"], N),
    ("ACME.CLIENTS", ["-- DSN=ACME.CLIENTS"], N),
    ("ACME.CLIENTS", ["# DSN=ACME.CLIENTS"], N),
])
def test_lit_dataset(objet, lignes, attendu):
    assert recette("LIT_DATASET", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("AGENCE", ["FOREIGN KEY (AGENCE_ID) REFERENCES AGENCE(ID)"], V),
    ("CLIENTS", ['REFERENCES "CLIENTS" (ID)'], V),
    ("clients", ["references clients (id)"], V),
    ("CLIENTS", ["REFERENCES AUTRE (ID)"], N),
    ("CLIENTS", ["REFERENCES CLIENTS_ARCHIVE (ID)"], N),
    ("CLIENTS", ["REFERENCES CLIENTS.ARCHIVE (ID)"], N),
    ("CLIENTS", ["* REFERENCES CLIENTS"], N),
    ("CLIENTS", ["//* REFERENCES CLIENTS"], N),
    ("CLIENTS", ["-- REFERENCES CLIENTS"], N),
    ("CLIENTS", ["# REFERENCES CLIENTS"], N),
])
def test_reference(objet, lignes, attendu):
    assert recette("REFERENCE", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("CLIENTS", ["CREATE TABLE CLIENTS ("], V),
    ("clients", ["create table clients"], V),
    ("CLIENTS", ['CREATE TABLE IF NOT EXISTS "CLIENTS" ('], V),
    ("CLIENTS", ['@Table(name = "CLIENTS")'], V),
    ("CLIENTS", ['@javax.persistence.Table(name = "CLIENTS")'], V),
    ("APP.CLIENTS", ["CREATE TABLE APP.CLIENTS ("], V),
    ("CLIENTS", ["CREATE TABLE APP.CLIENTS ("], V),
    ("CLIENTS", ['CREATE TABLE "APP"."CLIENTS" ('], V),
    ("CLIENTS", ["CREATE TABLE APP.CLIENTS_ARCHIVE ("], N),
    ("CLIENTS", ["CREATE TABLE CLIENTS_ARCHIVE ("], N),
    ("CLIENTS", ["CREATE TABLE AUTRE ("], N),
    ("CLIENTS", ["-- CREATE TABLE CLIENTS ("], N),
    ("CLIENTS", ["# CREATE TABLE CLIENTS ("], N),
    ("CLIENTS", ["/* CREATE TABLE CLIENTS */"], N),
    ("CLIENTS", ['// @Table(name = "CLIENTS")'], N),
    ("CLIENTS", ['<!-- @Table(name = "CLIENTS") -->'], N),
])
def test_table(objet, lignes, attendu):
    assert recette("TABLE", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("ORDERS", ['@Table(name = "ORDERS")'], V),
    ("ORDERS", ["CREATE TABLE ORDERS ("], V),
    ("ORDERS", ["@Entity", "class Order {}"], N),
    ("ORDERS", ["-- CREATE TABLE ORDERS ("], N),
    ("ORDERS", ['// @Table(name = "ORDERS")'], N),
])
def test_stocke_dans(objet, lignes, attendu):
    assert recette("STOCKE_DANS", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("Stateless", ["@Stateless"], V),
    ("stateless", ["@javax.ejb.Stateless"], V),
    ("MessageDriven", ["@MessageDriven"], V),
    ("session", ["<session>"], V),
    ("session", ["<session-type>Stateless</session-type>"], N),
    ("message-driven", ["<message-driven>"], V),
    ("Stateless", ["@Stateful"], N),
    ("Stateless", ["// @Stateless"], N),
    ("Stateless", ["<!-- @Stateless -->"], N),
    ("session", ["<!-- <session> -->"], N),
])
def test_composant_jee(objet, lignes, attendu):
    assert recette("COMPOSANT_JEE", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("AuditService", ["@EJB", "private AuditService audit;"], V),
    ("ClientService", ["@Autowired private ClientService service;"], V),
    ("EntityManager", ['@PersistenceContext(unitName = "x")', "private EntityManager em;"], V),
    ("OrderRepository", ["@Inject", "private OrderRepository repo;"], V),
    ("AuditService", ["@Service", "private AuditService audit;"], N),
    ("AuditService", ["private AuditService audit;"], N),
    ("AuditService", ["// @EJB", "private AuditService audit;"], N),
    ("AuditService", ["/* @EJB */", "private AuditService audit;"], N),
    ("AuditService", ["<!-- @EJB private AuditService audit; -->"], N),
    ("javax.sql.DataSource", ["<resource-ref>",
                              "<res-type>javax.sql.DataSource</res-type>",
                              "</resource-ref>"], V),
    ("javax.sql.DataSource", ["<resource-ref>",
                              "<res-type>javax.sql.Other</res-type>",
                              "</resource-ref>"], N),
])
def test_injecte(objet, lignes, attendu):
    assert recette("INJECTE", objet, lignes) == attendu


@pytest.mark.parametrize("objet,lignes,attendu", [
    ("/clients/save", ['<form action="/clients/save" method="post">'], V),
    ("/clients/save", ["<html:form action='/clients/save'>"], V),
    ("/WEB-INF/pied.jsp", ['<jsp:include page="/WEB-INF/pied.jsp" />'], V),
    ("/WEB-INF/pied.jsp", ['<c:import url="/WEB-INF/pied.jsp" />'], V),
    ("/done.jsp", ['<jsp:forward page="/done.jsp" />'], V),
    ("/WEB-INF/entete.jspf", ['<%@ include file="/WEB-INF/entete.jspf" %>'], V),
    ("/clients/save", ["<form", '  action="/clients/save"', '  method="post">'], V),
    ("/clients/save", ['<form action="/other" method="post">'], N),
    ("/clients", ['<form action="/clients/save" method="post">'], N),
    ("/WEB-INF/pied.jsp", ['<jsp:include page="/WEB-INF/pied.jspf" />'], N),
    ("/clients/save", ['<!-- <form action="/clients/save"> -->'], N),
    ("/clients/save", ["<%-- <form action=\"/clients/save\"> --%>"], N),
    ("/clients/save", ['// <form action="/clients/save">'], N),
])
def test_interface_utilisateur(objet, lignes, attendu):
    assert recette("INTERFACE_UTILISATEUR", objet, lignes) == attendu
