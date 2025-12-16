<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const currentDate = ref('')
const currentTime = ref('')
let timer: number | null = null

const updateDateTime = () => {
  const now = new Date()
  
  // 날짜 포맷: YYYY/MM/DD
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  
  currentDate.value = `${year}/${month}/${day}`
  
  // 시간 포맷: HH:MM:SS
  const hours = String(now.getHours()).padStart(2, '0')
  const minutes = String(now.getMinutes()).padStart(2, '0')
//   const seconds = String(now.getSeconds()).padStart(2, '0')
  
//   currentTime.value = `${hours}:${minutes}:${seconds}`
  currentTime.value = `${hours}:${minutes}`
}

onMounted(() => {
  updateDateTime()
  timer = window.setInterval(updateDateTime, 1000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
  }
})
</script>

<template>
  <div class="text-white text-right text-xs">
    <div class="date">{{ currentDate }}</div>
    <div class="time">{{ currentTime }}</div>
  </div>
</template>
