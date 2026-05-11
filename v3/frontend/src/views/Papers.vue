<template>
  <div>
    <h2 style="margin:0 0 16px;font-size:20px">📄 论文库</h2>

    <div style="margin-bottom:16px;display:flex;gap:12px;flex-wrap:wrap">
      <el-input v-model="keyword" placeholder="搜索标题/团队/方向..." style="width:280px" clearable @clear="search" @keyup.enter="search">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-select v-model="team" placeholder="团队" clearable filterable style="width:200px" @change="search">
        <el-option v-for="t in teams" :key="t.team" :label="`${t.team} (${t.count})`" :value="t.team" />
      </el-select>
      <el-select v-model="school" placeholder="学校" clearable filterable style="width:200px" @change="search">
        <el-option v-for="s in schools" :key="s.school" :label="`${s.school} (${s.count})`" :value="s.school" />
      </el-select>
      <span style="color:#999;font-size:13px;line-height:32px">共 {{ total }} 篇</span>
    </div>

    <div v-loading="loading">
      <el-card v-for="p in list" :key="p.id" style="margin-bottom:12px" shadow="hover">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <h3 style="margin:0 0 4px;font-size:15px">{{ p.title }}</h3>
            <div style="color:#666;font-size:13px">
              <span v-if="p.team">团队：{{ p.team }}</span>
              <span v-if="p.direction" style="margin-left:12px">方向：{{ p.direction }}</span>
              <span style="margin-left:12px">{{ p.upload_time }}</span>
            </div>
            <div v-if="p.summary" style="color:#999;font-size:12px;margin-top:4px">{{ p.summary }}</div>
          </div>
          <el-button text size="small" type="primary" @click="showAuthors = showAuthors === p.id ? null : p.id">
            {{ p.authors.length }} 位作者 {{ showAuthors === p.id ? '▲' : '▼' }}
          </el-button>
        </div>

        <!-- Authors list -->
        <div v-if="showAuthors === p.id" style="margin-top:12px;padding-top:12px;border-top:1px solid #ebeef5">
          <el-table :data="p.authors" size="small" stripe>
            <el-table-column prop="name" label="姓名" width="100" />
            <el-table-column prop="email" label="邮箱" width="200" />
            <el-table-column prop="institution" label="机构" width="200" />
            <el-table-column prop="research_field" label="方向" width="200" />
            <el-table-column label="GitHub" width="180">
              <template #default="{ row: a }">
                <a v-if="a.github_url" :href="a.github_url" target="_blank" style="color:#667eea">@{{ a.github_username }}</a>
                <span v-else style="color:#ccc">未匹配</span>
              </template>
            </el-table-column>
            <el-table-column label="匹配度" width="90">
              <template #default="{ row: a }">
                <el-tag :type="a.match_confidence === 'high' ? 'success' : a.match_confidence === 'medium' ? 'warning' : 'info'" size="small">
                  {{ a.match_confidence }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-card>
    </div>

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
const team = ref('')
const school = ref('')
const teams = ref([])
const schools = ref([])
const loading = ref(false)
const showAuthors = ref(null)

const loadData = async () => {
  loading.value = true
  const params = { page: page.value, size: 50 }
  if (keyword.value) params.keyword = keyword.value
  if (team.value) params.team = team.value
  if (school.value) params.school = school.value
  const resp = await api.listPapers(params)
  if (resp?.data) {
    list.value = resp.data
    total.value = resp.total
  }
  loading.value = false
}

const search = () => { page.value = 1; loadData() }

onMounted(async () => {
  const [t, s] = await Promise.all([api.getTeams(), api.getSchools()])
  teams.value = t?.data || []
  schools.value = s?.data || []
  loadData()
})
</script>
