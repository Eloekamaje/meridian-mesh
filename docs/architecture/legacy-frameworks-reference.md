# Legacy et frameworks de code — référence Méridian

**Date :** 2026-11-03  
**Objet :** cartographier les technologies legacy, les frameworks et les niveaux de couverture possibles.  
**Règle :** ce document décrit une **couverture**, pas une promesse de support.

---

## 1. Pourquoi une carte, pas une liste

Un système d’entreprise Legacy n’est pas seulement un langage. Il combine :

- un **langage** : COBOL, Java, C#, RPG…
- un **runtime** : JVM, .NET, CICS, batch, application server ;
- un **framework** : Spring, JSF, Struts, Rails, Laravel…
- un **descripteur** : `web.xml`, `pom.xml`, `applicationContext.xml`, JCL, copybook ;
- un **protocole** : SOAP, REST, MQ, EDI, DB2, VSAM ;
- une **UI** : JSP, JSF, WebForms, GWT, AngularJS, Flex ;
- une **donnée** : schéma, procédure stockée, fichier plat, ETL.

Méridian doit savoir **détecter** ces couches avant de prétendre les comprendre.

---

## 2. Niveaux de couverture

| Niveau | Nom | Preuve |
|---|---|---|
| L0 | Inventaire | fichier détecté, langage identifié |
| L1 | Indexé | symbole, classe, fonction, route ou fichier parsé |
| L2 | Citable | ligne/localator versionné, lecture vérifiable |
| L3 | Sémantique framework | controller, bean, entité, job, transaction |
| L4 | Claim | connaissance typée, prouvée |
| L5 | Impact | dépendance, appel, migration, rupture |

**Ne jamais confondre L1 et L4.**  
Un COBOL indexé n’est pas un COBOL compris.

---

## 3. Socle actuel

### Ce que la documentation CBM dit réellement

- **158 langages** dans les « Key facts » ; le marketing annonce 162 : écart documentaire à vérifier par version.
- **9 familles Hybrid LSP** : Python, TypeScript/JavaScript, PHP, C#, Go, C/C++, Java, Kotlin, Rust.
- **Java** est classé « Good » (75–89 %) et testé sur Spring PetClinic.
- **COBOL et XML** sont dans la liste « supported, not yet benchmarked », pas dans les langages
  principaux validés.
- **JSP n’est pas dans la liste des langages**.
- `check_index_coverage` vérifie des chemins/scopes précis ; **un résultat propre ne prouve pas
  que tout le dépôt est indexé**.
- `index_status` décrit l’état de l’index et sa fraîcheur, pas la couverture sémantique.
- Le mode `fast`, les limites de taille, `.gitignore`/`.cbmignore` et les filtres de découverte
  peuvent exclure des fichiers.


### Codebase-memory-mcp

- 162 langages via tree-sitter ;
- Hybrid LSP sur 9 familles : Python, TypeScript/JavaScript, PHP, C#, Go, C/C++, Java, Kotlin, Rust ;
- COBOL, XML, Fortran, Pascal, Ruby, Scala, Swift, Dart, SQL, YAML, Dockerfile, etc. indexés syntaxiquement.

### Méridian

- Claims code prouvés surtout sur les routes, variables, dépendances et images ;
- manifestes `requirements.txt`, `pyproject.toml`, `package.json`, `go.mod`, `pom.xml` ;
- WSDL/OpenAPI/XML partiels ;
- **pas de sémantique Spring/JEE/JSP** ;
- **pas de sémantique mainframe** ;
- Graphify MCP cartographie **Méridian**, pas un codebase client.

---

## 4. Langages legacy

| Famille | Exemples | Parsing CBM | Sémantique Méridian |
|---|---|---|---|
| Mainframe | COBOL, PL/I, RPG, Assembler, Natural, Easytrieve | COBOL complet ; PL/I et RPG structurels | partielle |
| Batch | JCL, REXX, CLIST, Control-M | JCL non | absente |
| Java/JVM | Java, Kotlin, Scala, Groovy | oui | Java partielle |
| .NET | C#, VB.NET, F# | C#/F# oui | partielle |
| Web dynamique | JSP, ASP, PHP, ColdFusion, CFML | PHP oui ; JSP/ASP non | absente |
| Scripting | Python, Ruby, Perl, Tcl, Lua | oui | partielle |
| Objet legacy | Delphi, PowerBuilder, VB6, FoxPro | PowerBuilder texte structurel, PBL binaire partiel | partielle |
| ERP | ABAP, Progress 4GL, Oracle Forms | ABAP structurel, Forms XML structurel, Progress non | partielle |
| Data | SQL, PL/SQL, T-SQL, stored procedures | SQL oui | partielle |
| UI legacy | JSF, Struts, GWT, ExtJS, AngularJS, Flex, Silverlight | JS/TS partiel | absente |

---

## 5. Frameworks et stacks

### Java / JEE

- Servlet, JSP, JSTL, JSF, Facelets ;
- EJB, JMS, JTA, JAX-RS, JAX-WS ;
- Spring MVC, Spring Boot, Spring Data, Spring Security, Spring Batch, Spring Integration ;
- Struts, Hibernate/JPA, MyBatis ;
- Tomcat, Jetty, WebLogic, WebSphere, JBoss/WildFly ;
- Maven, Gradle, `web.xml`, `applicationContext.xml`, `persistence.xml`.

