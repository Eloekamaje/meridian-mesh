import axios from "axios";

export const payer = (jeton) =>
  axios.post("https://api.stripe.com/v1/charges", jeton);
