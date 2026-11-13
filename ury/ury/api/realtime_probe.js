// Test helper (ury/ury/api/test_realtime_reach.py): connects to the real Socket.IO server as the given users and
// prints every event they receive.  usage: node realtime_probe.js <site> <password> <seconds after ready> user...
// prints: CONNECTED <user> | CONNECT_ERROR <user>: <msg> | READY | RESULT {"events": {user: [{ev, msg}]}, "sids": {user: sid}}
const http = require("http");
const { io } = require("socket.io-client");

const [site, password, seconds, ...users] = process.argv.slice(2);
// PROBE_FETCH_PREFIX=kot_update_ : when such an event arrives, read the kitchen screen's list (kot_list) as that user at
// once, like the screen does, and note whether the ticket of the event is in it (`listed`).
const fetchPrefix = process.env.PROBE_FETCH_PREFIX || "";

function listKots(sid) {
	return new Promise((resolve) => {
		const req = http.request(
			{ host: "127.0.0.1", port: 8000, path: "/api/method/ury.ury.api.ury_kot_display.kot_list", method: "GET",
			  headers: { Host: `${site}:8000`, Cookie: `sid=${sid}` } },
			(res) => {
				let data = "";
				res.on("data", (c) => (data += c));
				res.on("end", () => {
					try { resolve(JSON.parse(data).message.KOT.map((k) => k.name)); } catch (e) { resolve(null); }
				});
			}
		);
		req.on("error", () => resolve(null));
		req.end();
	});
}

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
		socket.onAny(async (ev, msg) => {
			const entry = { ev, msg: JSON.stringify(msg).slice(0, 300) };
			events[usr].push(entry);
			if (fetchPrefix && ev.startsWith(fetchPrefix) && msg && msg.kot) {
				entry.kot = msg.kot.name;
				const names = await listKots(sids[usr]);
				entry.listed = names ? names.includes(msg.kot.name) : null;
			}
		});
	}
})().catch((e) => { console.log("FATAL " + e.message); process.exit(1); });
