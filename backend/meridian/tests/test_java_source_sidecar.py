"""Sidecar Java source : routes, annotations Spring/JEE/JPA, masquage et couverture."""
from meridian.adapters.outbound.connectors.java_source import JavaSourceSidecar

CONTROLEUR = """package com.acme.web;

import com.acme.service.ClientService;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/clients")
public class ClientController extends BaseController implements Auditable {
    private final ClientService service;

    public ClientController(ClientService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Client lire(@PathVariable Long id) {
        return service.lire(id);
    }

    @PostMapping(path = "/clients")
    @Transactional
    public Client creer(@RequestBody Client client) {
        return service.creer(client);
    }

    @DeleteMapping
    public void supprimer(Long id) {
    }

    @RequestMapping(value = "/legacy", method = RequestMethod.PUT)
    public void legacy() {
    }
}
"""

SERVICE_EJB = """package com.acme.ejb;

import javax.ejb.EJB;
import javax.ejb.Stateless;
import javax.persistence.EntityManager;
import javax.persistence.PersistenceContext;

@Stateless
public class ClientService {
    @PersistenceContext
    private EntityManager em;

    @EJB
    private AuditService audit;

    @PersistenceUnit
    private EntityManagerFactory emf;

    public Client trouver(Long id) {
        return em.find(Client.class, id);
    }
}
"""

ENTITE_JPA = """package com.acme.entity;

import java.util.List;
import javax.persistence.*;

@Entity
@Table(name = "CLIENTS")
public class Client {
    @Id
    @Column(name = "ID", nullable = false)
    private Long id;

    @Column(name = "NOM")
    private String nom;

    @OneToMany(mappedBy = "client")
    private List<Commande> commandes;

    @ManyToOne
    @JoinColumn(name = "CLIENT_ID")
    private Client parent;

    @NamedQuery(name = "Client.parNom", query = "select c from Client c where c.nom = :nom")
    public static Client parNom(String nom) {
        return null;
    }
}
"""


def _ecrire(base, relatif, contenu):
    chemin = base / relatif
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(contenu, bytes):
        chemin.write_bytes(contenu)
    else:
        chemin.write_text(contenu, encoding="utf-8")
    return chemin


def _par_kind(observations):
    resultat = {}
    for observation in observations:
        resultat.setdefault(observation.kind, []).append(observation)
    return resultat


def test_controleur_spring_routes_types_et_membres(tmp_path):
    _ecrire(tmp_path, "src/main/java/com/acme/web/ClientController.java", CONTROLEUR)
    observations = JavaSourceSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    assert all(o.provider == "java" for o in observations)
    assert all(o.parser == "java-structural" for o in observations)
    assert all(o.parser_version == "1" for o in observations)
    assert all(o.language == "java" for o in observations)
    assert all(o.status == "extracted" and o.confidence == 1.0 for o in observations)

    assert kinds["java_package"][0].symbol == "com.acme.web"
    assert {o.symbol for o in kinds["java_import"]} == {
        "com.acme.service.ClientService", "org.springframework.web.bind.annotation.*"}

    type_ = kinds["java_type"][0]
    assert (type_.symbol, type_.start) == ("ClientController", 6)
    assert type_.attributes["fqn"] == "com.acme.web.ClientController"
    assert type_.attributes["package"] == "com.acme.web"
    assert type_.attributes["type_kind"] == "class"
    assert type_.attributes["stereotype"] == "RestController"
    assert {"RestController", "RequestMapping"} <= set(type_.attributes["annotations"])

    assert [o.attributes["parent"] for o in kinds["java_extends"]] == ["BaseController"]
    assert [o.attributes["interface"] for o in kinds["java_implements"]] == ["Auditable"]

    routes = {o.symbol: o for o in kinds["spring_route"]}
    assert set(routes) == {
        "ANY /clients", "GET /{id}", "POST /clients", "DELETE /clients", "PUT /legacy"}
    get = routes["GET /{id}"]
    assert (get.attributes["method"], get.attributes["http_method"]) == ("GET", "GET")
    assert (get.attributes["value"], get.attributes["path"]) == ("/{id}", "/{id}")
    assert get.attributes["controller"] == "com.acme.web.ClientController"
    assert get.attributes["prefix"] == "/clients"
    assert routes["POST /clients"].attributes["method"] == "POST"
    assert routes["PUT /legacy"].attributes["method"] == "PUT"
    assert routes["DELETE /clients"].attributes["path"] == "/clients"
    assert routes["ANY /clients"].attributes["scope"] == "type"

    methodes = {o.symbol: o for o in kinds["java_method"]}
    assert {"ClientController", "lire", "creer", "supprimer", "legacy"} <= set(methodes)
    assert methodes["ClientController"].attributes["constructor"] is True
    assert methodes["lire"].attributes["return_type"] == "Client"
    assert methodes["lire"].attributes["owner"] == "com.acme.web.ClientController"
    assert "GetMapping" in methodes["lire"].attributes["annotations"]
    assert "Transactional" in methodes["creer"].attributes["annotations"]

    champ = next(o for o in kinds["java_field"] if o.symbol == "service")
    assert champ.attributes["type"] == "ClientService"
    assert champ.attributes["owner"] == "com.acme.web.ClientController"

    symboles_annotations = {o.symbol for o in kinds["java_annotation"]}
    assert {"RestController", "Transactional", "PathVariable", "RequestBody"} <= symboles_annotations


