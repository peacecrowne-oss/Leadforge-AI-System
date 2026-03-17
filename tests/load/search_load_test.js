import http from "k6/http";
import { check, sleep } from "k6";

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

  const res = http.post("http://localhost:8000/leads/search", payload, params);

  console.log(`STATUS: ${res.status}`);
  console.log(`BODY: ${res.body}`);

  check(res, {
    "status valid": (r) => r.status === 200 || r.status === 403,
  });

  sleep(1);
}
