import ws from "k6/ws";
import { check, sleep } from "k6";

export const options = {
  scenarios: {
    ws_connections: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 10 },
        { duration: "60s", target: 50 },
        { duration: "60s", target: 50 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    ws_connecting: ["p(95)<500"],
    ws_msgs_received: ["count>100"],
  },
};

export default function () {
  const url = `${__ENV.TARGET_URL}/ws/collab/test-file-id/?token=test`;
  const res = ws.connect(url, {}, function (socket) {
    socket.on("open", () => {
      socket.send(
        JSON.stringify({
          type: "sync_request",
          file_id: "test-file-id",
          last_known_version: 0,
          client_state_vector: "",
        }),
      );
    });
    socket.on("message", (data) => {
      check(JSON.parse(data), { "valid message": (m) => m.type !== undefined });
    });
    socket.setTimeout(() => socket.close(), 120000);
  });
  check(res, { connected: (r) => r && r.status === 101 });
  sleep(1);
}
