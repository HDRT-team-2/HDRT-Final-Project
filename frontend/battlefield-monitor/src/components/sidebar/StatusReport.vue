<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import { ref } from 'vue';

// 작전 정보
const operationName = ref('천둥');
const operationStatus = ref('진행중');
const commanderName = ref('신중건');
</script>
<template>
  <Card title="상황 보고">
    <div class="space-y-1">
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
      <div class="bg-gray-50 rounded p-2 border border-gray-200 text-sm">
        <p>현재 전면전 개시 2일차로 아군, 적군간 대화력전이 실시되고 있는 상황.<br />
        적 기갑부대는 남방한계선 북측 20km 지점까지 남하하였으며 아군은 공격개시선 남측 10km 지점에서 공격명령 대기중.<br />
        아군의 임무는 남하하는 적 기갑부대를 격멸하고 목표지점인 00을 확보하는 것.</p>
      </div>
    </div>
  </Card>
</template>