<script setup lang="ts">
import { ref } from 'vue'
import { useDownloadHistory } from '@/composables/useDownloadHistory'

const { isDownloading, error, fetchHistory } = useDownloadHistory()
const showDropdown = ref(false)

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
</script>

<template>
  <div class="download-dropdown" v-click-outside="() => showDropdown = false">
    <!-- 다운로드 아이콘 버튼 -->
    <button 
      @click="toggleDropdown"
      class="download-icon-btn"
      :disabled="isDownloading"
      :class="{ 'loading': isDownloading }"
    >
      <svg 
        v-if="!isDownloading"
        xmlns="http://www.w3.org/2000/svg" 
        width="18" 
        height="18" 
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
        class="spinner"
        xmlns="http://www.w3.org/2000/svg" 
        width="18" 
        height="18" 
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
    <div v-if="showDropdown" class="dropdown-menu">
      <button @click="handleDownloadCSV" class="dropdown-item">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        CSV 다운로드
      </button>
      <button @click="handleDownloadExcel" class="dropdown-item">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        Excel 다운로드
      </button>
    </div>
  </div>
</template>

<style scoped>
.download-dropdown {
  position: relative;
  display: inline-block;
}

.download-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 0.375rem;
  color: white;
  cursor: pointer;
  transition: all 0.2s;
}

.download-icon-btn:hover:not(.loading) {
  background: rgba(255, 255, 255, 0.2);
  transform: translateY(-1px);
}

.download-icon-btn:active:not(.loading) {
  transform: translateY(0);
}

.download-icon-btn.loading {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 0.375rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  min-width: 160px;
  z-index: 1000;
  overflow: hidden;
}

.dropdown-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 0.875rem;
  background: white;
  border: none;
  text-align: left;
  font-size: 0.875rem;
  color: #374151;
  cursor: pointer;
  transition: background 0.15s;
}

.dropdown-item:hover {
  background: #f3f4f6;
}

.dropdown-item:not(:last-child) {
  border-bottom: 1px solid #f3f4f6;
}
</style>
