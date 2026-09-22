<template>
  <header class="top-bar">
    <div class="top-bar-inner">
      <!-- 左：Logo + 标题 -->
      <div class="logo-area" @click="goHome">
        <svg
          width="26"
          height="26"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M12 2L2 7V17L12 22L22 17V7L12 2Z"
            stroke="#4f9cf9"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M2 7L12 12L22 7"
            stroke="#4f9cf9"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M12 22V12"
            stroke="#4f9cf9"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <span class="app-name">桌面活动管理系统</span>
      </div>

      <!-- 中：主导航 -->
      <nav class="main-nav">
        <router-link to="/" class="nav-link" :class="{ active: route.path === '/' }">
          <i class="fas fa-chart-line"></i><span>概览</span>
        </router-link>
        <router-link
          to="/analysis"
          class="nav-link"
          :class="{ active: route.path.startsWith('/analysis') }"
        >
          <i class="fas fa-magnifying-glass-chart"></i><span>分析</span>
        </router-link>
        <router-link
          to="/saves"
          class="nav-link"
          :class="{ active: route.path.startsWith('/saves') }"
        >
          <i class="fas fa-cloud"></i><span>云存档</span>
        </router-link>
        <router-link
          to="/settings"
          class="nav-link"
          :class="{ active: route.path.startsWith('/settings') }"
        >
          <i class="fas fa-gear"></i><span>设置</span>
        </router-link>
      </nav>

      <!-- 右：账号 -->
      <div class="actions-area">
        <div v-if="authStore.isAuthenticated" class="user-menu">
          <button class="user-trigger">
            <span class="username-text">{{ authStore.username }}</span>
            <i class="fas fa-chevron-down arrow-icon"></i>
          </button>
          <div class="dropdown-menu">
            <button class="menu-item" @click="router.push('/saves')">
              <i class="fas fa-cloud"></i> 云存档
            </button>
            <button class="menu-item" @click="router.push('/settings')">
              <i class="fas fa-gear"></i> 设置
            </button>
            <div class="menu-sep"></div>
            <button class="menu-item danger" @click="handleLogout">
              <i class="fas fa-right-from-bracket"></i> 退出登录
            </button>
          </div>
        </div>

        <button v-else class="btn btn-primary" @click="router.push('/login')">立即登录</button>
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const goHome = () => {
  router.push('/')
}

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.top-bar {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: var(--topbar-h);
  z-index: 1000;
  background-color: rgba(11, 18, 32, 0.72);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border-bottom: 1px solid var(--border);
}

.top-bar-inner {
  max-width: var(--container);
  height: 100%;
  margin: 0 auto;
  padding: 0 var(--gutter);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-4);
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  cursor: pointer;
  min-width: 0;
}
.app-name {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-strong);
  white-space: nowrap;
}

/* 主导航 */
.main-nav {
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}
.nav-link {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 0.95rem;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  font-size: 0.9rem;
  font-weight: 500;
  text-decoration: none;
  transition:
    color 0.18s,
    background-color 0.18s;
}
.nav-link i {
  font-size: 0.85rem;
}
.nav-link:hover {
  color: var(--text);
  background-color: var(--surface-hover);
}
.nav-link.active {
  color: #fff;
  background-color: var(--accent-soft);
}

/* 账号区 */
.actions-area {
  display: flex;
  align-items: center;
}

.user-menu {
  position: relative;
  height: var(--topbar-h);
  display: flex;
  align-items: center;
}
.user-trigger {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.9rem;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text);
  font-size: 0.9rem;
  cursor: pointer;
  transition:
    background-color 0.18s,
    border-color 0.18s;
}
.user-trigger:hover {
  background: var(--surface-hover);
  border-color: var(--border);
}
.username-text {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.arrow-icon {
  font-size: 0.75rem;
  color: var(--text-faint);
  transition: transform 0.25s;
}
.user-menu:hover .arrow-icon {
  transform: rotate(180deg);
}

.dropdown-menu {
  position: absolute;
  top: calc(var(--topbar-h) - 8px);
  right: 0;
  min-width: 170px;
  padding: 0.35rem;
  background: var(--surface-strong);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  opacity: 0;
  visibility: hidden;
  transform: translateY(-8px);
  transition:
    opacity 0.18s ease,
    transform 0.18s ease,
    visibility 0.18s;
}
.user-menu:hover .dropdown-menu,
.user-menu:focus-within .dropdown-menu {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  padding: 0.6rem 0.7rem;
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text);
  font-size: 0.88rem;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s;
}
.menu-item:hover {
  background: var(--surface-hover);
}
.menu-item.danger {
  color: #fca5b3;
}
.menu-sep {
  height: 1px;
  margin: 0.3rem 0.2rem;
  background: var(--border);
}

@media (max-width: 860px) {
  .nav-link span {
    display: none;
  }
  .nav-link {
    padding: 0.5rem 0.7rem;
  }
}
@media (max-width: 640px) {
  .app-name {
    display: none;
  }
}
</style>
