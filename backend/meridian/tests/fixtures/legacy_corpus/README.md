# Corpus legacy de référence

Petit corpus autonome utilisé par `test_legacy_corpus.py` pour prouver l'indexation
fédérée de bout en bout. Il ne dépend ni de CBM, ni d'une base de données, ni du réseau :
tous les fichiers sont locaux et les liens sont déduits des seules observations.

| Fichier | Ce qu'il prouve |
| --- | --- |
| `web/WEB-INF/web.xml` | Un descripteur web déclare le servlet `ClientServlet` et son mapping `/clients/*`, exploités par les liens JSP → servlet → classe Java. |
| `web/client.jsp` | Une page JSP contient un formulaire, un include et un forward, tous extraits structurellement. |
| `src/main/java/com/acme/ClientServlet.java` | La classe Java cible du servlet est résolue par son FQN `com.acme.ClientServlet`. |
| `src/main/java/com/acme/web/ClientController.java` | Un contrôleur Spring expose une route et référence l'entité JPA `Client`. |
| `src/main/java/com/acme/service/ClientService.java` | Un service Spring référence l'entité JPA par import et par champ. |
| `src/main/java/com/acme/domain/Client.java` | Une entité JPA annotée `@Entity` / `@Table` porte le nom de table `CLIENT`. |
| `src/main/resources/META-INF/ejb-jar.xml` | Un descripteur EJB expose une session bean, un MDB et une ressource référencée. |
| `cobol/PROG.cbl` | Le programme principal fait un `CALL 'SOUSPROG'`, un `COPY CLIENT` et déclare le dataset `CLIENT.FILE`. |
| `cobol/SOUSPROG.cbl` | Le sous-programme appelé existe et fournit la cible du lien `CALL`. |
| `cobol/CLIENT.cpy` | Le copybook copié existe et fournit la cible du lien `COPY`. |
| `jcl/LOAD.jcl` | Un job exécute `PGM=PROG` et alloue `DSN=CLIENT.FILE`, ce qui relie le JCL au COBOL et à son dataset. |
| `sql/schema.sql` | Un DDL déclare deux tables, des colonnes, une clé étrangère, une vue et un index. |
