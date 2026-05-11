<template>
  <div class="login-bg">
    <div class="login-box">
      <h1>🎯 人才数据库</h1>
      <p class="sub">AI 驱动的简历/论文解析系统</p>
      <el-input v-model="username" placeholder="用户名" size="large" style="margin-bottom:12px" />
      <el-input v-model="password" placeholder="密码" type="password" size="large" style="margin-bottom:16px" @keyup.enter="doLogin" />
      <el-button type="primary" size="large" style="width:100%" @click="doLogin" :loading="loading">登录</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)

const doLogin = async () => {
  if (!username.value || !password.value) return
  loading.value = true
  try {
    const resp = await api.login({ username: username.value, password: password.value })
    if (resp.token) {
      localStorage.setItem('token', resp.token)
      localStorage.setItem('username', resp.username)
      localStorage.setItem('role', resp.role)
      router.push('/')
    } else {
      ElMessage.error(resp.error || '登录失败')
    }
  } catch (e) {
    ElMessage.error('登录失败')
  }
  loading.value = false
}
</script>

<style scoped>
.login-bg { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #667eea, #764ba2); }
.login-box { background: #fff; border-radius: 16px; padding: 48px 40px; width: 380px; box-shadow: 0 20px 60px rgba(0,0,0,.15); text-align: center; }
.login-box h1 { font-size: 24px; margin-bottom: 4px; }
.sub { color: #999; font-size: 13px; margin-bottom: 28px; }
</style>
