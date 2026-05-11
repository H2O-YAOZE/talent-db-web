<template>
  <router-view v-if="!token" />
  <el-container v-else style="height:100vh">
    <el-aside width="200px" style="background:#1a1a2e;color:#fff">
      <div style="padding:20px 16px;font-size:18px;font-weight:700;border-bottom:1px solid rgba(255,255,255,.1)">
        🎯 人才数据库
      </div>
      <el-menu
        :default-active="route.path"
        background-color="#1a1a2e"
        text-color="#a0aec0"
        active-text-color="#fff"
        @select="handleMenuSelect"
      >
        <el-menu-item index="/">
          <el-icon><User /></el-icon><span>全部简历</span>
        </el-menu-item>
        <el-menu-item index="/papers">
          <el-icon><Document /></el-icon><span>论文库</span>
        </el-menu-item>
        <el-menu-item index="/upload">
          <el-icon><Upload /></el-icon><span>上传文件</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><Clock /></el-icon><span>任务队列</span>
        </el-menu-item>
      </el-menu>
      <div style="position:absolute;bottom:0;width:200px;padding:16px;border-top:1px solid rgba(255,255,255,.1);font-size:12px;color:#a0aec0">
        👤 {{ username }}
        <el-button text size="small" style="color:#e74c3c;margin-left:8px" @click="logout">退出</el-button>
      </div>
    </el-aside>
    <el-main style="background:#f5f7fa;padding:24px;overflow-y:auto">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const token = ref(localStorage.getItem('token') || '')
const username = ref(localStorage.getItem('username') || '')

const handleMenuSelect = (index) => router.push(index)

const logout = () => {
  localStorage.clear()
  token.value = ''
  router.push('/login')
}

watch(() => route.path, () => {
  token.value = localStorage.getItem('token') || ''
})
</script>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif; }
.el-menu { border-right: none !important; }
.el-menu-item { font-size: 14px; }
.el-menu-item.is-active { background: rgba(255,255,255,0.08) !important; border-radius: 8px; margin: 2px 8px; }
</style>
