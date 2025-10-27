<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import LabelText from '@/components/common/LabelText.vue';
import { ref } from 'vue';

// Pinia
import { storeToRefs } from 'pinia'
import { usePositionStore } from '@/stores/position'

// Store 연결
const positionStore = usePositionStore()

// 반응형으로 current 가져오기
const { current } = storeToRefs(positionStore)

// #TODO
// NOTE: WebSocket 연결은 composables/useWebSocket.ts에서 처리 예정
// WebSocket이 메시지를 받으면 자동으로 positionStore.updateCurrentPosition() 호출
// 그러면 current 값이 자동으로 업데이트됨

</script>

<template>
  <Card title="위치 정보">
    <div class="flex items-center justify-center gap-4">
      <LabelText 
        label="X"
        :value="current.x"
        :maxlength="3"
      />
      
      <LabelText 
        label="Y"
        :value="current.y"
        :maxlength="3"
      />
    </div>
  </Card>
</template>