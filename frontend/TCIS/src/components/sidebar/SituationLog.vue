<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import SituationLogItem from '@/components/common/SituationLogItem.vue';
import { ref, computed } from 'vue';
import { storeToRefs } from 'pinia';
import { useSituationStore } from '@/stores/situation';

// Situation Store 연결
const situationStore = useSituationStore();
const { events } = storeToRefs(situationStore);


</script>

<template>
  <Card title="전장 인식 결과">
    <div class="h-full flex flex-col">
      <div class="flex-1 overflow-y-auto">
        <TransitionGroup
          tag="div"
          class="space-y-1"
          enter-active-class="transition-all duration-300"
          enter-from-class="opacity-0 -translate-y-2"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition-all duration-200"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 translate-y-2"
        >
          <SituationLogItem 
            v-for="event in events" 
            :key="event.id"
            :event="event"
          />
        </TransitionGroup>
        <!-- 빈 상태 -->
        <div v-if="events.length === 0" class="text-center py-4 text-gray-500 text-xs">
          상황인지 결과가 없습니다.
        </div>
      </div>
    </div>
  </Card>

</template>