import http from "k6/http";
import { sleep } from "k6";

export const options = {
  vus: 50,
  duration: "30s",
};

// Token should be read from environment variable
const token = __ENV.API_TOKEN;

export default function () {

  const payload = JSON.stringify({
    keywords: "software engineer",
    location: "San Francisco",
    limit: 5
  });

  const params = {
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    }
  };

  http.post("http://localhost:8000/leads/search", payload, params);

  sleep(1);
}
