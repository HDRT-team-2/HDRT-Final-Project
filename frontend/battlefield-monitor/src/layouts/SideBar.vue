<script setup lang="ts">
import DetectedObjects from '@/components/sidebar/DetectedObjects.vue';
import FireSchedule from '@/components/sidebar/FireSchedule.vue';
import PositionInfo from '@/components/sidebar/PositionInfo.vue';
import SituationLog from '@/components/sidebar/SituationLog.vue';
import StatusReport from '@/components/sidebar/StatusReport.vue';
import TargetInput from '@/components/sidebar/TargetInput.vue';

import { defineAsyncComponent } from 'vue';

// 동적 컴포넌트 맵핑
const componentMap = {
  // Sidebar Components
  'StatusReport': () => import('@/components/sidebar/StatusReport.vue'),
  'SituationLog': () => import('@/components/sidebar/SituationLog.vue'),
  'PositionInfo': () => import('@/components/sidebar/PositionInfo.vue'),
  'TargetInput': () => import('@/components/sidebar/TargetInput.vue'),
  'DetectedObjects': () => import('@/components/sidebar/DetectedObjects.vue'),
  'FireSchedule': () => import('@/components/sidebar/FireSchedule.vue'),
};

// Props 정의
const props = defineProps<{
  contents: string[];
  col: number[];
}>();

// 동적 컴포넌트 생성
const getComponent = (componentName: string) => {
  const componentLoader = componentMap[componentName as keyof typeof componentMap];
  return componentLoader ? defineAsyncComponent(componentLoader) : null;
};

// Flex 비율로 동적 스타일 생성
const getFlexStyle = (ratio: number) => {
  return {
    flexGrow: ratio,
    flexShrink: 0,
    flexBasis: 0
  };
};

</script>

<template>
    <div class="flex flex-col h-full gap-2 p-2">
        <div
            v-for="(componentName, index) in contents"
            :key="componentName"
            :style="getFlexStyle(col[index])"
            class="flex-item"
        >
            <component
                :is="getComponent(componentName)"
                v-if="getComponent(componentName)"
                class="h-full"
            />
            <div v-else class="h-full flex items-center justify-center text-gray-500">
                {{ componentName }} (컴포넌트를 찾을 수 없음)
            </div>
        </div>
    </div>
</template>