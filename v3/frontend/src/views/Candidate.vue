<template>
  <div v-loading="loading">
    <el-button text @click="$router.back()" style="margin-bottom:16px">← 返回</el-button>
    <el-card v-if="candidate">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:18px;font-weight:600">👤 {{ candidate.name }}</span>
          <div style="display:flex;gap:8px">
            <el-button v-if="candidate.task_id" size="small" @click="download">📥 下载源文件</el-button>
            <el-popconfirm title="确定删除？" @confirm="del">
              <template #reference>
                <el-button type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </template>

      <el-descriptions :column="2" border>
        <el-descriptions-item label="邮箱">{{ candidate.email || '-' }}</el-descriptions-item>
        <el-descriptions-item label="电话">{{ candidate.phone || '-' }}</el-descriptions-item>
        <el-descriptions-item label="学历">{{ candidate.degree || '-' }}</el-descriptions-item>
        <el-descriptions-item label="学校">{{ candidate.institution || '-' }}</el-descriptions-item>
        <el-descriptions-item label="研究领域">{{ candidate.research_field || '-' }}</el-descriptions-item>
        <el-descriptions-item label="来源">{{ candidate.source === 'resume' ? '简历' : '论文' }}</el-descriptions-item>
        <el-descriptions-item label="GitHub">
          <a v-if="candidate.github_url" :href="candidate.github_url" target="_blank" style="color:#667eea">
            @{{ candidate.github_username }}
          </a>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item label="入库时间">{{ candidate.created_at }}</el-descriptions-item>
      </el-descriptions>

      <!-- Education -->
      <h3 style="margin:20px 0 8px">🎓 教育经历</h3>
      <el-table :data="candidate.education || []" size="small" stripe>
        <el-table-column prop="school" label="学校" />
        <el-table-column prop="degree" label="学位" />
        <el-table-column prop="major" label="专业" />
        <el-table-column prop="year" label="年份" />
      </el-table>

      <!-- Work -->
      <h3 style="margin:20px 0 8px">💼 工作经历</h3>
      <el-table :data="candidate.work_experience || []" size="small" stripe>
        <el-table-column prop="company" label="公司" />
        <el-table-column prop="role" label="职位" />
        <el-table-column prop="duration" label="时长" />
      </el-table>

      <!-- Skills -->
      <h3 style="margin:20px 0 8px">🛠 技能</h3>
      <div>
        <el-tag v-for="s in (candidate.skills || [])" :key="s" style="margin:2px">{{ s }}</el-tag>
        <span v-if="!(candidate.skills || []).length" style="color:#999">无</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const router = useRouter()
const candidate = ref(null)
const loading = ref(false)

const loadData = async () => {
  loading.value = true
  try {
    const resp = await api.getCandidate(route.params.id)
    candidate.value = resp?.error ? null : (resp.name ? resp : null)
  } catch (e) { console.error(e) }
  loading.value = false
}

const download = () => {
  if (!candidate.value?.id) return
  const token = localStorage.getItem('token') || ''
  const url = `/api/candidates/${candidate.value.id}/download?token=${token}`
  window.open(url, '_blank')
}

const del = async () => {
  await api.deleteCandidate(route.params.id)
  router.push('/')
}

onMounted(loadData)
</script>
