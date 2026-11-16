<template>
  <div
    v-if="offline"
    role="alert"
    class="fixed inset-x-0 top-0 z-[100] bg-red-600 px-4 py-3 text-center text-sm font-semibold text-white shadow-lg"
  >
    {{ $t("connection.lost") }}
  </div>

  <Header />

  <div class="bg-slate-300 min-h-screen">
    <router-view />
  </div>
</template>

<script>
import Header from "./components/Header.vue";
import { createConnectionMonitor, startConnectionMonitor } from "./lib/connection.js";
import { createWakeLock } from "./lib/wake-lock.js";

// Is the server answering? A small request that needs no login; five seconds is the longest a look may take.
async function serverAnswers() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch("/api/method/ping", { cache: "no-store", signal: controller.signal });
    return response.ok;
  } catch (error) {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export default {
  name: "App",

  components: {
    Header,
  },

  data() {
    return { offline: false };
  },

  mounted() {
    // the kitchen tablet must not go dark, and a dead connection must not look like a quiet kitchen
    this.wakeLock = createWakeLock(navigator, document);
    this.wakeLock.start();
    const monitor = createConnectionMonitor({ check: serverAnswers, onChange: (online) => (this.offline = !online) });
    this.stopMonitor = startConnectionMonitor(monitor, window);
  },

  beforeUnmount() {
    if (this.stopMonitor) this.stopMonitor();
    if (this.wakeLock) this.wakeLock.stop();
  },
};
</script>
