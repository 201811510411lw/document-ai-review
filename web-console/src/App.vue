<template>
  <div v-if="route.meta.noShell" class="app-container bare-container">
    <router-view />
  </div>
  <WorkspaceShell v-else><router-view /></WorkspaceShell>
</template>

<script setup>
import { useRoute } from 'vue-router'
import WorkspaceShell from '@/components/WorkspaceShell.vue'

const route = useRoute()
</script>

<style>
:root {
  --van-primary-color: #3864f4;
  color-scheme: light;
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #f3f6fb;
  color: #182238;
}
.app-container {
  min-height: 100dvh;
}
.workspace-content.top-level-route > [class$="-page"] > .van-nav-bar {
  display: none;
}
</style>
