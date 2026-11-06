<%@ page contentType="text/html;charset=UTF-8" %>
<!DOCTYPE html>
<html>
<body>
  <form action="/clients/save" method="post">
    <input type="text" name="nom"/>
    <input type="submit" value="Enregistrer"/>
  </form>
  <jsp:include page="/WEB-INF/header.jspf"/>
  <jsp:forward page="/WEB-INF/detail.jsp"/>
</body>
</html>