**Couverture cible :** controllers, services, repositories, entités, transactions, routes, beans, configuration, JSP/taglibs.

### .NET

- ASP.NET WebForms, MVC, Web API, Core ;
- WCF, ASMX, IIS ;
- Entity Framework, Dapper, LINQ ;
- WinForms, WPF, Silverlight ;
- `web.config`, `.csproj`, `.sln`, `packages.config`.

### PHP

- Laravel, Symfony, WordPress, Drupal, CodeIgniter ;
- Composer, Blade, Twig, Doctrine.

### JavaScript / TypeScript

- Node, Express, NestJS, Next.js ;
- Angular, AngularJS, React, Vue, Svelte ;
- jQuery, ExtJS, GWT, Dojo, Backbone ;
- Webpack, Vite, Babel.

### Python

- Django, Flask, FastAPI, Pyramid ;
- SQLAlchemy, Pydantic, Celery.

### Ruby

- Rails, Sinatra, Sidekiq, Active Record.

### Intégration

- SOAP/WSDL, REST/OpenAPI, GraphQL, gRPC ;
- MQ, Kafka, EDI, file transfer ;
- TIBCO, MuleSoft, IBM ACE/IIB, webMethods, BizTalk.

### SaaS / ERP

- SAP ABAP, BAPI, IDoc, RFC, SAPUI5 ;
- Salesforce Apex, LWC, Visualforce ;
- ServiceNow Glide/Flow ;
- Oracle Forms/Reports/ADF, PL/SQL.

---

## 6. Legacy data et UI

### Données

- DB2, Oracle, SQL Server, VSAM, IMS ;
- procédures stockées, triggers, vues, packages ;
- ETL, fichiers plats, copybooks ;
- schémas XML/XSD.

### UI

- JSP, JSF, Struts, ASP.NET WebForms ;
- AngularJS, ExtJS, GWT, Flex, Silverlight ;
- WPF/WinForms, Delphi/VB6/PowerBuilder.

Une UI legacy doit être reliée aux routes, formulaires, services et données qu’elle expose.

---

## 7. Détection

Un pack framework doit détecter par :

1. extension : `.jsp`, `.jsf`, `.xhtml`, `.cshtml`, `.aspx`, `.vb`, `.pbl`, `.frm`, `.cbl`, `.jcl`, `.rpg`, `.abap`, `.cls` ;
2. manifeste : `pom.xml`, `build.gradle`, `web.xml`, `applicationContext.xml`, `persistence.xml`, `packages.config`, `composer.json`, `package.json`, `Gemfile`, `requirements.txt` ;
3. annotation/import : `@RestController`, `@Service`, `@Entity`, `@EJB`, `import javax.servlet`, `using System.Web` ;
4. descripteur de déploiement : Tomcat, WebLogic, IIS, CICS, batch ;
5. runtime observé : traces, logs, files d’attente.

Sans détection, on ne peut pas choisir le bon extracteur.

---

## 8. Packs à construire

| Pack | Priorité | Contenu |
|---|---|---|
| Java/JEE/Spring | P0 | Servlet, JSP, JSF, Spring, JPA, XML |
| Mainframe COBOL | P0 | COBOL, copybooks, CICS, DB2, JCL |
| .NET legacy | P1 | WebForms, MVC, WCF, EF, config |
| Oracle/PLSQL | P1 | packages, procédures, Forms/Reports |
| SAP/Salesforce/ServiceNow | P1 | ABAP, Apex/LWC, Glide |
| PHP/Ruby/Python legacy | P2 | Laravel, Symfony, Rails, Django |
| UI legacy | P2 | JSF, Struts, GWT, ExtJS, AngularJS |

---

## 9. Claims attendus

Exemples de Claims utiles :

- `EXPOSE` : route HTTP, opération SOAP, transaction CICS ;
- `DEPEND_DE` : bibliothèque, service, queue, table ;
- `LIT_VARIABLE` : configuration, environnement ;
- `PERSISTE_DANS` : entité → table ;
- `DECLENCHE` : job → programme → fichier ;
- `AFFICHE` : JSP/JSF → controller/service ;
- `CONSOMME` : service → API/queue ;
- `MIGRE_VERS` : legacy → cible.

Chaque Claim doit porter source, version, locator et preuve.

---

## 10. Limites actuelles

- CBM parse Java mais Méridian n’extrait pas les beans Spring.
- CBM parse COBOL mais pas les copybooks/CICS/DB2/JCL.
- JSP n’est pas dans les langages CBM.
- XML générique n’est pas une connaissance : seuls WSDL/OpenAPI/config sont exploités.
- Aucun corpus de test legacy multi-framework.
- Graphify ne remplace pas un analyseur de code client.

---

## 11. Règle produit

> Une technologie est « couverte » seulement si Méridian peut produire un **Claim prouvé** et l’utiliser dans un **impact**.

Sinon, elle est seulement **indexée** ou **citable**.

---

## 12. Prochaine étape

1. Inventorier un portfolio réel : extensions, manifests, frameworks, runtimes.
2. Construire le détecteur de stack.
3. Livrer le pack Java/JEE/Spring + JSP.
4. Livrer le pack COBOL/CICS/JCL.
5. Ajouter les corpus de test et les Claims.
6. Mesurer L0 → L5 par pack.
