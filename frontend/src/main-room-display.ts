import { createApp, h } from 'vue'
import { createRouter, createWebHistory, RouterView } from 'vue-router'
import RoomDisplay from './pages/RoomDisplay.vue'
import RoomControl from './pages/RoomControl.vue'
import V6Control from './pages/V6Control.vue'
import './style.css'

// A separate entry bundle: no platform layout or administration routes.
const router = createRouter({ history: createWebHistory(), routes: [
  { path: '/control', component: V6Control },
  { path: '/control/legacy', component: RoomControl },
  { path: '/:pathMatch(.*)*', component: RoomDisplay },
] })
router.beforeEach(to => {
  if (to.path === '/' && !('version' in to.query) && !('managed' in to.query)) {
    return {path:'/control',query:to.query,replace:true}
  }
  return to.query.preview ? { path: to.path } : true
})
const app = createApp({ render: () => h(RouterView) }).use(router)
router.isReady().then(() => app.mount('#app'))
