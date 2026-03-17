import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 50,
  duration: "30s",
};

const token = __ENV.API_TOKEN;

export default function () {
  const params = {
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    }
  };

  // Step 1: Create a campaign
  const payload = JSON.stringify({ name: "Load Test Campaign", query: "AI startups" });
  const createRes = http.post("http://localhost:8000/campaigns", payload, params);

  console.log(`CREATE STATUS: ${createRes.status}`);
  console.log(`CREATE BODY: ${createRes.body}`);

  if (createRes.status !== 201) {
    check(createRes, {
      "campaign request completed": (r) => r.status >= 200 && r.status < 500
    });
    sleep(1);
    return;
  }

  // Step 2: Parse the campaign ID and run it
  const campaignId = createRes.json("id");
  const runRes = http.post(`http://localhost:8000/campaigns/${campaignId}/run`, null, params);

  console.log(`STATUS: ${runRes.status}`);
  console.log(`BODY: ${runRes.body}`);

  check(runRes, {
    "campaign request completed": (r) => r.status >= 200 && r.status < 500
  });

  sleep(1);
}
