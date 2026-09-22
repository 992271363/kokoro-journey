<template>
  <div class="range-picker">
    <div class="presets">
      <button
        v-for="item in PRESETS"
        :key="item.key"
        class="chip"
        :class="{ active: preset === item.key }"
        @click="emit('preset', item.key)"
      >
        {{ item.label }}
      </button>
      <button class="chip" :class="{ active: preset === 'custom' }" @click="activateCustom">
        自定义
      </button>
    </div>
    <div v-if="preset === 'custom'" class="custom">
      <input class="input date" type="date" :value="localFrom" @change="onFromChange" />
      <span class="sep">至</span>
      <input class="input date" type="date" :value="localTo" @change="onToChange" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { PRESETS, type PresetKey } from '@/composables/useTimeRange'

const props = defineProps<{ preset: PresetKey; from: string; to: string }>()
const emit = defineEmits<{
  (e: 'preset', key: PresetKey): void
  (e: 'custom', from: string, to: string): void
}>()

const localFrom = ref(props.from)
const localTo = ref(props.to)

watch(
  () => [props.from, props.to],
  () => {
    localFrom.value = props.from
    localTo.value = props.to
  },
)

function onFromChange(event: Event) {
  localFrom.value = (event.target as HTMLInputElement).value
  emit('custom', localFrom.value, localTo.value)
}

function onToChange(event: Event) {
  localTo.value = (event.target as HTMLInputElement).value
  emit('custom', localFrom.value, localTo.value)
}

function activateCustom() {
  emit('preset', 'custom')
  emit('custom', props.from, props.to)
}
</script>

<style scoped>
.range-picker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2, 8px);
}
.presets {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--border);
  border-radius: var(--r-sm, 8px);
  background: rgba(2, 6, 23, 0.4);
}
.chip {
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 0.78rem;
  padding: 0.35rem 0.7rem;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.chip:hover {
  color: var(--text);
}
.chip.active {
  background: var(--accent-soft);
  color: #bfdbfe;
}
.custom {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.date {
  width: auto;
  padding: 0.35rem 0.5rem;
  font-size: 0.8rem;
  color-scheme: dark;
}
.sep {
  color: var(--text-faint);
  font-size: 0.78rem;
}
</style>
