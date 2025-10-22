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
    <div class="sidebar flex flex-col h-full">
        <component
            v-for="(componentName, index) in contents"
            :is="getComponent(componentName)"
            :key="componentName"
            :style="getFlexStyle(col[index])"
        />
    </div>
</template>