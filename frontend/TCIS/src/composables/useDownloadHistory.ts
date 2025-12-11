import { ref } from 'vue'
import { ApiService } from '@/services/api_service'

/**
 * 사격 이력 다운로드
 */
export function useDownloadHistory() {
  const isDownloading = ref(false)
  const error = ref<string | null>(null)
  
  /**
   * 사격 이력 JSON 데이터 가져오기
   */
  async function fetchHistory(): Promise<any[] | null> {
    isDownloading.value = true
    error.value = null
    
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000'
      const api = new ApiService({ baseURL: API_URL })
      
      const response = await api.get<any[]>('/api/history')
      
      console.log('사격 이력 데이터 가져오기 완료:', response.data)
      return response.data
    } catch (err) {
      error.value = `데이터 가져오기 실패: ${err instanceof Error ? err.message : '알 수 없는 오류'}`
      console.error('사격 이력 데이터 가져오기 실패:', err)
      return null
    } finally {
      isDownloading.value = false
    }
  }
  
  return {
    isDownloading,
    error,
    fetchHistory
  }
}
