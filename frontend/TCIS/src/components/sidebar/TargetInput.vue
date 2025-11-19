<script setup lang="ts">
import Card from '@/components/common/Card.vue'
import InputNumber from '@/components/common/InputNumber.vue'
import { ref, watch } from 'vue'

// pinia
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position'

// Store 연결
const positionStore = usePositionStore()
// 반응형으로 target 가져오기
const { target } = storeToRefs(positionStore)

const xPosition = ref('')
const yPosition = ref('')

// 무한 루프 방지 플래그
let isUpdatingFromStore = false

// target 값이 변경되면 input 값도 업데이트 (지도 클릭 시)
watch(target, (newTarget) => {
  isUpdatingFromStore = true
  
  if (newTarget && typeof newTarget.x === 'number' && typeof newTarget.y === 'number') {
    xPosition.value = newTarget.x.toFixed(3)
    yPosition.value = newTarget.y.toFixed(3)
  } else {
    xPosition.value = ''
    yPosition.value = ''
  }
  
  // 다음 틱에서 플래그 해제
  setTimeout(() => {
    isUpdatingFromStore = false
  }, 0)
}, { immediate: true })

// focus가 벗어났을 때 store 업데이트
const handleBlur = () => {
  if (isUpdatingFromStore) return
  
  if (xPosition.value !== '' && yPosition.value !== '') {
    let x = parseFloat(xPosition.value)
    let y = parseFloat(yPosition.value)
    
    // 300 초과 시 300으로 제한
    if (x > 300) {
      x = 300
      xPosition.value = '300.000'
    }
    if (y > 300) {
      y = 300
      yPosition.value = '300.000'
    }
    
    if (!isNaN(x) && !isNaN(y)) {
      positionStore.setTarget(x, y)
    }
  }
}
</script>

<template>
  <Card title="목표 위치">
    <div class="flex items-center justify-center gap-2">
      <InputNumber 
        v-model="xPosition"
        label="X"
        :maxlength="7"
        placeholder="000.000"
        @blur="handleBlur"
      />
      
      <InputNumber 
        v-model="yPosition"
        label="Y" 
        :maxlength="7"
        placeholder="000.000"
        @blur="handleBlur"
      />
    </div>
  </Card>
</template>