def test_service_ejb_et_entite_jpa(tmp_path):
    _ecrire(tmp_path, "src/com/acme/ejb/ClientService.java", SERVICE_EJB)
    _ecrire(tmp_path, "src/com/acme/entity/Client.java", ENTITE_JPA)
    observations = JavaSourceSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    composant = kinds["jee_component"][0]
    assert composant.symbol == "ClientService"
    assert composant.attributes["annotation"] == "Stateless"
    assert composant.attributes["framework"] == "jee"

    injections = {o.symbol: o for o in kinds["jee_injection"]}
    assert set(injections) == {"em", "audit", "emf"}
    assert injections["em"].attributes["annotation"] == "PersistenceContext"
    assert injections["audit"].attributes["annotation"] == "EJB"
    assert injections["emf"].attributes["annotation"] == "PersistenceUnit"

    entite = kinds["jpa_entity"][0]
    assert entite.symbol == "Client"
    assert entite.attributes["annotation"] == "Entity"
    assert entite.attributes["fqn"] == "com.acme.entity.Client"
    assert entite.attributes["table"] == "CLIENTS"

    table = kinds["jpa_table"][0]
    assert (table.symbol, table.attributes["table"]) == ("CLIENTS", "CLIENTS")

    colonnes = {o.symbol: o for o in kinds["jpa_column"]}
    assert {"id", "ID", "NOM", "CLIENT_ID"} <= set(colonnes)
    assert colonnes["ID"].attributes["column"] == "ID"
    assert colonnes["ID"].attributes["nullable"] == "false"
    assert colonnes["CLIENT_ID"].attributes["annotation"] == "JoinColumn"

    relations = {o.symbol: o for o in kinds["jpa_relation"]}
    assert set(relations) == {"commandes", "parent"}
    assert relations["commandes"].attributes["relation"] == "OneToMany"
    assert relations["commandes"].attributes["target"] == "Commande"
    assert relations["commandes"].attributes["mappedBy"] == "client"
    assert relations["parent"].attributes["target"] == "Client"

    requete = kinds["jpa_query"][0]
    assert requete.symbol == "Client.parNom"
    assert requete.attributes["query"] == "select c from Client c where c.nom = :nom"

    champ_id = next(o for o in kinds["java_field"] if o.symbol == "id")
    assert {"Id", "Column"} == set(champ_id.attributes["annotations"])


def test_annotations_dans_commentaires_et_chaines_ignorees(tmp_path):
    _ecrire(tmp_path, "Vrai.java", """package com.acme;

// @Service
/*
 * @RestController
 * @GetMapping("/faux")
 */
public class Vrai {
    private String url = "http://exemple/@Entity";
    // @Autowired
    /* @Bean */
    public String ping() { return "@GetMapping"; }
}
""")
    observations = JavaSourceSidecar().index(str(tmp_path))
    kinds = _par_kind(observations)

    assert set(kinds) == {"java_package", "java_type", "java_field", "java_method"}
    assert kinds["java_type"][0].symbol == "Vrai"
    assert kinds["java_type"][0].start == 8
    assert kinds["java_type"][0].attributes["annotations"] == []
    assert kinds["java_field"][0].start == 9
    assert kinds["java_method"][0].start == 12
    assert all("annotation" not in o.kind for o in observations)


