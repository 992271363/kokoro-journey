<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import TopBar from '@/components/TopBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useBackgroundStore } from '@/stores/background'

const route = useRoute()
const authStore = useAuthStore()
const backgroundStore = useBackgroundStore()

const syncBackground = () => {
  if (authStore.isAuthenticated) {
    void backgroundStore.load()
  } else {
    backgroundStore.reset()
  }
}

onMounted(syncBackground)
watch(() => authStore.isAuthenticated, syncBackground)
</script>

<template>
  <div class="app-bg" aria-hidden="true"></div>
  <div class="app-scrim" aria-hidden="true"></div>
  <TopBar v-if="!route.meta.hideTopBar" />
  <main class="app-main" :class="{ 'with-topbar': !route.meta.hideTopBar }">
    <RouterView />
  </main>
</template>

<style>
.app-main {
  position: relative;
  z-index: 2;
  width: 100%;
  min-height: 100vh;
}
.app-main.with-topbar {
  padding-top: var(--topbar-h);
}
</style>
