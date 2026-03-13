import http from "k6/http";
import { sleep } from "k6";

export const options = {
  vus: 20,
  duration: "30s"
};

export default function () {
  const campaignId = "TEST_CAMPAIGN_ID";

  http.post(`http://localhost:8000/campaigns/${campaignId}/run`);

  sleep(1);
}
