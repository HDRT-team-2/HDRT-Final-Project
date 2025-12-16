<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useDownloadHistory } from '@/composables/useDownloadHistory'

const { isDownloading, error, fetchHistory } = useDownloadHistory()
const showDropdown = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)

/**
 * JSON 데이터를 CSV로 변환
 */
function jsonToCSV(data: any[]): string {
  if (!data || data.length === 0) return ''
  
  // 헤더 추출
  const headers = Object.keys(data[0])
  const csvHeaders = headers.join(',')
  
  // 데이터 행 변환
  const csvRows = data.map(row => {
    return headers.map(header => {
      const value = row[header]
      // 쉼표나 따옴표가 있으면 따옴표로 감싸기
      if (typeof value === 'string' && (value.includes(',') || value.includes('"'))) {
        return `"${value.replace(/"/g, '""')}"`
      }
      return value
    }).join(',')
  })
  
  return [csvHeaders, ...csvRows].join('\n')
}

/**
 * JSON 데이터를 Excel용 CSV로 변환 (UTF-8 BOM 포함)
 */
function jsonToExcelCSV(data: any[]): string {
  const csv = jsonToCSV(data)
  // UTF-8 BOM 추가 (Excel에서 한글 깨짐 방지)
  return '\uFEFF' + csv
}

/**
 * CSV 다운로드
 */
async function handleDownloadCSV() {
  showDropdown.value = false
  const data = await fetchHistory()
  if (!data) {
    if (error.value) alert(error.value)
    return
  }
  
  const csv = jsonToCSV(data)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `fire_history_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

/**
 * Excel용 CSV 다운로드 (UTF-8 BOM 포함)
 */
async function handleDownloadExcel() {
  showDropdown.value = false
  const data = await fetchHistory()
  if (!data) {
    if (error.value) alert(error.value)
    return
  }
  
  const csv = jsonToExcelCSV(data)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `fire_history_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

const toggleDropdown = () => {
  showDropdown.value = !showDropdown.value
}

// 외부 클릭 감지
const handleClickOutside = (event: MouseEvent) => {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    showDropdown.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<template>
  <div class="relative inline-block" ref="dropdownRef">
    <!-- 다운로드 아이콘 버튼 -->
    <button 
      @click="toggleDropdown"
      :disabled="isDownloading"
      class="text-white hover:opacity-80 active:opacity-60 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed border-0 bg-transparent outline-none p-0"
    >
      <svg 
        v-if="!isDownloading"
        xmlns="http://www.w3.org/2000/svg" 
        width="16" 
        height="16" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        stroke-width="2" 
        stroke-linecap="round" 
        stroke-linejoin="round"
      >
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
        <polyline points="7 10 12 15 17 10"></polyline>
        <line x1="12" y1="15" x2="12" y2="3"></line>
      </svg>
      <svg 
        v-else
        class="animate-spin"
        xmlns="http://www.w3.org/2000/svg" 
        width="16" 
        height="16" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="currentColor" 
        stroke-width="2" 
        stroke-linecap="round" 
        stroke-linejoin="round"
      >
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M12 6v6l4 2"></path>
      </svg>
    </button>

    <!-- 드롭다운 메뉴 -->
    <div 
      v-if="showDropdown" 
      class="absolute top-full right-0 mt-1 bg-white border border-gray-200 rounded-md shadow-lg min-w-[160px] z-50 overflow-hidden"
    >
      <button 
        @click="handleDownloadCSV" 
        class="w-full flex items-center gap-2 px-3.5 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors border-b border-gray-100"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        CSV 다운로드
      </button>
      <button 
        @click="handleDownloadExcel" 
        class="w-full flex items-center gap-2 px-3.5 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        Excel 다운로드
      </button>
    </div>
  </div>
</template>
