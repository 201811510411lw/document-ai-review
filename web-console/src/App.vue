<template>
  <div class="app-container">
    <router-view />
    <van-tabbar route fixed placeholder>
      <van-tabbar-item to="/home" icon="home-o">
        首页
      </van-tabbar-item>
      <van-tabbar-item to="/profile" icon="contact">
        我的
      </van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const activeTab = window.location.hash ? undefined : 0
</script>

<style>
:root {
  --van-primary-color: #1989fa;
}
body {
  margin: 0;
  background: #f5f6f8;
}
.app-container {
  min-height: 100vh;
  padding-bottom: 50px;
}
</style>
