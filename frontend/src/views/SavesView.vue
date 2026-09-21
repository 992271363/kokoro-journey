<template>
  <div class="saves-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Cloud Saves</p>
        <h1>云存档浏览</h1>
      </div>
      <button class="refresh-btn" :disabled="loadingGames" @click="loadGames(true)">
        <i class="fas fa-rotate" :class="{ spinning: loadingGames }"></i> 刷新
      </button>
    </header>

    <p v-if="errorMessage" class="error-banner">
      <i class="fas fa-triangle-exclamation"></i> {{ errorMessage }}
    </p>

    <div class="saves-body">
      <!-- 云端游戏列表 -->
      <aside class="panel games-panel">
        <div class="panel-header">
          <h2>云端游戏</h2>
          <span class="panel-badge">{{ games.length }} 个</span>
        </div>
        <div v-if="loadingGames && games.length === 0" class="hint">加载中…</div>
        <div v-else-if="games.length === 0" class="empty-state">
          <i class="fas fa-box-open"></i>
          <p>云端还没有存档</p>
        </div>
        <ul v-else class="game-list">
          <li
            v-for="game in games"
            :key="game.id"
            class="game-item"
            :class="{ active: game.id === selectedGameId }"
            @click="selectGame(game)"
          >
            <div class="game-top">
              <span class="game-name">{{ game.name }}</span>
              <span class="game-dot" :class="{ on: !!game.latestVersion }"></span>
            </div>
            <div class="game-sub">
              <span class="game-ident">{{ game.identifier || '—' }}</span>
              <span class="game-time">{{ formatDateTime(game.latestCreatedAt) || '暂无存档' }}</span>
            </div>
          </li>
        </ul>
      </aside>

      <!-- 存档位 + 文件清单 -->
      <section class="panel slots-panel">
        <div class="panel-header">
          <h2>{{ selectedGame ? selectedGame.name : '存档位' }}</h2>
          <span v-if="selectedGame" class="panel-badge">
            标识符 {{ selectedGame.identifier || '—' }}
          </span>
        </div>

        <div v-if="!selectedGame" class="empty-state">
          <i class="fas fa-hand-point-left"></i>
          <p>请选择左侧的云端游戏</p>
        </div>

        <template v-else>
          <div class="slot-grid">
            <button
              v-for="slot in slots"
              :key="slot.slot"
              class="slot-card"
              :class="{ occupied: !!slot.versionId, active: slot.slot === selectedSlot }"
              :disabled="!slot.versionId"
              @click="selectSlot(slot)"
            >
              <span class="slot-name">{{ slot.label || `存档位 ${slot.slot}` }}</span>
              <span class="slot-sub">
                {{ slot.versionId ? formatDateTime(slot.createdAt) : '空' }}
              </span>
              <span class="slot-sub">
                {{ slot.versionId ? `${formatSize(slot.totalSize)} · ${slot.fileCount ?? 0} 个文件` : '' }}
              </span>
            </button>
          </div>

          <div class="files-section">
            <div class="files-header">
              <h3 v-if="selectedSlotInfo && selectedSlotInfo.versionId">
                文件清单
                <span class="files-count">{{ files.length }} 个</span>
              </h3>
              <h3 v-else>文件清单</h3>
              <button
                class="zip-btn"
                :disabled="!selectedSlotInfo || !selectedSlotInfo.versionId || filesLoading"
                @click="onDownloadZip"
              >
                <i class="fas fa-file-zipper"></i> 打包下载
              </button>
            </div>

            <div v-if="!selectedSlotInfo || !selectedSlotInfo.versionId" class="hint">
              选择一个已占用的存档位以查看文件
            </div>
            <div v-else-if="filesLoading" class="hint">加载中…</div>
            <div v-else-if="files.length === 0" class="hint">该存档位没有文件</div>
            <table v-else class="files-table">
              <thead>
                <tr>
                  <th>路径</th>
                  <th class="col-size">大小</th>
                  <th class="col-time">修改时间</th>
                  <th class="col-action"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="file in files" :key="file.path">
                  <td class="cell-path" :title="file.path">{{ file.path }}</td>
                  <td class="col-size">{{ formatSize(file.size) }}</td>
                  <td class="col-time">{{ formatMtimeNs(file.mtimeNs) }}</td>
                  <td class="col-action">
                    <button class="dl-btn" title="下载该文件" @click="onDownloadFile(file)">
                      <i class="fas fa-download"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  downloadFile,
  downloadSlotZip,
  listFiles,
  listGames,
  listSlots,
  saveBlob,
  type SaveFile,
  type SaveGame,
  type SaveSlot,
} from '@/api/saves'

