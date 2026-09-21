<template>
  <header class="top-bar">
    <div class="top-bar-content">
      <!-- 左侧：Logo 和标题 (保持不变) -->
      <div class="logo-area" @click="goHome">
        <svg
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M12 2L2 7V17L12 22L22 17V7L12 2Z"
            stroke="#4299e1"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M2 7L12 12L22 7"
            stroke="#4299e1"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M12 22V12"
            stroke="#4299e1"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <span class="app-name">桌面活动管理系统</span>
      </div>

      <!-- 主导航 -->
      <nav class="main-nav">
        <router-link to="/" class="nav-link" :class="{ active: route.path === '/' }">
          <i class="fas fa-chart-line"></i> 仪表盘
        </router-link>
        <router-link
          to="/saves"
          class="nav-link"
          :class="{ active: route.path.startsWith('/saves') }"
        >
          <i class="fas fa-cloud"></i> 云存档
        </router-link>
      </nav>

      <!-- 右侧：功能操作区 (修改部分) -->
      <div class="actions-area">
        
        <!-- 场景1：如果已登录，显示用户名 + 下拉菜单 -->
        <div v-if="authStore.isAuthenticated" class="user-menu-container">
          <div class="user-trigger">
            <span class="username-text">Hi, {{ authStore.username }}</span>
            <i class="fas fa-chevron-down arrow-icon"></i>
          </div>
          
          <!-- 悬停或点击后展开的菜单 -->
          <div class="dropdown-menu">
            <div class="menu-item" @click="router.push('/saves')">
              <i class="fas fa-cloud"></i> 云存档
            </div>
            <div class="menu-item logout-btn" @click="handleLogout">
              <i class="fas fa-sign-out-alt"></i> 退出登录
            </div>
          </div>
        </div>

        <!-- 场景2：如果未登录，显示登录按钮 -->
        <div v-else class="guest-actions">
           <!-- 如果当前已经是登录页，按钮可以置灰或者隐藏，这里做成高亮跳转 -->
           <button class="login-btn" @click="router.push('/login')">
             立即登录
           </button>
        </div>

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

// 点击 Logo 回首页
const goHome = () => {
  router.push('/')
}

// 退出登录逻辑
const handleLogout = () => {
  // 1. 调用 Pinia 的 logout 清除状态
  authStore.logout()
  // 2. 强制跳转回登录页
  router.push('/login')
}
</script>

<style scoped>
/* 保持原有的 TopBar 基础样式 */
.top-bar {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 64px;
  z-index: 1000;
  background-color: rgba(26, 32, 44, 0.8); /*稍微加深一点背景，提升菜单对比度*/
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.top-bar-content {
  max-width: 1600px;
  height: 100%;
  margin: 0 auto;
  padding: 0 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
}

.app-name {
  font-size: 1.15rem;
  font-weight: 600;
  color: #f7fafc;
}

/* --- 主导航 --- */
.main-nav {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.nav-link {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  color: #94a3b8;
  font-size: 0.9rem;
  font-weight: 500;
  text-decoration: none;
  transition:
    color 0.2s,
    background-color 0.2s;
}
.nav-link i {
  font-size: 0.85rem;
}
.nav-link:hover {
  color: #e2e8f0;
  background-color: rgba(255, 255, 255, 0.06);
}
.nav-link.active {
  color: #fff;
  background-color: rgba(66, 153, 225, 0.18);
}

/* --- 新增/修改的样式 --- */

.actions-area {
  display: flex;
  align-items: center;
}

/* 1. 未登录状态的按钮 */
.login-btn {
  background-color: #4299e1;
  color: white;
  border: none;
  padding: 0.5rem 1.5rem;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s;
}
.login-btn:hover {
  background-color: #3182ce;
}

/* 2. 已登录状态的下拉菜单容器 */
.user-menu-container {
  position: relative; /* 关键：为了下拉菜单的绝对定位 */
  height: 64px; /* 撑满高度，方便鼠标移动 */
  display: flex;
  align-items: center;
  cursor: pointer;
}

/* 触发区：用户名 + 箭头 */
.user-trigger {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  color: #e2e8f0;
  transition: color 0.2s;
}

.user-trigger:hover {
  color: #fff;
}

.arrow-icon {
  font-size: 0.8rem;
  transition: transform 0.3s;
}

/* 下拉菜单本体 */
.dropdown-menu {
  position: absolute;
  top: 60px; /* 在 Header 下方 */
  right: 0;
  width: 160px;
  background-color: #2d3748; /* 深色背景 */
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  
  /* 默认隐藏 */
  opacity: 0;
  visibility: hidden;
  transform: translateY(-10px);
  transition: all 0.2s ease-in-out;
  overflow: hidden;
}

/* 交互逻辑：鼠标悬停在容器上时，显示菜单 */
.user-menu-container:hover .dropdown-menu {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

/* 鼠标悬停时箭头旋转 */
.user-menu-container:hover .arrow-icon {
  transform: rotate(180deg);
}

/* 菜单项 */
.menu-item {
  padding: 0.75rem 1rem;
  color: #e2e8f0;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: background-color 0.2s;
}

/* 退出登录按钮特有样式 */
.logout-btn {
  color: #fc8181; /* 红色文字示警 */
}

.logout-btn:hover {
  background-color: rgba(255, 255, 255, 0.05);
  cursor: pointer;
}
</style>