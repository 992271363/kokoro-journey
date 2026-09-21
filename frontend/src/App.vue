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
  <TopBar v-if="!route.meta.hideTopBar" />
  <main class="main-content">
    <RouterView />
  </main>
</template>
<style>
.main-content {
  padding-top: 64px;
  width: 100%;
}
</style>