const games = ref<SaveGame[]>([])
const slots = ref<SaveSlot[]>([])
const files = ref<SaveFile[]>([])
const selectedGameId = ref<number | null>(null)
const selectedSlot = ref<number | null>(null)

const loadingGames = ref(false)
const filesLoading = ref(false)
const errorMessage = ref('')

const selectedGame = computed(
  () => games.value.find((g) => g.id === selectedGameId.value) ?? null,
)
const selectedSlotInfo = computed(
  () => slots.value.find((s) => s.slot === selectedSlot.value) ?? null,
)

const formatSize = (bytes?: number | null): string => {
  const n = Number(bytes ?? 0)
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB']
  let value = n / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i += 1
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[i]}`
}

const formatDateTime = (iso?: string | null): string => {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const formatMtimeNs = (ns?: number | null): string => {
  if (!ns) return '—'
  const d = new Date(Number(ns) / 1e6)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

async function loadGames(keepSelection = false) {
  loadingGames.value = true
  errorMessage.value = ''
  try {
    const list = await listGames()
    games.value = Array.isArray(list) ? list : []
    const stillThere = games.value.some((g) => g.id === selectedGameId.value)
    if (!keepSelection || !stillThere || selectedGameId.value === null) {
      const first = games.value[0]
      selectedGameId.value = first ? first.id : null
      slots.value = []
      files.value = []
      selectedSlot.value = null
      if (first) await loadSlots(first.id)
    } else {
      // 刷新：保留当前选择并同步槽位/文件
      await loadSlots(selectedGameId.value)
      const info = selectedSlotInfo.value
      if (info && info.versionId) {
        await loadFiles()
      } else {
        selectedSlot.value = null
        files.value = []
      }
    }
  } catch (e) {
    errorMessage.value = extractError(e, '无法加载云端游戏列表')
  } finally {
    loadingGames.value = false
  }
}

async function loadSlots(gameId: number) {
  try {
    const list = await listSlots(gameId)
    slots.value = Array.isArray(list) ? list : []
  } catch (e) {
    slots.value = []
    errorMessage.value = extractError(e, '无法加载存档位')
  }
}

async function selectGame(game: SaveGame) {
  if (game.id === selectedGameId.value) return
  selectedGameId.value = game.id
  selectedSlot.value = null
  slots.value = []
  files.value = []
  await loadSlots(game.id)
}

async function selectSlot(slot: SaveSlot) {
  if (!slot.versionId) return
  if (slot.slot === selectedSlot.value) return
  selectedSlot.value = slot.slot
  files.value = []
  await loadFiles()
}

async function loadFiles() {
  const game = selectedGame.value
  const info = selectedSlotInfo.value
  if (!game || !info || !info.versionId) return
  filesLoading.value = true
  errorMessage.value = ''
  try {
    const list = await listFiles(game.id, info.versionId)
    files.value = Array.isArray(list) ? list : []
  } catch (e) {
    files.value = []
    errorMessage.value = extractError(e, '无法加载文件清单')
  } finally {
    filesLoading.value = false
  }
}

async function onDownloadFile(file: SaveFile) {
  const game = selectedGame.value
  const info = selectedSlotInfo.value
  if (!game || !info || !info.versionId) return
  try {
    const { blob, filename } = await downloadFile(game.id, info.versionId, file.path)
    saveBlob(blob, filename)
  } catch (e) {
    errorMessage.value = extractError(e, '文件下载失败')
  }
}

async function onDownloadZip() {
  const game = selectedGame.value
  const info = selectedSlotInfo.value
  if (!game || !info || !info.versionId) return
  const key = game.identifier || game.name
  try {
    const { blob, filename } = await downloadSlotZip(
      game.id,
      info.versionId,
      `${key}-存档位${info.slot}.zip`,
    )
    saveBlob(blob, filename)
  } catch (e) {
    errorMessage.value = extractError(e, '打包下载失败')
  }
}

function extractError(e: unknown, fallback: string): string {
  const err = e as { response?: { status?: number; data?: unknown }; message?: string }
  if (err?.response?.status === 409) return '云同步已由其他设备接管，请稍后重试'
  if (err?.response?.status === 404) return '资源不存在或已被删除'
  return err?.message ? `${fallback}：${err.message}` : fallback
}

onMounted(() => loadGames())
</script>

<style scoped>
.saves-page {
  font-family: 'DM Sans', sans-serif;
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem 2.5rem 3rem;
  color: #e2e8f0;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 1.75rem;
}
.page-header h1 {
  margin: 0;
  font-size: 2rem;
  font-weight: 600;
  color: #f1f5f9;
  letter-spacing: -0.02em;
}
.eyebrow {
  margin: 0 0 0.25rem;
  font-size: 0.9rem;
  color: #64748b;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.refresh-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #cbd5e1;
  border-radius: 8px;
  padding: 0.5rem 1rem;
  cursor: pointer;
  font-size: 0.85rem;
  transition: background 0.15s, border-color 0.15s;
}
.refresh-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}
.refresh-btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.spinning {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.error-banner {
  margin: 0 0 1rem;
  padding: 0.65rem 1rem;
  border-radius: 8px;
  background: rgba(232, 93, 117, 0.12);
  border: 1px solid rgba(232, 93, 117, 0.35);
  color: #fca5b3;
  font-size: 0.85rem;
}

.saves-body {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 1.25rem;
  align-items: start;
}

.panel {
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 16px;
  overflow: hidden;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 1.1rem 1.25rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.panel-header h2 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.panel-badge {
  font-size: 0.7rem;
  color: #64748b;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  padding: 0.2rem 0.65rem;
  white-space: nowrap;
}

.game-list {
  list-style: none;
  margin: 0;
  padding: 0.4rem 0;
  max-height: 620px;
  overflow-y: auto;
}
.game-item {
  padding: 0.7rem 1.1rem;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.game-item:hover {
  background: rgba(255, 255, 255, 0.03);
}
.game-item.active {
  background: rgba(79, 156, 249, 0.1);
  border-left-color: #4f9cf9;
}
.game-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.game-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.game-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #334155;
  flex-shrink: 0;
}
.game-dot.on {
  background: #34c88a;
}
.game-sub {
  margin-top: 0.25rem;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 0.72rem;
  color: #64748b;
}
.game-ident {
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.game-time {
  flex-shrink: 0;
}

.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.75rem;
  padding: 1.1rem 1.25rem;
}
.slot-card {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  text-align: left;
  padding: 0.85rem 0.9rem;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(30, 41, 59, 0.5);
  color: #cbd5e1;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}
.slot-card.occupied:hover {
  transform: translateY(-2px);
  border-color: rgba(79, 156, 249, 0.5);
}
.slot-card.active {
  border-color: #4f9cf9;
  background: rgba(79, 156, 249, 0.12);
}
.slot-card:disabled {
  cursor: default;
  opacity: 0.5;
}
.slot-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slot-sub {
  font-size: 0.7rem;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.files-section {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding: 1rem 1.25rem 1.25rem;
}
.files-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.files-header h3 {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: #cbd5e1;
}
.files-count {
  margin-left: 0.4rem;
  font-size: 0.72rem;
  color: #64748b;
  font-weight: 400;
}
.zip-btn {
  background: rgba(79, 156, 249, 0.14);
  border: 1px solid rgba(79, 156, 249, 0.35);
  color: #93c5fd;
  border-radius: 8px;
  padding: 0.4rem 0.85rem;
  font-size: 0.8rem;
  cursor: pointer;
  transition: background 0.15s;
}
.zip-btn:hover:not(:disabled) {
  background: rgba(79, 156, 249, 0.24);
}
.zip-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.files-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}
.files-table th {
  text-align: left;
  padding: 0.5rem 0.6rem;
  color: #64748b;
  font-weight: 500;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  white-space: nowrap;
}
.files-table td {
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
}
.files-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.03);
}
.cell-path {
  max-width: 0;
  width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
}
.col-size,
.col-time {
  white-space: nowrap;
  color: #94a3b8;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.72rem;
}
.col-action {
  width: 1%;
  text-align: right;
}
.dl-btn {
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: #93c5fd;
  border-radius: 6px;
  width: 28px;
  height: 28px;
  cursor: pointer;
  transition: background 0.15s;
}
.dl-btn:hover {
  background: rgba(79, 156, 249, 0.18);
}

.hint {
  padding: 1.5rem 1.25rem;
  color: #475569;
  font-size: 0.85rem;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 3rem 1rem;
  color: #334155;
  font-size: 0.85rem;
}
.empty-state i {
  font-size: 1.5rem;
}

@media (max-width: 1024px) {
  .saves-body {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 640px) {
  .saves-page {
    padding: 1rem;
  }
}
</style>
