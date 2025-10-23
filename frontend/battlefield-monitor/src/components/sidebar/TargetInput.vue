<script setup lang="ts">
import Card from '@/components/common/Card.vue';
import InputNumber from '@/components/common/InputNumber.vue';
import { ref } from 'vue';

const xPosition = ref('');
const yPosition = ref('');
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