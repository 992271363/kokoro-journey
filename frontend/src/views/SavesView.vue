<template>
  <div class="page">
    <header class="page-header">
      <div>
        <p class="eyebrow">Cloud Saves</p>
        <h1 class="page-title">云存档浏览</h1>
      </div>
      <button class="btn" :disabled="loadingGames" @click="loadGames(true)">
        <i class="fas fa-rotate" :class="{ spinning: loadingGames }"></i> 刷新
      </button>
    </header>

    <p v-if="errorMessage" class="flash err">
      <i class="fas fa-triangle-exclamation"></i> {{ errorMessage }}
    </p>

    <div class="saves-body">
      <!-- 云端游戏列表 -->
      <aside class="panel games-panel">
        <div class="panel-header">
          <h2 class="panel-title">云端游戏</h2>
          <span class="panel-badge">{{ games.length }} 个</span>
        </div>
        <div v-if="loadingGames && games.length === 0" class="hint pad">加载中…</div>
        <div v-else-if="games.length === 0" class="empty-state">
          <i class="fas fa-box-open"></i>
          <p>云端还没有存档</p>
        </div>
        <ul v-else class="game-list scroll-y">
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
              <span class="game-time">{{
                formatDateTime(game.latestCreatedAt) || '暂无存档'
              }}</span>
            </div>
          </li>
        </ul>
      </aside>

      <!-- 存档位 + 文件清单 -->
      <section class="panel slots-panel">
        <div class="panel-header">
          <h2 class="panel-title">{{ selectedGame ? selectedGame.name : '存档位' }}</h2>
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
              class="slot-card card"
              :class="{ occupied: !!slot.versionId, active: slot.slot === selectedSlot }"
              :disabled="!slot.versionId"
              @click="selectSlot(slot)"
            >
              <span class="slot-name">{{ slot.label || `存档位 ${slot.slot}` }}</span>
              <span class="slot-sub">
                {{ slot.versionId ? formatDateTime(slot.createdAt) : '空' }}
              </span>
              <span class="slot-sub">
                {{
                  slot.versionId
                    ? `${formatSize(slot.totalSize)} · ${slot.fileCount ?? 0} 个文件`
                    : ''
                }}
              </span>
            </button>
          </div>

          <div class="files-section">
            <div class="files-header">
              <h3 class="panel-title">
                文件清单
                <span v-if="selectedSlotInfo && selectedSlotInfo.versionId" class="files-count">
                  {{ files.length }} 个
                </span>
              </h3>
              <button
                class="btn btn-primary"
                :disabled="!selectedSlotInfo || !selectedSlotInfo.versionId || filesLoading"
                @click="onDownloadZip"
              >
                <i class="fas fa-file-zipper"></i> 打包下载
              </button>
            </div>

            <div v-if="!selectedSlotInfo || !selectedSlotInfo.versionId" class="hint pad">
              选择一个已占用的存档位以查看文件
            </div>
            <div v-else-if="filesLoading" class="hint pad">加载中…</div>
            <div v-else-if="files.length === 0" class="hint pad">该存档位没有文件</div>
            <div v-else class="table-wrap">
              <table class="data-table">
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
                      <button class="btn btn-icon" title="下载该文件" @click="onDownloadFile(file)">
                        <i class="fas fa-download"></i>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
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
.spinning {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.saves-body {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: var(--sp-4);
  align-items: start;
}

.pad {
  padding: var(--sp-5);
}

/* 游戏列表 */
.game-list {
  list-style: none;
  margin: 0;
  padding: 0.4rem 0;
  max-height: 620px;
}
.game-item {
  padding: 0.7rem 1.1rem;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition:
    background 0.15s,
    border-color 0.15s;
}
.game-item:hover {
  background: var(--surface-hover);
}
.game-item.active {
  background: var(--accent-soft);
  border-left-color: var(--accent);
}
.game-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-2);
}
.game-name {
  font-size: 0.9rem;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.game-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  flex-shrink: 0;
}
.game-dot.on {
  background: var(--ok);
}
.game-sub {
  margin-top: 0.25rem;
  display: flex;
  justify-content: space-between;
  gap: var(--sp-2);
  font-size: 0.72rem;
  color: var(--text-faint);
}
.game-ident {
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.game-time {
  flex-shrink: 0;
}

/* 存档位 */
.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: var(--sp-3);
  padding: var(--sp-5);
}
.slot-card {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  text-align: left;
  padding: 0.8rem 0.9rem;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s,
    transform 0.15s;
}
.slot-card.occupied:hover {
  transform: translateY(-2px);
  border-color: var(--accent-border);
}
.slot-card.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.slot-card:disabled {
  cursor: default;
  opacity: 0.5;
}
.slot-name {
  font-size: 0.88rem;
  font-weight: 600;
  color: var(--text-strong);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slot-sub {
  font-size: 0.7rem;
  color: var(--text-faint);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 文件清单 */
.files-section {
  border-top: 1px solid var(--border);
  padding: var(--sp-4) var(--sp-5) var(--sp-5);
}
.files-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
  margin-bottom: var(--sp-3);
}
.files-count {
  margin-left: 0.4rem;
  font-size: 0.72rem;
  color: var(--text-faint);
  font-weight: 400;
}
.table-wrap {
  overflow-x: auto;
}
.cell-path {
  max-width: 0;
  width: 55%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 0.75rem;
}
.col-size,
.col-time {
  white-space: nowrap;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 0.72rem;
}
.col-action {
  width: 1%;
  text-align: right;
}

@media (max-width: 900px) {
  .saves-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
