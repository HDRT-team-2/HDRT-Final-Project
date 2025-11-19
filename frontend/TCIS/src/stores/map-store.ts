import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export type MapId = '1' | '2' | '3' | '4'

export const useMapStore = defineStore('map', () => {
  const currentMapId = ref<MapId>('1')

  // 맵 ID에 따른 이미지 경로 매핑
  const mapImages: Record<MapId, string> = {
    '1': new URL('@/assets/images/maps/01_forest_and_river_basemap_with_contours.jpg', import.meta.url).href,
    '2': new URL('@/assets/images/maps/02_country_road_basemap_with_contours.png', import.meta.url).href,
    '3': new URL('@/assets/images/maps/03_wildness_dry_basemap_with_contours.png', import.meta.url).href,
    '4': new URL('@/assets/images/maps/04_simple_flat_basemap_with_contours-format.jpg', import.meta.url).href
  }

  // 현재 맵 이미지 URL
  const currentMapImage = computed(() => mapImages[currentMapId.value])

  // 맵 변경
  function setMapId(id: MapId) {
    currentMapId.value = id
  }

  return {
    currentMapId,
    currentMapImage,
    setMapId
  }
})
