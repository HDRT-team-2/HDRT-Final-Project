<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import LabelText from '@/components/common/LabelText.vue';
import { ref } from 'vue';

// 현재 위치 정보 (실제로는 props나 store에서 가져올 예정)
const currentX = ref(125);
const currentY = ref(347);
</script>

<template>
  <Card title="위치 정보">
    <div class="flex items-center justify-center gap-4">
      <LabelText 
        label="X"
        :value="currentX"
        :maxlength="3"
      />
      
      <LabelText 
        label="Y"
        :value="currentY"
        :maxlength="3"
      />
    </div>
  </Card>
</template>