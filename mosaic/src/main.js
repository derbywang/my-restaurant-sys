import './index.css';
import { createApp, reactive } from "vue";
import App from "./App.vue";

import router from './router';
import { initLanguage, installLanguage } from './lib/language';

const app = createApp(App);

// Plugins
app.use(router);
installLanguage(app);

// Global Properties,
// components can inject this

// Configure route gaurds
router.beforeEach(async (to, from, next) => {
	next();
});

// the words wait for the language of the user, so no screen flashes in the wrong one
initLanguage().finally(() => app.mount("#app"));
