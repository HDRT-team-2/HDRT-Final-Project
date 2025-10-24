<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import LabelText from '@/components/common/LabelText.vue';
import { ref } from 'vue';

// 작전 정보
const operationName = ref('천둥의 진격');
const operationStatus = ref('진행중');
const commanderName = ref('신중건');
</script>
<template>
  <Card title="상황 보고">
    <div class="space-y-3">
      <!-- 작전 정보 -->
      <div class="p-2 flex items-center justify-between">
        <h5 class="font-semibold text-primary-800">
          {{ operationName }} <span class="text-xs">({{ commanderName }})</span>
        </h5>
        <span class="px-2 py-1 bg-green-500 text-white text-xs rounded-full font-medium">
          {{ operationStatus }}
        </span>
      </div>

      <!-- 작전 목표 -->
      <div class="bg-gray-50 rounded p-2 border border-gray-200">
        <h4 class="text-xs font-bold text-gray-800 mb-1">주요 목표</h4>
        <ul class="text-xs text-gray-700 list-disc list-inside space-y-0.5">
          <li>적군 탱크 부대 제압</li>
          <li>전략 거점 [320, 240] 확보</li>
        </ul>
      </div>

      <!-- 현재 상황 -->
      <div class="bg-green-50 rounded p-2 border border-green-200">
        <h4 class="text-xs font-bold text-green-800 mb-1">현재 상황</h4>
        <ul class="text-xs text-green-700 list-disc list-inside space-y-0.5">
          <li>적군 3개 부대 탐지</li>
          <li>1차 타격 성공</li>
        </ul>
      </div>
    </div>
  </Card>
</template>