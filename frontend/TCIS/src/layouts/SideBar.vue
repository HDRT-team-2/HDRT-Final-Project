<script setup lang="ts">
import DetectedObjects from '@/components/sidebar/DetectedObjects.vue';
import FireLog from '@/components/sidebar/FireLog.vue';
import SituationLog from '@/components/sidebar/SituationLog.vue';
import StatusReport from '@/components/sidebar/MissionStatusReport.vue';
import CommandPanel from '@/components/sidebar/CommandPanel.vue';
import Positions from '@/components/sidebar/Positions.vue';
import { defineAsyncComponent } from 'vue';

// 동적 컴포넌트 맵핑
const componentMap = {
  // Sidebar Components
  'StatusReport': () => import('@/components/sidebar/MissionStatusReport.vue'),
  'SituationLog': () => import('@/components/sidebar/SituationLog.vue'),
  'Positions': () => import('@/components/sidebar/Positions.vue'),
  'DetectedObjects': () => import('@/components/sidebar/DetectedObjects.vue'),
  'FireLog': () => import('@/components/sidebar/FireLog.vue'),
  'CommandPanel': () => import('@/components/sidebar/CommandPanel.vue'),
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
            class="flex-item min-h-0"
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