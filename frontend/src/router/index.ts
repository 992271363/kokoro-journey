import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'main',
      component: () => import('@/views/MainView.vue'),
    },
    {
      path: '/saves',
      name: 'saves',
      component: () => import('@/views/SavesView.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { hideTopBar: true }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { hideTopBar: true }
    },
        {
      // :pathMatch(.*)* 是 Vue Router 4 的固定写法，匹配所有剩余路径
      path: '/:pathMatch(.*)*', 
      name: 'NotFound',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { hideTopBar: true }
    },
  ],
})

// 需要登录的页面统一守卫（登录/注册/404 标记 hideTopBar，放行）
router.beforeEach((to) => {
  if (to.meta.hideTopBar) return true
  const authStore = useAuthStore()
  if (!authStore.isAuthenticated) {
    return { name: 'login' }
  }
  return true
})

export default router
