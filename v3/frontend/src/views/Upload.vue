<template>
  <div>
    <h2 style="margin:0 0 16px;font-size:20px">📤 上传文件</h2>

    <el-upload
      v-model:file-list="fileList"
      drag
      multiple
      :auto-upload="false"
      :on-change="onChange"
      accept=".pdf"
      style="margin-bottom:20px"
    >
      <el-icon style="font-size:48px;color:#667eea"><UploadFilled /></el-icon>
      <div style="margin-top:8px;font-size:15px;color:#333">拖拽 PDF 到此处，或点击选择</div>
      <div style="margin-top:4px;font-size:12px;color:#999">支持简历和论文，自动识别类型</div>
    </el-upload>

    <div v-if="fileList.length" style="margin-bottom:16px">
      <div style="font-size:14px;font-weight:600;margin-bottom:8px">待上传文件（{{ fileList.length }} 个）</div>
      <el-button type="primary" @click="doUpload" :loading="uploading">开始上传并自动处理</el-button>
      <el-button @click="fileList = []">清空</el-button>
    </div>

    <el-alert v-if="results.length" title="上传结果" type="success" style="margin-top:16px">
      <div v-for="r in results" :key="r.file">
        {{ r.file }} → <el-tag :type="r.type === 'paper' ? 'warning' : 'primary'" size="small">{{ r.type || '排队中' }}</el-tag>
        {{ r.status === 'queued' ? '已加入队列' : r.status }}
      </div>
    </el-alert>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'

const fileList = ref([])
const uploading = ref(false)
const results = ref([])

const onChange = () => {}  // just for attachment tracking

const doUpload = async () => {
  if (!fileList.value.length) return
  uploading.value = true
  const formData = new FormData()
  fileList.value.forEach((f) => {
    formData.append('files', f.raw)
  })
  const resp = await api.upload(formData)
  if (resp?.results) {
    results.value = resp.results

    // Auto-process
    const processResp = await api.processPending()
    if (processResp?.processing > 0) {
      ElMessage.success(`已上传并开始处理 ${resp.results.length} 个文件`)
    }

    // Poll for completion
    pollTasks(0)
  }
  fileList.value = []
  uploading.value = false
}

const pollTasks = (attempt) => {
  if (attempt > 30) return
  setTimeout(async () => {
    const resp = await api.listTasks()
    if (resp?.data) {
      const pending = resp.data.filter(t => t.status === 'pending' || t.status === 'processing')
      if (!pending.length) {
        ElMessage.success('全部处理完成！')
        return
      }
    }
    pollTasks(attempt + 1)
  }, 3000)
}
</script>
