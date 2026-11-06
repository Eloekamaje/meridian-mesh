import axios from "axios";

export const getAccount = (id) =>
  axios.get(`http://antifraude-backend:8080/internal/accounts/${id}`);
