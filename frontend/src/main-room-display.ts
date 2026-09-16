import { createApp, h } from 'vue'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import RoomDisplay from './pages/RoomDisplay.vue'
import RoomControl from './pages/RoomControl.vue'
import './style.css'

// A separate entry bundle: no platform layout or administration routes.
const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/control', component: RoomControl },
  { path: '/:pathMatch(.*)*', component: RoomDisplay },
] })
router.beforeEach(to => to.query.preview ? { path: to.path } : true)
const app = createApp({ render: () => h(RouterView) }).use(router)
router.isReady().then(() => app.mount('#app'))
