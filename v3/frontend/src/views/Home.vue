<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <h2 style="margin:0;font-size:20px">📋 全部简历</h2>
      <el-button type="primary" @click="$router.push('/upload')">+ 上传文件</el-button>
    </div>

    <!-- Search -->
    <div style="margin-bottom:16px;display:flex;gap:12px;flex-wrap:wrap">
      <el-input v-model="keyword" placeholder="搜索姓名/邮箱/机构/技能..." style="width:300px" clearable @clear="search" @keyup.enter="search">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="degree" placeholder="学历" clearable style="width:120px" @change="search">
        <el-option v-for="d in degrees" :key="d.degree" :label="`${d.degree} (${d.count})`" :value="d.degree" />
      </el-select>
      <el-select v-model="company" placeholder="公司" clearable filterable style="width:200px" @change="search">
        <el-option v-for="c in companies" :key="c.company" :label="`${c.company} (${c.count})`" :value="c.company" />
      </el-select>
      <el-select v-model="uploader" placeholder="上传人" clearable style="width:140px" @change="search">
        <el-option v-for="u in uploaders" :key="u.uploader" :label="`${u.uploader} (${u.count})`" :value="u.uploader" />
      </el-select>
      <span style="color:#999;font-size:13px;line-height:32px">共 {{ total }} 人</span>
    </div>

    <!-- Table -->
    <el-table :data="list" stripe style="width:100%" @row-click="(row) => $router.push(`/candidate/${row.id}`)" v-loading="loading">
      <el-table-column prop="name" label="姓名" width="100" />
      <el-table-column prop="email" label="邮箱" width="200" />
      <el-table-column prop="phone" label="电话" width="130" />
      <el-table-column label="最近公司" width="200">
        <template #default="{ row }">
          {{ getLatestCompany(row) }}
        </template>
      </el-table-column>
      <el-table-column prop="degree" label="学历" width="80" />
      <el-table-column prop="institution" label="学校" width="150" />
      <el-table-column prop="batch_name" label="批次" width="120" />
      <el-table-column prop="uploaded_by" label="上传人" width="80" />
      <el-table-column label="技能" min-width="200">
        <template #default="{ row }">
          <el-tag v-for="s in (row.skills || []).slice(0,5)" :key="s" size="small" style="margin:1px">{{ s }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ row.created_at }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确定删除？" @confirm="del(row.id)">
            <template #reference>
              <el-button type="danger" text size="small" @click.stop>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <div style="margin-top:16px;text-align:center">
      <el-pagination v-model:current-page="page" :total="total" :page-size="50" layout="prev, pager, next" @current-change="loadData" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const list = ref([])
const total = ref(0)
const page = ref(1)
const keyword = ref('')
const degree = ref('')
const company = ref('')
const companies = ref([])
const degrees = ref([])
const uploaders = ref([])
const loading = ref(false)

const getLatestCompany = (row) => {
  if (!row.work_experience || !row.work_experience.length) return ''
  return row.work_experience[0]?.company || ''
}

const loadData = async () => {
  loading.value = true
  try {
    const params = { page: page.value, size: 50 }
    if (keyword.value) params.keyword = keyword.value
    if (degree.value) params.degree = degree.value
    if (company.value) params.company = company.value
    if (uploader.value) params.uploader = uploader.value
    const resp = await api.listCandidates(params)
    if (resp && resp.data) {
      list.value = resp.data
      total.value = resp.total
    }
  } catch (e) {
    console.error('Load candidates failed:', e)
  }
  loading.value = false
}

const search = () => { page.value = 1; loadData() }

const del = async (id) => {
  await api.deleteCandidate(id)
  loadData()
}

onMounted(async () => {
  const [compRes, degRes, upRes] = await Promise.all([api.getCompanies(), api.getDegrees(), api.getUploaders()])
  companies.value = compRes?.data || []
  degrees.value = degRes?.data || []
  uploaders.value = upRes?.data || []
  loadData()
})
</script>
