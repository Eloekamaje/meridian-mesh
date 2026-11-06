# Pack Java / JEE / Spring

**Date :** 2026-11-03  
**Statut :** spécification de pack, non implémenté  
**But :** transformer le Java indexé en connaissance Spring/EJB/JEE prouvée.

## Principe

CBM fournit la base Java :

- classes, interfaces, méthodes ;
- annotations ;
- héritage et génériques ;
- appels et imports ;
- Hybrid LSP Java.

Méridian doit ajouter la **sémantique framework** :

```text
classe Java + annotation + descripteur + configuration
→ rôle framework
→ Claim prouvé
→ relation d’impact
```

## Spring Boot

### Détection

- `pom.xml` / `build.gradle` : `spring-boot-starter-*` ;
- `@SpringBootApplication` ;
- `application.yml` / `application.properties` ;
- `spring.factories`, `META-INF/spring/*` ;
- `@Configuration`, `@Bean`, `@ComponentScan`.

### Claims attendus

| Claim | Exemple |
|---|---|
| `EXPOSE` | `@RestController` + `@GetMapping("/owners")` |
| `DECLARE_BEAN` | `@Bean`, `@Service`, `@Repository`, `@Component` |
| `INJECTE` | `@Autowired`, constructeur injecté |
| `PERSISTE_DANS` | `@Entity` + `@Table` |
| `TRANSACTION` | `@Transactional` |
| `PLANIFIE` | `@Scheduled` |
| `ECOUTE` | `@EventListener`, `@KafkaListener`, `@RabbitListener` |
| `CONFIGURE` | propriété Spring lue par `@Value` ou `@ConfigurationProperties` |
| `SECURISE` | `@PreAuthorize`, `SecurityFilterChain` |

### Relations

```text
Controller → Service → Repository → Entity → Table
Configuration → Bean
Listener → Queue/Topic
Scheduler → Job
```

## JEE / Jakarta EE

### Détection

- `web.xml`, `ejb-jar.xml`, `application.xml`, `persistence.xml` ;
- `@WebServlet`, `@WebFilter`, `@WebListener` ;
- `@Stateless`, `@Stateful`, `@Singleton`, `@MessageDriven` ;
- `@EJB`, `@Inject`, `@Resource`, `@PersistenceContext` ;
- `@Path`/`@GET` JAX-RS, `@WebService` JAX-WS ;
- `@TransactionAttribute`, JMS, JTA, JNDI.

### Claims attendus

| Claim | Exemple |
|---|---|
| `EXPOSE` | Servlet, JAX-RS, JAX-WS |
| `DECLARE_BEAN` | EJB session bean, CDI bean |
| `INJECTE` | `@EJB`, `@Inject`, JNDI |
| `ECOUTE` | MDB + JMS destination |
| `TRANSACTION` | `@TransactionAttribute` |
| `DEPLOIE_SUR` | WebLogic, WebSphere, JBoss, Tomcat |
| `PERSISTE_DANS` | JPA `@Entity` |
| `SECURISE` | rôle JEE, contrainte `web.xml` |

## JSP / JSF

JSP n’est pas un langage CBM. Il faut un pack UI :

- JSP, JSTL, EL, taglibs ;
- formulaires et routes ;
- inclusions et templates ;
- JSF/Facelets, `xhtml`, managed beans ;
- lien JSP/JSF → Servlet/Controller → Service.

Sans ce pack, une application JEE est indexée côté Java mais **incomplète côté UI**.

## Struts / Hibernate / MyBatis

- Struts : `struts.xml`, actions, résultats, interceptors ;
- Hibernate : `@Entity`, mappings XML, sessions, transactions ;
- MyBatis : mappers XML, SQL, result maps.

Ces frameworks doivent être des sous-packs du pack Java, pas des parseurs génériques.

## Niveau de couverture actuel

| Élément | Indexé | Citable | Claim | Impact |
|---|---:|---:|---:|---:|
| Java | oui | oui | partiel | partiel |
| Spring Boot | oui | oui | **non** | non |
| EJB/JEE | oui | oui | **non** | non |
| JSP/JSF | non | non | non | non |
| Struts | partiel | partiel | non | non |

## Ordre de livraison

1. Détecteur de stack Java.
2. Extracteur Spring Boot : controllers, services, repositories, entities, config.
3. Extracteur EJB/JEE : servlets, session beans, MDB, JMS, JNDI, transactions.
4. Pack JSP/JSF.
5. Sous-packs Struts/Hibernate/MyBatis.
6. Corpus de test :
   - Spring PetClinic ;
   - application EJB minimale ;
   - application JSP/JSTL ;
   - application Struts.

## Règle

Une annotation Spring ou EJB n’est pas un Claim à elle seule.  
Il faut le rôle, la cible, la preuve, la version et l’impact.
