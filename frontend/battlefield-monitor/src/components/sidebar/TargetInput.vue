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
    xPosition.value = newTarget.x.toString()
    yPosition.value = newTarget.y.toString()
  } else {
    xPosition.value = ''
    yPosition.value = ''
  }
  
  // 다음 틱에서 플래그 해제
  setTimeout(() => {
    isUpdatingFromStore = false
  }, 0)
}, { immediate: true })

// input 값이 변경되면 store의 target 값도 업데이트
watch([xPosition, yPosition], ([newX, newY]) => {
  // Store에서 업데이트 중이면 무시
  if (isUpdatingFromStore) return
  
  if (newX !== '' && newY !== '') {
    const x = parseInt(newX)
    const y = parseInt(newY)
    if (!isNaN(x) && !isNaN(y)) {
      positionStore.setTarget(x, y)
    }
  }
})
</script>

<template>
  <Card title="목표 위치">
    <div class="flex items-center justify-center gap-4">
      <InputNumber 
        v-model="xPosition"
        label="X"
        :maxlength="3"
        placeholder="000"
      />
      
      <InputNumber 
        v-model="yPosition"
        label="Y" 
        :maxlength="3"
        placeholder="000"
      />
    </div>
  </Card>
</template>