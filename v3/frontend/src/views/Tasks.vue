<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2 style="margin:0;font-size:20px">⚙️ 任务队列</h2>
      <el-button type="primary" @click="processPending">处理所有待处理</el-button>
    </div>

    <el-table :data="tasks" v-loading="loading" stripe>
      <el-table-column label="文件" min-width="250">
        <template #default="{ row }">
          {{ row.file_path?.split('/').pop() || row.file_path }}
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-tag :type="row.task_type === 'paper' ? 'warning' : 'primary'" size="small">
            {{ row.task_type === 'paper' ? '论文' : '简历' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusText(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="错误" min-width="200">
        <template #default="{ row }">
          <span v-if="row.error_message" style="color:#e74c3c;font-size:12px">{{ row.error_message }}</span>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ row.created_at }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-popconfirm title="确定删除此任务及关联数据？" @confirm="del(row.id)">
            <template #reference>
              <el-button type="danger" text size="small">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'
import { ElMessage } from 'element-plus'

const tasks = ref([])
const loading = ref(false)

const statusType = (s) => ({ pending: 'info', processing: 'warning', done: 'success', failed: 'danger' }[s] || 'info')
const statusText = (s) => ({ pending: '等待', processing: '处理中', done: '完成', failed: '失败' }[s] || s)

const loadData = async () => {
  loading.value = true
  const resp = await api.listTasks()
  tasks.value = resp?.data || []
  loading.value = false
}

const processPending = async () => {
  const resp = await api.processPending()
  if (resp?.processing > 0) {
    ElMessage.success(`开始处理 ${resp.processing} 个任务`)
  } else {
    ElMessage.info('没有待处理的任务')
  }
  loadData()
}

const del = async (id) => {
  await api.deleteTask(id)
  loadData()
}

onMounted(loadData)
</script>
