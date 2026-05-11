import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
  { path: '/', name: 'Home', component: () => import('../views/Home.vue') },
  { path: '/papers', name: 'Papers', component: () => import('../views/Papers.vue') },
  { path: '/upload', name: 'Upload', component: () => import('../views/Upload.vue') },
  { path: '/tasks', name: 'Tasks', component: () => import('../views/Tasks.vue') },
  { path: '/candidate/:id', name: 'Candidate', component: () => import('../views/Candidate.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/')
  } else {
    next()
  }
})

export default router
