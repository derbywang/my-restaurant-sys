// Test helper (ury/ury/api/test_realtime_reach.py): connects to the real Socket.IO server as the given users and
// prints every event they receive.  usage: node realtime_probe.js <site> <password> <seconds after ready> user...
// prints: CONNECTED <user> | CONNECT_ERROR <user>: <msg> | READY | RESULT {"events": {user: [{ev, msg}]}, "sids": {user: sid}}
const http = require("http");
const { io } = require("socket.io-client");

const [site, password, seconds, ...users] = process.argv.slice(2);

function login(usr) {
	return new Promise((resolve, reject) => {
		const body = `usr=${encodeURIComponent(usr)}&pwd=${encodeURIComponent(password)}`;
		const req = http.request(
			{ host: "127.0.0.1", port: 8000, path: "/api/method/login", method: "POST",
			  headers: { Host: `${site}:8000`, "Content-Type": "application/x-www-form-urlencoded", "Content-Length": Buffer.byteLength(body) } },
			(res) => {
				let data = "";
				res.on("data", (c) => (data += c));
				res.on("end", () => {
					const sid = (res.headers["set-cookie"] || []).map((c) => c.match(/^sid=([^;]+)/)).filter(Boolean)[0];
					sid ? resolve(sid[1]) : reject(new Error(`login failed for ${usr}: ${res.statusCode} ${data}`));
				});
			}
		);
		req.on("error", reject);
		req.end(body);
	});
}

(async () => {
	const events = {};
	const sids = {};
	let connected = 0;
	for (const usr of users) {
		sids[usr] = await login(usr);
		events[usr] = [];
		const socket = io(`http://127.0.0.1:9000/${site}`, {
			extraHeaders: { Host: `${site}:9000`, Origin: `http://${site}:9000`, Cookie: `sid=${sids[usr]}`, "X-Frappe-Site-Name": site },
			transports: ["websocket"],
			reconnection: false,
		});
		socket.on("connect", () => {
			console.log(`CONNECTED ${usr}`);
			if (++connected === users.length) {
				console.log("READY");
				setTimeout(() => { console.log("RESULT " + JSON.stringify({ events, sids })); process.exit(0); }, Number(seconds) * 1000);
			}
		});
		socket.on("connect_error", (e) => console.log(`CONNECT_ERROR ${usr}: ${e.message}`));
		socket.onAny((ev, msg) => events[usr].push({ ev, msg: JSON.stringify(msg).slice(0, 300) }));
	}
})().catch((e) => { console.log("FATAL " + e.message); process.exit(1); });
