/**
 * API Service
 * 
 * REST API 요청을 관리하는 공통 클래스
 * HTTP 요청 (GET, POST, PUT, DELETE 등)에서 재사용
 */

export interface ApiConfig {
  baseURL: string
  timeout?: number        // 타임아웃 (ms)
  headers?: Record<string, string>
  debug?: boolean
}

export interface ApiResponse<T = any> {
  data: T
  status: number
  statusText: string
}

export class ApiService {
  private baseURL: string
  private timeout: number
  private headers: Record<string, string>
  private debug: boolean
  
  constructor(config: ApiConfig) {
    this.baseURL = config.baseURL
    this.timeout = config.timeout ?? 30000
    this.headers = {
      'Content-Type': 'application/json',
      ...config.headers
    }
    this.debug = config.debug ?? false
  }
  
  /**
   * GET 요청
   */
  async get<T = any>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>('GET', endpoint)
  }
  
  /**
   * POST 요청
   */
  async post<T = any>(endpoint: string, data?: any): Promise<ApiResponse<T>> {
    return this.request<T>('POST', endpoint, data)
  }
  
  /**
   * PUT 요청
   */
  async put<T = any>(endpoint: string, data?: any): Promise<ApiResponse<T>> {
    return this.request<T>('PUT', endpoint, data)
  }
  
  /**
   * DELETE 요청
   */
  async delete<T = any>(endpoint: string): Promise<ApiResponse<T>> {
    return this.request<T>('DELETE', endpoint)
  }
  
  /**
   * 공통 요청 메서드
   */
  private async request<T>(
    method: string,
    endpoint: string,
    data?: any
  ): Promise<ApiResponse<T>> {
    const url = `${this.baseURL}${endpoint}`
    
    if (this.debug) {
      console.log(`[API] ${method} ${url}`, data ? data : '')
    }
    
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), this.timeout)
    
    try {
      const options: RequestInit = {
        method,
        headers: this.headers,
        signal: controller.signal
      }
      
      if (data && (method === 'POST' || method === 'PUT')) {
        options.body = JSON.stringify(data)
      }
      
      const response = await fetch(url, options)
      clearTimeout(timeoutId)
      
      // 응답 파싱
      let responseData: T
      const contentType = response.headers.get('content-type')
      
      if (contentType?.includes('application/json')) {
        responseData = await response.json()
      } else {
        responseData = await response.text() as T
      }
      
      // 에러 응답 처리
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      
      if (this.debug) {
        console.log(`[API] 응답 (${response.status}):`, responseData)
      }
      
      return {
        data: responseData,
        status: response.status,
        statusText: response.statusText
      }
      
    } catch (error) {
      clearTimeout(timeoutId)
      
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          console.error(`[API] 타임아웃: ${url}`)
          throw new Error('요청 시간 초과')
        }
        console.error(`[API] 오류: ${url}`, error.message)
        throw error
      }
      
      throw new Error('알 수 없는 오류 발생')
    }
  }
  
  /**
   * Base URL 변경
   */
  setBaseURL(url: string): void {
    this.baseURL = url
  }
  
  /**
   * 헤더 추가/변경
   */
  setHeader(key: string, value: string): void {
    this.headers[key] = value
  }
  
  /**
   * 헤더 제거
   */
  removeHeader(key: string): void {
    delete this.headers[key]
  }
}