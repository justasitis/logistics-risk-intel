import './styles/logistics-light-theme.css'
import './styles/maplibre-light-overrides.css'

document.documentElement.dataset.theme = 'logistics-light'

import './assets/main.css'

import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
