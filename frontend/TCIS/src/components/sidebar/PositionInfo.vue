<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import LabelText from '@/components/common/LabelText.vue';
import { ref, computed } from 'vue';

// Pinia
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position-store'

// Store 연결
const positionStore = usePositionStore()

// 반응형으로 current 가져오기
const { current } = storeToRefs(positionStore)

const displayX = computed(() => current.value.x.toFixed(3))
const displayY = computed(() => current.value.y.toFixed(3))
// #TODO
// NOTE: WebSocket 연결은 composables/useWebSocket.ts에서 처리 예정
// WebSocket이 메시지를 받으면 자동으로 positionStore.updateCurrentPosition() 호출
// 그러면 current 값이 자동으로 업데이트됨

</script>

<template>
  <Card title="위치 정보">
    <div class="flex items-center justify-center gap-2">
      <LabelText 
        label="X"
        :value="displayX"
        :maxlength="7"
      />
      
      <LabelText 
        label="Y"
        :value="displayY"
        :maxlength="7"
      />
    </div>
  </Card>
</template>