def test_couverture_indexe_partiel_ignore_et_decouverte(tmp_path):
    _ecrire(tmp_path, "src/A.java", "package a;\npublic class A {}\n")
    _ecrire(tmp_path, "src/B.java", "package b;\npublic class B {}\n")
    _ecrire(tmp_path, "src/vide.java", "")

    for dossier in (".git", "target", "build", "node_modules"):
        _ecrire(tmp_path, f"{dossier}/Gen.java", "public class Gen {}")

    observations = JavaSourceSidecar().index(str(tmp_path))
    assert {o.file for o in observations} == {"src/A.java", "src/B.java"}

    decouverte = {ligne.file: ligne for ligne in JavaSourceSidecar().couverture(str(tmp_path))}
    assert set(decouverte) == {"src/A.java", "src/B.java", "src/vide.java"}
    assert decouverte["src/A.java"].statut == "indexe"
    assert decouverte["src/A.java"].language == "java"
    assert decouverte["src/vide.java"].statut in {"partiel", "ignore"}
    assert decouverte["src/vide.java"].raison

    explicite = {ligne.file: ligne for ligne in JavaSourceSidecar().couverture(
        str(tmp_path), fichiers=["src/notes.txt", "absent.java", "src/B.java"])}
    assert explicite["src/notes.txt"].statut == "partiel"
    assert explicite["src/notes.txt"].raison
    assert explicite["absent.java"].statut == "partiel"
    assert explicite["absent.java"].raison
    assert explicite["src/B.java"].statut == "indexe"

    limites = JavaSourceSidecar().index(str(tmp_path), fichiers=["src/B.java"])
    assert {o.file for o in limites} == {"src/B.java"}
    absolu = JavaSourceSidecar().index(
        str(tmp_path), fichiers=[str(tmp_path / "src" / "A.java")])
    assert {o.file for o in absolu} == {"src/A.java"}


def test_fichier_invalide_ou_illisible_non_fatal(tmp_path):
    _ecrire(tmp_path, "src/Casse.java", b"\xff\xfe\x00\x01\x02")

    observations = JavaSourceSidecar().index(str(tmp_path))
    assert isinstance(observations, list)

    couverture = {ligne.file: ligne for ligne in JavaSourceSidecar().couverture(str(tmp_path))}
    assert couverture["src/Casse.java"].statut in {"partiel", "ignore"}
    assert couverture["src/Casse.java"].raison

    (tmp_path / "Dossier.java").mkdir()
    explicite = {ligne.file: ligne for ligne in JavaSourceSidecar().couverture(
        str(tmp_path), fichiers=["Dossier.java", "absent.java"])}
    assert explicite["Dossier.java"].statut == "partiel"
    assert explicite["Dossier.java"].raison
    assert explicite["absent.java"].statut == "partiel"


def test_annotations_web_et_bean(tmp_path):
    _ecrire(tmp_path, "Web.java", """package com.acme.web;

import javax.servlet.annotation.*;

@WebServlet(name = "accueil", urlPatterns = {"/accueil", "/home"})
public class AccueilServlet extends HttpServlet {
    @Autowired
    private ClientService service;
}

@WebFilter(urlPatterns = "/*")
public class AuthFilter {
}

@WebListener
public class SessionListener {
}

@Configuration
class Config {
    @Bean
    public ClientService service() {
        return new ClientService();
    }
}
""")
    kinds = _par_kind(JavaSourceSidecar().index(str(tmp_path)))

    servlet = kinds["web_servlet"][0]
    assert servlet.symbol == "accueil"
    assert servlet.attributes["url_patterns"] == ["/accueil", "/home"]

    filtre = kinds["web_filter"][0]
    assert filtre.symbol == "AuthFilter"
    assert filtre.attributes["url_patterns"] == ["/*"]

    assert kinds["web_listener"][0].symbol == "SessionListener"

    injection = kinds["spring_injection"][0]
    assert (injection.symbol, injection.attributes["annotation"]) == ("service", "Autowired")

    bean = kinds["spring_bean"][0]
    assert (bean.symbol, bean.attributes["annotation"]) == ("service", "Bean")
    assert bean.attributes["method"] == "service"
